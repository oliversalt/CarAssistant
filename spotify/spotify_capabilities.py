"""
spotify_capabilities_test.py

Tests the underlying Spotify API calls that CarPi will use.
Run this to verify each capability works before integrating into the main pipeline.

Make sure Spotify is open and playing on your phone before running.
"""

import os
import time
import random
from dotenv import load_dotenv
import spotipy
from spotipy.oauth2 import SpotifyOAuth

load_dotenv()

sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
    client_id=os.getenv("SPOTIFY_CLIENT_ID"),
    client_secret=os.getenv("SPOTIFY_CLIENT_SECRET"),
    redirect_uri=os.getenv("SPOTIFY_REDIRECT_URI"),
    scope=" ".join([
        "user-read-playback-state",
        "user-modify-playback-state",
        "user-read-private",
        "user-library-read",
        "user-read-currently-playing",
    ]),
    cache_path=".spotify_cache"
))

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def section(title):
    print(f"\n{'─' * 50}")
    print(f"  {title}")
    print(f"{'─' * 50}")

def get_active_device_id():
    """Returns the ID of the first active device, or None."""
    devices = sp.devices()
    for d in devices["devices"]:
        if d["is_active"]:
            return d["id"]
    if devices["devices"]:
        return devices["devices"][0]["id"]
    return None


# ─────────────────────────────────────────────
# TESTS
# ─────────────────────────────────────────────

def test_current_playback():
    section("1. Current playback state")
    playback = sp.current_playback()
    if not playback or not playback.get("item"):
        print("  ⚠ Nothing playing. Open Spotify and start a song first.")
    else:
        track = playback["item"]
        artist = track["artists"][0]["name"]
        album = track["album"]["name"]
        print(f"  Track:   {track['name']}")
        print(f"  Artist:  {artist}")
        print(f"  Album:   {album}")
        print(f"  Status:  {'Playing' if playback['is_playing'] else 'Paused'}")
        print(f"  Device:  {playback['device']['name']}")


def test_pause_resume():
    section("2. Pause & resume")
    print("  Pausing for 2 seconds...")
    sp.pause_playback()
    time.sleep(2)
    print("  Resuming...")
    sp.start_playback()
    print("  ✓ Pause/resume works")


def test_skip():
    section("3. Skip next & previous")
    print("  Skipping forward...")
    sp.next_track()
    time.sleep(1)
    playback = sp.current_playback()
    if playback and playback.get("item"):
        print(f"  Now playing: {playback['item']['name']}")
    time.sleep(1)
    print("  Going back to previous...")
    sp.previous_track()
    time.sleep(1)
    playback = sp.current_playback()
    if playback and playback.get("item"):
        print(f"  Now playing: {playback['item']['name']}")
    print("  ✓ Skip next/previous works")


def test_shuffle():
    section("5. Shuffle")
    print("  Enabling shuffle...")
    sp.shuffle(True)
    time.sleep(1)
    print("  Disabling shuffle...")
    sp.shuffle(False)
    time.sleep(1)
    print("  ✓ Shuffle works")


def test_track_details():
    section("6. Current track details (what CarPi passes to Claude)")
    playback = sp.current_playback()
    if playback and playback.get("item"):
        track = playback["item"]
        details = {
            "track_name": track["name"],
            "artist_name": track["artists"][0]["name"],
            "all_artists": [a["name"] for a in track["artists"]],
            "album_name": track["album"]["name"],
            "release_year": track["album"]["release_date"][:4],
            "spotify_url": track["external_urls"]["spotify"],
            "duration_ms": track["duration_ms"],
        }
        for k, v in details.items():
            print(f"  {k}: {v}")
        print("  ✓ Track details work (pass these to Claude for questions like 'who sings this')")


def test_artist_search():
    section("7. Search for an artist")
    ARTIST_QUERY = "Radiohead"
    results = sp.search(q=f"artist:{ARTIST_QUERY}", type="artist", limit=1)
    artists = results["artists"]["items"]
    if artists:
        artist = artists[0]
        print(f"  Found: {artist.get('name', 'Unknown')}")
        print(f"  Genres: {', '.join(artist.get('genres', [])[:3]) or 'N/A'}")
        print(f"  Popularity: {artist.get('popularity', 'N/A')}")
        print(f"  Artist URI: {artist.get('uri', 'N/A')}")
        print("  ✓ Artist search works")
        return artist.get("uri"), artist.get("id")
    else:
        print("  ✗ Artist not found")
        return None, None


