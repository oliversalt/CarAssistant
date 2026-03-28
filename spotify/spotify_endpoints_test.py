"""
spotify_endpoint_tests.py

Tests every relevant Spotify Web API endpoint individually.
Run this before building composite tools — it tells you exactly what works.

BEFORE RUNNING:
- Make sure Spotify is open and playing on your phone
- Change the config values below to match your library
"""

import os
import time
from dotenv import load_dotenv
import spotipy
from spotipy.oauth2 import SpotifyOAuth

load_dotenv()

# ─────────────────────────────────────────────
# CONFIG — change these to match your library
# ─────────────────────────────────────────────

TEST_ARTIST_NAME    = "Radiohead"
TEST_ALBUM_NAME     = "OK Computer"
TEST_TRACK_NAME     = "Creep"
TEST_PLAYLIST_ID    = ""   # paste a playlist ID you own here (from its Spotify URL)

# ─────────────────────────────────────────────
# AUTH
# ─────────────────────────────────────────────

sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
    client_id=os.getenv("SPOTIFY_CLIENT_ID"),
    client_secret=os.getenv("SPOTIFY_CLIENT_SECRET"),
    redirect_uri=os.getenv("SPOTIFY_REDIRECT_URI"),
    scope=" ".join([
        "user-read-playback-state",
        "user-modify-playback-state",
        "user-read-currently-playing",
        "user-read-private",
        "user-library-read",
        "user-read-recently-played",
        "playlist-read-private",
        "playlist-read-collaborative",
        "playlist-modify-public",
        "playlist-modify-private",
    ]),
    cache_path=".spotify_cache"
))

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

passed = []
failed = []

def section(title):
    print(f"\n{'═' * 55}")
    print(f"  {title}")
    print(f"{'═' * 55}")

def ok(name, info=""):
    print(f"  ✓ {name}" + (f" — {info}" if info else ""))
    passed.append(name)

def fail(name, err):
    print(f"  ✗ {name} — {err}")
    failed.append(name)

def get_active_device_id():
    devices = sp.devices()
    for d in devices["devices"]:
        if d["is_active"]:
            return d["id"]
    if devices["devices"]:
        return devices["devices"][0]["id"]
    return None


# ══════════════════════════════════════════════
# ALBUMS
# ══════════════════════════════════════════════
section("ALBUMS")

# Search for album first so we have an ID
_album_id = None
try:
    r = sp.search(q=f"album:{TEST_ALBUM_NAME} artist:{TEST_ARTIST_NAME}", type="album", limit=1)
    _album_id = r["albums"]["items"][0]["id"]
except Exception as e:
    fail("album search (needed for album tests)", e)

# Get Album
try:
    if _album_id:
        album = sp.album(_album_id)
        ok("Get Album", f"{album['name']} — {album['total_tracks']} tracks")
except Exception as e:
    fail("Get Album", e)

# Get Album Tracks
try:
    if _album_id:
        tracks = sp.album_tracks(_album_id)
        names = [t["name"] for t in tracks["items"][:3]]
        ok("Get Album Tracks", f"First 3: {', '.join(names)}")
except Exception as e:
    fail("Get Album Tracks", e)

# Get User's Saved Albums
try:
    saved = sp.current_user_saved_albums(limit=5)
    names = [i["album"]["name"] for i in saved["items"]]
    ok("Get User's Saved Albums", f"First 5: {', '.join(names)}")
except Exception as e:
    fail("Get User's Saved Albums", e)


# ══════════════════════════════════════════════
# ARTISTS
# ══════════════════════════════════════════════
section("ARTISTS")

_artist_id = None
try:
    r = sp.search(q=f"artist:{TEST_ARTIST_NAME}", type="artist", limit=1)
    _artist_id = r["artists"]["items"][0]["id"]
except Exception as e:
    fail("artist search (needed for artist tests)", e)

# Get Artist
try:
    if _artist_id:
        artist = sp.artist(_artist_id)
        ok("Get Artist", f"{artist['name']} — popularity {artist['popularity']}, genres: {', '.join(artist['genres'][:2])}")
except Exception as e:
    fail("Get Artist", e)

# Get Artist's Albums
try:
    if _artist_id:
        albums = sp.artist_albums(_artist_id, album_type="album", limit=5)
        names = [a["name"] for a in albums["items"]]
        ok("Get Artist's Albums", f"First 5: {', '.join(names)}")
except Exception as e:
    fail("Get Artist's Albums", e)


# ══════════════════════════════════════════════
# PLAYER
# ══════════════════════════════════════════════
section("PLAYER")

