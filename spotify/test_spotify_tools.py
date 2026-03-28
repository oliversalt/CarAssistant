"""
test_spotify_tools.py

End-to-end tests for spotify_tools.py composite tools.
Make sure Spotify is open and playing on your phone before running.
"""

import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from spotify.spotify_tools import (
    get_current_track_info,
    play_song,
    queue_song,
    play_album,
    play_liked_songs_by_artist,
    play_liked_songs_shuffled,
    find_and_queue_song_by_description,
    search_spotify,
    pause,
    resume,
    skip_next,
    skip_previous,
    get_queue,
    get_available_devices,
    set_shuffle,
)


def section(title):
    print(f"\n{'─' * 50}")
    print(f"  {title}")
    print(f"{'─' * 50}")


def show(result):
    print(json.dumps(result, indent=2))


# ─────────────────────────────────────────────
# RUN TESTS — comment out any you want to skip
# ─────────────────────────────────────────────

section("get_current_track_info")
show(get_current_track_info())

section("search_spotify — track")
show(search_spotify("Creep", type="track", limit=3))

section("search_spotify — album")
show(search_spotify("OK Computer", type="album", limit=3))

section("search_spotify — artist")
show(search_spotify("Radiohead", type="artist", limit=3))

section("find_and_queue_song_by_description")
show(find_and_queue_song_by_description("Radiohead song about a creep feeling out of place"))

section("get_available_devices")
show(get_available_devices())

section("get_queue")
show(get_queue())

section("play_song")
show(play_song("Creep", artist_name="Radiohead"))

section("queue_song")
show(queue_song("Karma Police", artist_name="Radiohead"))

section("play_album")
show(play_album("OK Computer", artist_name="Radiohead"))

section("play_liked_songs_by_artist")
show(play_liked_songs_by_artist("Radiohead"))

section("play_liked_songs_shuffled")
show(play_liked_songs_shuffled())

section("All tests complete")
print("  Any 'error' keys above mean that feature needs attention.")
