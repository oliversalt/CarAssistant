"""
spotify_tools.py

Spotify integration layer for CarPi.
Provides raw endpoint wrappers and composite tools that Claude can call
via voice commands. Designed to be imported into tools.py and exposed
to the model via the TOOLS list and dispatch().

All functions catch exceptions and return None / [] / error dict — never raise.
"""

import json
import os
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
# Internal helpers
# ─────────────────────────────────────────────

def get_active_device_id():
    """Returns the active device ID, falling back to the first available."""
    try:
        devices = sp.devices().get("devices", [])
        for d in devices:
            if d["is_active"]:
                return d["id"]
        if devices:
            return devices[0]["id"]
    except Exception as e:
        print(f"[Spotify] get_active_device_id failed: {e}")
    return None


def _track_dict(track: dict) -> dict:
    """Normalise a Spotify track object into a consistent shape."""
    return {
        "name": track.get("name", ""),
        "artist": track["artists"][0]["name"] if track.get("artists") else "",
        "album": track.get("album", {}).get("name", "") if track.get("album") else "",
        "uri": track.get("uri", ""),
        "duration_seconds": track.get("duration_ms", 0) // 1000,
    }


def _album_dict(album: dict) -> dict:
    """Normalise a Spotify album object into a consistent shape."""
    return {
        "name": album.get("name", ""),
        "artist": album["artists"][0]["name"] if album.get("artists") else "",
        "uri": album.get("uri", ""),
        "total_tracks": album.get("total_tracks", 0),
        "release_date": album.get("release_date", ""),
    }


# ─────────────────────────────────────────────
# Raw endpoint wrappers
# ─────────────────────────────────────────────

def get_playback_state() -> dict | None:
    try:
        pb = sp.current_playback()
        if not pb or not pb.get("item"):
            return None
        track = pb["item"]
        return {
            "track": track.get("name", ""),
            "artist": track["artists"][0]["name"] if track.get("artists") else "",
            "album": track.get("album", {}).get("name", ""),
            "is_playing": pb.get("is_playing", False),
            "device": pb.get("device", {}).get("name", ""),
            "progress_ms": pb.get("progress_ms", 0),
            "duration_ms": track.get("duration_ms", 0),
        }
    except Exception as e:
        print(f"[Spotify] get_playback_state failed: {e}")
        return None


def get_currently_playing() -> dict | None:
    return get_playback_state()


def get_available_devices() -> list:
    try:
        return [
            {
                "id": d.get("id", ""),
                "name": d.get("name", ""),
                "type": d.get("type", ""),
                "is_active": d.get("is_active", False),
                "volume_percent": d.get("volume_percent"),
            }
            for d in sp.devices().get("devices", [])
        ]
    except Exception as e:
        print(f"[Spotify] get_available_devices failed: {e}")
        return []


def get_queue() -> dict:
    try:
        q = sp.queue()
        current = q.get("currently_playing")
        return {
            "currently_playing": _track_dict(current) if current else None,
            "queue": [_track_dict(t) for t in q.get("queue", [])],
        }
    except Exception as e:
        print(f"[Spotify] get_queue failed: {e}")
        return {"currently_playing": None, "queue": []}


def get_recently_played(n: int = 10) -> list:
    try:
        results = sp.current_user_recently_played(limit=n)
        return [_track_dict(item["track"]) for item in results.get("items", [])]
    except Exception as e:
        print(f"[Spotify] get_recently_played failed: {e}")
        return []


def get_saved_tracks(limit: int = 50, offset: int = 0) -> list:
    try:
        results = sp.current_user_saved_tracks(limit=limit, offset=offset)
        return [_track_dict(item["track"]) for item in results.get("items", [])]
    except Exception as e:
        print(f"[Spotify] get_saved_tracks failed: {e}")
        return []


def get_saved_albums(limit: int = 20) -> list:
    try:
        results = sp.current_user_saved_albums(limit=limit)
        return [_album_dict(item["album"]) for item in results.get("items", [])]
    except Exception as e:
        print(f"[Spotify] get_saved_albums failed: {e}")
        return []


