import os
import time
from dotenv import load_dotenv
import spotipy
from spotipy.oauth2 import SpotifyOAuth

load_dotenv()

sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
    client_id=os.getenv("SPOTIFY_CLIENT_ID"),
    client_secret=os.getenv("SPOTIFY_CLIENT_SECRET"),
    redirect_uri=os.getenv("SPOTIFY_REDIRECT_URI"),
    scope="user-read-playback-state user-modify-playback-state user-read-private",
    cache_path=".spotify_cache"
))

# --- Show current playback ---
playback = sp.current_playback()

if not playback:
    print("Nothing is currently playing.")
    print("Open Spotify on your phone or PC and play something first.")
else:
    track = playback["item"]
    device = playback["device"]
    is_playing = playback["is_playing"]

    print(f"Device:  {device['name']} ({device['type']})")
    print(f"Track:   {track['name']} by {track['artists'][0]['name']}")
    print(f"Status:  {'Playing' if is_playing else 'Paused'}")
    print()

    # --- Pause ---
    print("Pausing...")
    sp.pause_playback()
    time.sleep(2)

    # --- Resume ---
    print("Resuming...")
    sp.start_playback()
    time.sleep(2)

    # --- Skip ---
    print("Skipping to next track...")
    sp.next_track()
    time.sleep(1)

    # --- Show what's playing now ---
    playback = sp.current_playback()
    if playback and playback["item"]:
        track = playback["item"]
        print(f"Now playing: {track['name']} by {track['artists'][0]['name']}")

    print("\nPlayback control working!")