def test_album_play():
    section("8. Search for an album and play it")
    ALBUM_QUERY = "OK Computer"
    ALBUM_ARTIST = "Radiohead"
    results = sp.search(q=f"album:{ALBUM_QUERY} artist:{ALBUM_ARTIST}", type="album", limit=1)
    albums = results["albums"]["items"]
    if albums:
        album = albums[0]
        print(f"  Found: {album['name']} by {album['artists'][0]['name']}")
        print(f"  Released: {album['release_date']}")
        print(f"  Album URI: {album['uri']}")
        print("  Playing album (first few tracks)...")
        sp.start_playback(context_uri=album["uri"])
        time.sleep(2)
        playback = sp.current_playback()
        if playback and playback.get("item"):
            print(f"  Now playing: {playback['item']['name']}")
        print("  ✓ Album search and play works")
    else:
        print("  ✗ Album not found")


def test_song_queue():
    section("9. Search for a specific song and queue it")
    SONG_QUERY = "Creep"
    SONG_ARTIST = "Radiohead"
    results = sp.search(q=f"track:{SONG_QUERY} artist:{SONG_ARTIST}", type="track", limit=1)
    tracks = results["tracks"]["items"]
    if tracks:
        track = tracks[0]
        print(f"  Found: {track['name']} by {track['artists'][0]['name']}")
        print(f"  Track URI: {track['uri']}")
        print("  Adding to queue...")
        sp.add_to_queue(track["uri"])
        print("  ✓ Song search and queue works")
    else:
        print("  ✗ Song not found")


def test_liked_songs_by_artist():
    section("10. Liked songs filtered by artist")
    TARGET_ARTIST = "Radiohead"
    print(f"  Scanning liked songs for tracks by {TARGET_ARTIST}...")
    print("  (Fetching up to 200 liked songs — this may take a moment)")

    liked_by_artist = []
    offset = 0
    limit = 50

    while True:
        results = sp.current_user_saved_tracks(limit=limit, offset=offset)
        items = results["items"]
        if not items:
            break
        for item in items:
            track = item["track"]
            artists = [a["name"].lower() for a in track["artists"]]
            if TARGET_ARTIST.lower() in artists:
                liked_by_artist.append(track)
        if len(items) < limit:
            break
        offset += limit

    if liked_by_artist:
        print(f"  Found {len(liked_by_artist)} liked songs by {TARGET_ARTIST}:")
        for t in liked_by_artist:
            print(f"    - {t['name']}")
        uris = [t["uri"] for t in liked_by_artist]
        random.shuffle(uris)
        device_id = get_active_device_id()
        sp.start_playback(device_id=device_id, uris=uris)
        sp.shuffle(True)
        time.sleep(1)
        playback = sp.current_playback()
        if playback and playback.get("item"):
            print(f"  Now playing: {playback['item']['name']}")
        print(f"  ✓ Liked songs by artist works")
    else:
        print(f"  No liked songs found by {TARGET_ARTIST} (try a different artist)")



def test_queue_view():
    section("12. View queue")
    queue = sp.queue()
    current = queue.get("currently_playing")
    upcoming = queue.get("queue", [])[:5]
    if current:
        print(f"  Now playing: {current['name']}")
    if upcoming:
        print(f"  Up next:")
        for t in upcoming:
            print(f"    - {t['name']} by {t['artists'][0]['name']}")
    print("  ✓ Queue works")


# ─────────────────────────────────────────────
# RUN TESTS — comment out any you want to skip
# ─────────────────────────────────────────────

# test_current_playback()
# test_pause_resume()
# test_skip()
# test_shuffle()
# test_track_details()
artist_uri, artist_id = test_artist_search()
# test_album_play()
# test_song_queue()
# test_liked_songs_by_artist()
test_queue_view()

section("All tests complete")
print("  Any ✗ above means that feature needs attention.")
print("  Any ✓ means it's ready to integrate into CarPi.")