def get_user_playlists() -> list:
    try:
        results = sp.current_user_playlists()
        return [
            {
                "id": p.get("id", ""),
                "name": p.get("name", ""),
                "track_count": p.get("tracks", {}).get("total", 0),
                "owner": p.get("owner", {}).get("display_name", ""),
            }
            for p in results.get("items", [])
        ]
    except Exception as e:
        print(f"[Spotify] get_user_playlists failed: {e}")
        return []


def get_playlist_items(playlist_id: str) -> list:
    try:
        results = sp.playlist_items(playlist_id)
        return [
            _track_dict(item["track"])
            for item in results.get("items", [])
            if item.get("track")
        ]
    except Exception as e:
        print(f"[Spotify] get_playlist_items failed: {e}")
        return []


def get_artist_albums(artist_name: str) -> list:
    try:
        results = sp.search(q=f"artist:{artist_name}", type="artist", limit=1)
        artists = results.get("artists", {}).get("items", [])
        if not artists:
            return []
        artist_id = artists[0]["id"]
        albums = sp.artist_albums(artist_id, album_type="album", limit=20)
        return [_album_dict(a) for a in albums.get("items", [])]
    except Exception as e:
        print(f"[Spotify] get_artist_albums failed: {e}")
        return []


def pause() -> None:
    try:
        sp.pause_playback()
    except Exception as e:
        print(f"[Spotify] pause failed: {e}")


def resume() -> None:
    try:
        sp.start_playback()
    except Exception as e:
        print(f"[Spotify] resume failed: {e}")


def skip_next() -> None:
    try:
        sp.next_track()
    except Exception as e:
        print(f"[Spotify] skip_next failed: {e}")


def skip_previous() -> None:
    try:
        sp.previous_track()
    except Exception as e:
        print(f"[Spotify] skip_previous failed: {e}")


def seek(seconds: int) -> None:
    try:
        sp.seek_track(seconds * 1000)
    except Exception as e:
        print(f"[Spotify] seek failed: {e}")


def set_volume(percent: int) -> None:
    try:
        sp.volume(max(0, min(100, percent)))
    except Exception as e:
        print(f"[Spotify] set_volume failed: {e}")


def set_shuffle(enabled: bool) -> None:
    try:
        sp.shuffle(enabled)
    except Exception as e:
        print(f"[Spotify] set_shuffle failed: {e}")


def set_repeat(mode: str) -> None:
    try:
        sp.repeat(mode)
    except Exception as e:
        print(f"[Spotify] set_repeat failed: {e}")


def transfer_playback(device_id: str, force_play: bool = False) -> None:
    try:
        sp.transfer_playback(device_id, force_play=force_play)
    except Exception as e:
        print(f"[Spotify] transfer_playback failed: {e}")


def add_to_queue(track_uri: str) -> None:
    try:
        sp.add_to_queue(track_uri)
    except Exception as e:
        print(f"[Spotify] add_to_queue failed: {e}")


def add_to_playlist(playlist_id: str, track_uris: list) -> None:
    try:
        sp.playlist_add_items(playlist_id, track_uris)
    except Exception as e:
        print(f"[Spotify] add_to_playlist failed: {e}")


def remove_from_playlist(playlist_id: str, track_uris: list) -> None:
    try:
        sp.playlist_remove_all_occurrences_of_items(playlist_id, track_uris)
    except Exception as e:
        print(f"[Spotify] remove_from_playlist failed: {e}")


# ─────────────────────────────────────────────
# Composite tools
# ─────────────────────────────────────────────

def play_song(song_name: str, artist_name: str = None) -> dict:
    try:
        query = f"track:{song_name}"
        if artist_name:
            query += f" artist:{artist_name}"
        results = sp.search(q=query, type="track", limit=1)
        tracks = results.get("tracks", {}).get("items", [])
        if not tracks:
            return {"error": f"No track found for '{song_name}'"}
        track = tracks[0]
        sp.start_playback(uris=[track["uri"]])
        return {
            "track": track["name"],
            "artist": track["artists"][0]["name"],
            "album": track["album"]["name"],
        }
    except Exception as e:
        print(f"[Spotify] play_song failed: {e}")
        return {"error": str(e)}