# Get Playback State
_playback = None
try:
    _playback = sp.current_playback()
    if _playback and _playback.get("item"):
        track = _playback["item"]
        ok("Get Playback State", f"{track['name']} by {track['artists'][0]['name']}")
    else:
        fail("Get Playback State", "Nothing playing — open Spotify and start a song")
except Exception as e:
    fail("Get Playback State", e)

# Get Available Devices
_device_id = None
try:
    devices = sp.devices()
    _device_id = get_active_device_id()
    names = [d["name"] for d in devices["devices"]]
    ok("Get Available Devices", f"{', '.join(names)}")
except Exception as e:
    fail("Get Available Devices", e)

# Get Currently Playing Track
try:
    current = sp.currently_playing()
    if current and current.get("item"):
        ok("Get Currently Playing Track", current["item"]["name"])
    else:
        fail("Get Currently Playing Track", "Nothing playing")
except Exception as e:
    fail("Get Currently Playing Track", e)

# Pause Playback
try:
    sp.pause_playback()
    time.sleep(1)
    ok("Pause Playback")
except Exception as e:
    fail("Pause Playback", e)

# Start/Resume Playback
try:
    sp.start_playback()
    time.sleep(1)
    ok("Start/Resume Playback")
except Exception as e:
    fail("Start/Resume Playback", e)

# Skip To Next
try:
    sp.next_track()
    time.sleep(1)
    current = sp.currently_playing()
    if current and current.get("item"):
        ok("Skip To Next", f"Now: {current['item']['name']}")
    else:
        ok("Skip To Next")
except Exception as e:
    fail("Skip To Next", e)

# Skip To Previous
try:
    sp.previous_track()
    time.sleep(1)
    current = sp.currently_playing()
    if current and current.get("item"):
        ok("Skip To Previous", f"Now: {current['item']['name']}")
    else:
        ok("Skip To Previous")
except Exception as e:
    fail("Skip To Previous", e)

# Seek To Position (seek to 30 seconds in)
try:
    sp.seek_track(30000)  # milliseconds
    time.sleep(1)
    ok("Seek To Position", "Seeked to 30s")
except Exception as e:
    fail("Seek To Position", e)

# Set Repeat Mode (off / track / context)
try:
    sp.repeat("off")
    time.sleep(0.5)
    sp.repeat("context")
    time.sleep(0.5)
    sp.repeat("off")
    ok("Set Repeat Mode", "Cycled off → context → off")
except Exception as e:
    fail("Set Repeat Mode", e)

# Toggle Shuffle
try:
    sp.shuffle(True)
    time.sleep(0.5)
    sp.shuffle(False)
    ok("Toggle Shuffle", "Enabled then disabled")
except Exception as e:
    fail("Toggle Shuffle", e)

# Transfer Playback (transfer to same device — harmless)
try:
    if _device_id:
        sp.transfer_playback(_device_id, force_play=False)
        ok("Transfer Playback", f"Transferred to {_device_id[:8]}...")
    else:
        fail("Transfer Playback", "No device ID available")
except Exception as e:
    fail("Transfer Playback", e)

# Get Recently Played Tracks
try:
    recent = sp.current_user_recently_played(limit=5)
    names = [i["track"]["name"] for i in recent["items"]]
    ok("Get Recently Played Tracks", f"Last 5: {', '.join(names)}")
except Exception as e:
    fail("Get Recently Played Tracks", e)

# Get the User's Queue
try:
    queue = sp.queue()
    upcoming = [t["name"] for t in queue.get("queue", [])[:3]]
    ok("Get the User's Queue", f"Next up: {', '.join(upcoming) if upcoming else 'empty'}")
except Exception as e:
    fail("Get the User's Queue", e)

# Add Item to Playback Queue
_track_uri = None
try:
    r = sp.search(q=f"track:{TEST_TRACK_NAME} artist:{TEST_ARTIST_NAME}", type="track", limit=1)
    _track_uri = r["tracks"]["items"][0]["uri"]
    sp.add_to_queue(_track_uri)
    ok("Add Item to Playback Queue", f"Queued: {TEST_TRACK_NAME}")
except Exception as e:
    fail("Add Item to Playback Queue", e)


# ══════════════════════════════════════════════
# PLAYLISTS
# ══════════════════════════════════════════════
section("PLAYLISTS")

# Get Current User's Playlists
_first_playlist_id = None
try:
    playlists = sp.current_user_playlists(limit=10)
    items = playlists["items"]
    names = [p["name"] for p in items[:5]]
    ok("Get Current User's Playlists", f"First 5: {', '.join(names)}")
    # Use first owned playlist for further tests if no ID configured
    if not TEST_PLAYLIST_ID:
        user_id = sp.current_user()["id"]
        for p in items:
            if p["owner"]["id"] == user_id:
                _first_playlist_id = p["id"]
                print(f"    → Using '{p['name']}' (ID: {_first_playlist_id}) for playlist tests")
                print(f"    → Set TEST_PLAYLIST_ID in config to use a specific playlist")
                break
    else:
        _first_playlist_id = TEST_PLAYLIST_ID