def queue_song(song_name: str, artist_name: str = None) -> dict:
    try:
        query = f"track:{song_name}"
        if artist_name:
            query += f" artist:{artist_name}"
        results = sp.search(q=query, type="track", limit=1)
        tracks = results.get("tracks", {}).get("items", [])
        if not tracks:
            return {"error": f"No track found for '{song_name}'"}
        track = tracks[0]
        sp.add_to_queue(track["uri"])
        return {
            "track": track["name"],
            "artist": track["artists"][0]["name"],
        }
    except Exception as e:
        print(f"[Spotify] queue_song failed: {e}")
        return {"error": str(e)}


def play_album(album_name: str, artist_name: str = None) -> dict:
    try:
        query = f"album:{album_name}"
        if artist_name:
            query += f" artist:{artist_name}"
        results = sp.search(q=query, type="album", limit=1)
        albums = results.get("albums", {}).get("items", [])
        if not albums:
            return {"error": f"No album found for '{album_name}'"}
        album = albums[0]
        sp.start_playback(context_uri=album["uri"])
        return {
            "album": album["name"],
            "artist": album["artists"][0]["name"],
            "total_tracks": album.get("total_tracks", 0),
        }
    except Exception as e:
        print(f"[Spotify] play_album failed: {e}")
        return {"error": str(e)}


def play_liked_songs_by_artist(artist_name: str) -> dict:
    try:
        liked = []
        offset = 0
        while True:
            results = sp.current_user_saved_tracks(limit=50, offset=offset)
            items = results.get("items", [])
            if not items:
                break
            for item in items:
                track = item["track"]
                if any(a["name"].lower() == artist_name.lower() for a in track.get("artists", [])):
                    liked.append(track)
            if len(items) < 50:
                break
            offset += 50

        if not liked:
            return {"error": f"No liked songs found by '{artist_name}'"}

        uris = [t["uri"] for t in liked]
        random.shuffle(uris)
        device_id = get_active_device_id()
        sp.start_playback(device_id=device_id, uris=uris)
        sp.shuffle(True)
        now = sp.current_playback()
        now_playing = now["item"]["name"] if now and now.get("item") else liked[0]["name"]
        return {
            "artist": artist_name,
            "track_count": len(uris),
            "now_playing": now_playing,
        }
    except Exception as e:
        print(f"[Spotify] play_liked_songs_by_artist failed: {e}")
        return {"error": str(e)}


def play_liked_songs_shuffled() -> dict:
    try:
        all_tracks = []
        offset = 0
        while len(all_tracks) < 200:
            results = sp.current_user_saved_tracks(limit=50, offset=offset)
            items = results.get("items", [])
            if not items:
                break
            all_tracks.extend(item["track"] for item in items)
            if len(items) < 50:
                break
            offset += 50

        if not all_tracks:
            return {"error": "No liked songs found"}

        uris = [t["uri"] for t in all_tracks]
        random.shuffle(uris)
        device_id = get_active_device_id()
        sp.start_playback(device_id=device_id, uris=uris)
        sp.shuffle(True)
        now = sp.current_playback()
        now_playing = now["item"]["name"] if now and now.get("item") else "Unknown"
        return {
            "track_count": len(uris),
            "now_playing": now_playing,
        }
    except Exception as e:
        print(f"[Spotify] play_liked_songs_shuffled failed: {e}")
        return {"error": str(e)}


def get_current_track_info() -> dict | None:
    try:
        pb = sp.current_playback()
        if not pb or not pb.get("item"):
            return None
        track = pb["item"]
        return {
            "track_name": track.get("name", ""),
            "artist_name": track["artists"][0]["name"] if track.get("artists") else "",
            "all_artists": [a["name"] for a in track.get("artists", [])],
            "album_name": track.get("album", {}).get("name", ""),
            "release_year": track.get("album", {}).get("release_date", "")[:4],
            "release_date": track.get("album", {}).get("release_date", ""),
            "duration_seconds": track.get("duration_ms", 0) // 1000,
            "progress_seconds": pb.get("progress_ms", 0) // 1000,
            "is_playing": pb.get("is_playing", False),
            "spotify_url": track.get("external_urls", {}).get("spotify", ""),
            "device_name": pb.get("device", {}).get("name", ""),
        }
    except Exception as e:
        print(f"[Spotify] get_current_track_info failed: {e}")
        return None