except Exception as e:
    fail("Get Current User's Playlists", e)

# Get Playlist
try:
    if _first_playlist_id:
        playlist = sp.playlist(_first_playlist_id)
        ok("Get Playlist", f"{playlist['name']} — {playlist['tracks']['total']} tracks")
    else:
        fail("Get Playlist", "No playlist ID available")
except Exception as e:
    fail("Get Playlist", e)

# Get Playlist Items
_playlist_track_uri = None
try:
    if _first_playlist_id:
        items = sp.playlist_items(_first_playlist_id, limit=5)
        tracks = items["items"]
        names = [t["track"]["name"] for t in tracks if t.get("track")]
        if tracks and tracks[0].get("track"):
            _playlist_track_uri = tracks[0]["track"]["uri"]
        ok("Get Playlist Items", f"First 5: {', '.join(names)}")
    else:
        fail("Get Playlist Items", "No playlist ID available")
except Exception as e:
    fail("Get Playlist Items", e)

# Add Items to Playlist
try:
    if _first_playlist_id and _track_uri:
        sp.playlist_add_items(_first_playlist_id, [_track_uri])
        ok("Add Items to Playlist", f"Added {TEST_TRACK_NAME}")
    else:
        fail("Add Items to Playlist", "No playlist ID or track URI available")
except Exception as e:
    fail("Add Items to Playlist", e)

# Remove Playlist Items
try:
    if _first_playlist_id and _track_uri:
        sp.playlist_remove_all_occurrences_of_items(_first_playlist_id, [_track_uri])
        ok("Remove Playlist Items", f"Removed {TEST_TRACK_NAME}")
    else:
        fail("Remove Playlist Items", "No playlist ID or track URI available")
except Exception as e:
    fail("Remove Playlist Items", e)

# Get Playlist Cover Image
try:
    if _first_playlist_id:
        images = sp.playlist_cover_image(_first_playlist_id)
        ok("Get Playlist Cover Image", f"{images[0]['url'][:50]}..." if images else "No image")
    else:
        fail("Get Playlist Cover Image", "No playlist ID available")
except Exception as e:
    fail("Get Playlist Cover Image", e)


# ══════════════════════════════════════════════
# SEARCH
# ══════════════════════════════════════════════
section("SEARCH")

# Search — track
try:
    r = sp.search(q=f"track:{TEST_TRACK_NAME} artist:{TEST_ARTIST_NAME}", type="track", limit=3)
    names = [t["name"] for t in r["tracks"]["items"]]
    ok("Search — track", f"Results: {', '.join(names)}")
except Exception as e:
    fail("Search — track", e)

# Search — album
try:
    r = sp.search(q=f"album:{TEST_ALBUM_NAME} artist:{TEST_ARTIST_NAME}", type="album", limit=3)
    names = [a["name"] for a in r["albums"]["items"]]
    ok("Search — album", f"Results: {', '.join(names)}")
except Exception as e:
    fail("Search — album", e)

# Search — artist
try:
    r = sp.search(q=f"artist:{TEST_ARTIST_NAME}", type="artist", limit=3)
    names = [a["name"] for a in r["artists"]["items"]]
    ok("Search — artist", f"Results: {', '.join(names)}")
except Exception as e:
    fail("Search — artist", e)


# ══════════════════════════════════════════════
# TRACKS
# ══════════════════════════════════════════════
section("TRACKS")

# Get Track
try:
    if _track_uri:
        track_id = _track_uri.split(":")[-1]
        track = sp.track(track_id)
        ok("Get Track", f"{track['name']} — {track['duration_ms'] // 1000}s, popularity {track['popularity']}")
except Exception as e:
    fail("Get Track", e)

# Get User's Saved Tracks
try:
    saved = sp.current_user_saved_tracks(limit=5)
    names = [i["track"]["name"] for i in saved["items"]]
    ok("Get User's Saved Tracks", f"First 5: {', '.join(names)}")
except Exception as e:
    fail("Get User's Saved Tracks", e)


# ══════════════════════════════════════════════
# SUMMARY
# ══════════════════════════════════════════════
section("SUMMARY")
print(f"  Passed: {len(passed)}")
print(f"  Failed: {len(failed)}")
if failed:
    print(f"\n  Failed endpoints:")
    for f in failed:
        print(f"    ✗ {f}")
else:
    print("\n  All endpoints working — ready to build composite tools.")