def find_and_queue_song_by_description(description: str) -> list:
    try:
        results = sp.search(q=description, type="track", limit=3)
        tracks = results.get("tracks", {}).get("items", [])
        return [
            {
                "track": t["name"],
                "artist": t["artists"][0]["name"] if t.get("artists") else "",
                "album": t.get("album", {}).get("name", ""),
                "uri": t.get("uri", ""),
            }
            for t in tracks
        ]
    except Exception as e:
        print(f"[Spotify] find_and_queue_song_by_description failed: {e}")
        return []


def play_playlist(playlist_name: str) -> dict:
    try:
        results = sp.current_user_playlists(limit=50)
        playlists = results.get("items", [])
        # Case-insensitive name match, fall back to closest partial match
        match = next(
            (p for p in playlists if p["name"].lower() == playlist_name.lower()),
            next(
                (p for p in playlists if playlist_name.lower() in p["name"].lower()),
                None
            )
        )
        if not match:
            names = [p["name"] for p in playlists]
            return {"error": f"Playlist '{playlist_name}' not found. Available: {names}"}
        sp.start_playback(context_uri=match["uri"])
        return {
            "playlist": match["name"],
            "track_count": match.get("tracks", {}).get("total", 0),
        }
    except Exception as e:
        print(f"[Spotify] play_playlist failed: {e}")
        return {"error": str(e)}


def search_spotify(query: str, type: str = "track", limit: int = 5) -> list:
    try:
        results = sp.search(q=query, type=type, limit=limit)
        if type == "track":
            items = results.get("tracks", {}).get("items", [])
            return [_track_dict(t) for t in items]
        elif type == "album":
            items = results.get("albums", {}).get("items", [])
            return [_album_dict(a) for a in items]
        elif type == "artist":
            items = results.get("artists", {}).get("items", [])
            return [
                {
                    "name": a.get("name", ""),
                    "uri": a.get("uri", ""),
                    "genres": a.get("genres", [])[:3],
                    "popularity": a.get("popularity"),
                }
                for a in items
            ]
        return []
    except Exception as e:
        print(f"[Spotify] search_spotify failed: {e}")
        return []


# ─────────────────────────────────────────────
# Tool schema definitions (OpenAI Realtime format)
# These are imported by tools.py and passed to the model.
# ─────────────────────────────────────────────

SPOTIFY_TOOLS = [
    {
        "type": "function",
        "name": "get_current_track_info",
        "description": (
            "Get full details about the currently playing track — name, artist, album, "
            "release year, progress, and device. Call this whenever the user asks anything "
            "about what's playing: 'who sings this', 'what album is this', 'what year is this from'."
        ),
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "type": "function",
        "name": "play_song",
        "description": "Search for a song and start playing it immediately.",
        "parameters": {
            "type": "object",
            "properties": {
                "song_name": {"type": "string", "description": "Name of the song."},
                "artist_name": {"type": "string", "description": "Artist name (optional but improves accuracy)."},
            },
            "required": ["song_name"],
        },
    },
    {
        "type": "function",
        "name": "queue_song",
        "description": "Search for a song and add it to the queue without interrupting what's playing.",
        "parameters": {
            "type": "object",
            "properties": {
                "song_name": {"type": "string", "description": "Name of the song."},
                "artist_name": {"type": "string", "description": "Artist name (optional)."},
            },
            "required": ["song_name"],
        },
    },
    {
        "type": "function",
        "name": "play_album",
        "description": "Search for an album and play it from the start.",
        "parameters": {
            "type": "object",
            "properties": {
                "album_name": {"type": "string", "description": "Name of the album."},
                "artist_name": {"type": "string", "description": "Artist name (optional)."},
            },
            "required": ["album_name"],
        },
    },
    {
        "type": "function",
        "name": "play_liked_songs_by_artist",
        "description": "Play all of the user's liked songs by a specific artist, shuffled.",
        "parameters": {
            "type": "object",
            "properties": {
                "artist_name": {"type": "string", "description": "Name of the artist to filter by."},
            },
            "required": ["artist_name"],
        },
    },
    {
        "type": "function",
        "name": "play_liked_songs_shuffled",
        "description": "Shuffle and play the user's liked songs library.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "type": "function",
        "name": "find_and_queue_song_by_description",
        "description": (
            "Search Spotify using a vague description and return the top 3 candidates. "
            "Use this when the user says something like 'that Radiohead song about paranoia' "
            "or 'the one that goes creep'. Returns candidates so you can pick the best match "
            "and then call play_song or queue_song."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "description": {"type": "string", "description": "Free-text description of the song."},
            },
            "required": ["description"],
        },
    },
    {
        "type": "function",
        "name": "search_spotify",
        "description": "General-purpose Spotify search. Use when none of the other tools fit.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query."},
                "type": {
                    "type": "string",
                    "enum": ["track", "album", "artist"],
                    "description": "Type of result to search for.",
                },
                "limit": {"type": "integer", "description": "Number of results (default 5)."},
            },
            "required": ["query"],
        },
    },
    {
        "type": "function",
        "name": "pause",
        "description": "Pause playback.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "type": "function",
        "name": "resume",
        "description": "Resume playback.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "type": "function",
        "name": "skip_next",
        "description": "Skip to the next track.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "type": "function",
        "name": "skip_previous",
        "description": "Go back to the previous track.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "type": "function",
        "name": "seek",
        "description": "Seek to a position in the current track.",
        "parameters": {
            "type": "object",
            "properties": {
                "seconds": {"type": "integer", "description": "Position in seconds from the start."},
            },
            "required": ["seconds"],
        },
    },
    {
        "type": "function",
        "name": "set_volume",
        "description": "Set the playback volume.",
        "parameters": {
            "type": "object",
            "properties": {
                "percent": {"type": "integer", "description": "Volume level from 0 to 100."},
            },
            "required": ["percent"],
        },
    },
    {
        "type": "function",
        "name": "set_shuffle",
        "description": "Enable or disable shuffle.",
        "parameters": {
            "type": "object",
            "properties": {
                "enabled": {"type": "boolean", "description": "True to enable, False to disable."},
            },
            "required": ["enabled"],
        },
    },
    {
        "type": "function",
        "name": "set_repeat",
        "description": "Set the repeat mode.",
        "parameters": {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["off", "track", "context"],
                    "description": "'off' = no repeat, 'track' = repeat current song, 'context' = repeat playlist/album.",
                },
            },
            "required": ["mode"],
        },
    },
    {
        "type": "function",
        "name": "get_queue",
        "description": "Get the current playback queue — what's playing and what's coming up.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "type": "function",
        "name": "get_available_devices",
        "description": "List the Spotify Connect devices available for playback.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "type": "function",
        "name": "get_user_playlists",
        "description": "List all of the user's Spotify playlists with their names and track counts.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "type": "function",
        "name": "play_playlist",
        "description": (
            "Play one of the user's playlists by name. "
            "If unsure of the exact name, call get_user_playlists first to see what's available."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "playlist_name": {"type": "string", "description": "The name of the playlist to play."},
            },
            "required": ["playlist_name"],
        },
    },
    {
        "type": "function",
        "name": "get_recently_played",
        "description": "Get the user's recently played tracks.",
        "parameters": {
            "type": "object",
            "properties": {
                "n": {"type": "integer", "description": "Number of tracks to return (default 10, max 50)."},
            },
            "required": [],
        },
    },
    {
        "type": "function",
        "name": "get_saved_tracks",
        "description": "Get tracks from the user's liked songs library.",
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Number of tracks to return (default 50)."},
                "offset": {"type": "integer", "description": "Offset for pagination (default 0)."},
            },
            "required": [],
        },
    },
    {
        "type": "function",
        "name": "get_saved_albums",
        "description": "Get albums saved in the user's library.",
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Number of albums to return (default 20)."},
            },
            "required": [],
        },
    },
    {
        "type": "function",
        "name": "get_playlist_items",
        "description": "Get the tracks inside a specific playlist by its Spotify playlist ID.",
        "parameters": {
            "type": "object",
            "properties": {
                "playlist_id": {"type": "string", "description": "The Spotify playlist ID (get this from get_user_playlists)."},
            },
            "required": ["playlist_id"],
        },
    },
    {
        "type": "function",
        "name": "get_artist_albums",
        "description": "Get all albums by an artist. Searches for the artist by name then returns their discography.",
        "parameters": {
            "type": "object",
            "properties": {
                "artist_name": {"type": "string", "description": "Name of the artist."},
            },
            "required": ["artist_name"],
        },
    },
    {
        "type": "function",
        "name": "transfer_playback",
        "description": "Transfer Spotify playback to a different device.",
        "parameters": {
            "type": "object",
            "properties": {
                "device_id": {"type": "string", "description": "The device ID to transfer to (get from get_available_devices)."},
                "force_play": {"type": "boolean", "description": "Whether to start playing immediately on the new device (default false)."},
            },
            "required": ["device_id"],
        },
    },
    {
        "type": "function",
        "name": "add_to_queue",
        "description": "Add a track URI directly to the playback queue.",
        "parameters": {
            "type": "object",
            "properties": {
                "track_uri": {"type": "string", "description": "Spotify track URI (e.g. spotify:track:...)."},
            },
            "required": ["track_uri"],
        },
    },
    {
        "type": "function",
        "name": "add_to_playlist",
        "description": "Add one or more tracks to a playlist.",
        "parameters": {
            "type": "object",
            "properties": {
                "playlist_id": {"type": "string", "description": "The Spotify playlist ID."},
                "track_uris": {"type": "array", "items": {"type": "string"}, "description": "List of Spotify track URIs to add."},
            },
            "required": ["playlist_id", "track_uris"],
        },
    },
    {
        "type": "function",
        "name": "remove_from_playlist",
        "description": "Remove one or more tracks from a playlist.",
        "parameters": {
            "type": "object",
            "properties": {
                "playlist_id": {"type": "string", "description": "The Spotify playlist ID."},
                "track_uris": {"type": "array", "items": {"type": "string"}, "description": "List of Spotify track URIs to remove."},
            },
            "required": ["playlist_id", "track_uris"],
        },
    },
]


# ─────────────────────────────────────────────
# Dispatcher
# ─────────────────────────────────────────────

SPOTIFY_REGISTRY = {
    "get_current_track_info":           lambda args: get_current_track_info(),
    "play_song":                        lambda args: play_song(args["song_name"], args.get("artist_name")),
    "queue_song":                       lambda args: queue_song(args["song_name"], args.get("artist_name")),
    "play_album":                       lambda args: play_album(args["album_name"], args.get("artist_name")),
    "play_liked_songs_by_artist":       lambda args: play_liked_songs_by_artist(args["artist_name"]),
    "play_liked_songs_shuffled":        lambda args: play_liked_songs_shuffled(),
    "find_and_queue_song_by_description": lambda args: find_and_queue_song_by_description(args["description"]),
    "search_spotify":                   lambda args: search_spotify(args["query"], args.get("type", "track"), args.get("limit", 5)),
    "pause":                            lambda args: pause(),
    "resume":                           lambda args: resume(),
    "skip_next":                        lambda args: skip_next(),
    "skip_previous":                    lambda args: skip_previous(),
    "seek":                             lambda args: seek(args["seconds"]),
    "set_volume":                       lambda args: set_volume(args["percent"]),
    "set_shuffle":                      lambda args: set_shuffle(args["enabled"]),
    "set_repeat":                       lambda args: set_repeat(args["mode"]),
    "get_queue":                        lambda args: get_queue(),
    "get_available_devices":            lambda args: get_available_devices(),
    "get_user_playlists":               lambda args: get_user_playlists(),
    "play_playlist":                    lambda args: play_playlist(args["playlist_name"]),
    "get_recently_played":              lambda args: get_recently_played(args.get("n", 10)),
    "get_saved_tracks":                 lambda args: get_saved_tracks(args.get("limit", 50), args.get("offset", 0)),
    "get_saved_albums":                 lambda args: get_saved_albums(args.get("limit", 20)),
    "get_playlist_items":               lambda args: get_playlist_items(args["playlist_id"]),
    "get_artist_albums":                lambda args: get_artist_albums(args["artist_name"]),
    "transfer_playback":                lambda args: transfer_playback(args["device_id"], args.get("force_play", False)),
    "add_to_queue":                     lambda args: add_to_queue(args["track_uri"]),
    "add_to_playlist":                  lambda args: add_to_playlist(args["playlist_id"], args["track_uris"]),
    "remove_from_playlist":             lambda args: remove_from_playlist(args["playlist_id"], args["track_uris"]),
}


def spotify_dispatch(name: str, args: dict) -> str:
    fn = SPOTIFY_REGISTRY.get(name)
    if fn is None:
        return f"Unknown Spotify tool: {name}"
    result = fn(args)
    return json.dumps(result) if result is not None else "null"
