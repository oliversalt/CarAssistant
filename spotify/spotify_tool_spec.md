# Spotify Tools — Claude Code Instructions

## What to build

Create a file called `spotify_tools.py` in the root of the CarPi project.

This file is the complete Spotify integration layer for CarPi — a voice-activated car
assistant running on a Raspberry Pi 4B. The main pipeline takes voice input, transcribes
it with Whisper, sends it to Claude, and Claude calls tools from this file to control
Spotify on the user's phone via Spotify Connect.

The file should contain two types of tools:

1. **Raw endpoint wrappers** — thin wrappers around individual Spotify API calls.
   Claude can call these directly for simple tasks.

2. **Composite tools** — functions that combine multiple API calls to accomplish
   something meaningful from a single voice command. These are what Claude will
   call most of the time.

---

## Auth & setup

Use `spotipy` with `SpotifyOAuth`. Load credentials from `.env` using `python-dotenv`.

Required scopes:
```
user-read-playback-state
user-modify-playback-state
user-read-currently-playing
user-read-private
user-library-read
user-read-recently-played
playlist-read-private
playlist-read-collaborative
playlist-modify-public
playlist-modify-private
```

Cache the token to `.spotify_cache`.

Create a single `sp` instance at module level so all functions share it.

Also create a helper `get_active_device_id()` that returns the active device ID,
falling back to the first available device if none is active. Many playback commands
need this.

---

## Tested endpoints

The following endpoints have been confirmed working on this Spotify account.
Only implement tools that use these. Do NOT implement tools that require
Get Artist, Get Playlist metadata, or Get Track by ID — these return 403 on
this account (family plan restriction).

### Albums
- Get Album (`sp.album`)
- Get Album Tracks (`sp.album_tracks`)
- Get User's Saved Albums (`sp.current_user_saved_albums`)

### Artists
- Get Artist's Albums (`sp.artist_albums`) ← note: Get Artist itself is blocked

### Player
- Get Playback State (`sp.current_playback`)
- Transfer Playback (`sp.transfer_playback`)
- Get Available Devices (`sp.devices`)
- Get Currently Playing Track (`sp.currently_playing`)
- Start/Resume Playback (`sp.start_playback`)
- Pause Playback (`sp.pause_playback`)
- Skip To Next (`sp.next_track`)
- Skip To Previous (`sp.previous_track`)
- Seek To Position (`sp.seek_track`) — takes milliseconds
- Set Repeat Mode (`sp.repeat`) — values: "off", "track", "context"
- Toggle Shuffle (`sp.shuffle`)
- Get Recently Played (`sp.current_user_recently_played`)
- Get Queue (`sp.queue`)
- Add Item to Queue (`sp.add_to_queue`)

### Playlists
- Get Current User's Playlists (`sp.current_user_playlists`)
- Get Playlist Items (`sp.playlist_items`)
- Add Items to Playlist (`sp.playlist_add_items`)
- Remove Playlist Items (`sp.playlist_remove_all_occurrences_of_items`)
- Get Playlist Cover Image (`sp.playlist_cover_image`)

### Search
- Search (`sp.search`) — supports type: "track", "album", "artist"

### Tracks
- Get User's Saved Tracks (`sp.current_user_saved_tracks`)

---

## Raw endpoint wrappers to implement

These are thin wrappers — minimal logic, just call the Spotify API and return
clean structured data. Each should handle exceptions and return None or [] on failure
rather than raising, so the pipeline never crashes on a Spotify error.

```
get_playback_state()        → dict with track, artist, album, is_playing, device, progress_ms, duration_ms
get_currently_playing()     → same as above, or None if nothing playing
get_available_devices()     → list of dicts: {id, name, type, is_active, volume_percent}
get_queue()                 → dict: {currently_playing: track_dict, queue: [track_dict, ...]}
get_recently_played(n=10)   → list of track dicts (most recent first)
get_saved_tracks(limit=50, offset=0) → list of track dicts
get_saved_albums(limit=20)  → list of album dicts
get_user_playlists()        → list of dicts: {id, name, track_count, owner}
get_playlist_items(playlist_id) → list of track dicts
get_artist_albums(artist_name)  → search for artist, then return list of album dicts

pause()                     → None
resume()                    → None
skip_next()                 → None
skip_previous()             → None
seek(seconds)               → None (converts to ms internally)
set_volume(percent)         → None (0–100)
set_shuffle(enabled: bool)  → None
set_repeat(mode: str)       → None ("off", "track", "context")
transfer_playback(device_id, force_play=False) → None

add_to_queue(track_uri)     → None
add_to_playlist(playlist_id, track_uris: list) → None
remove_from_playlist(playlist_id, track_uris: list) → None
```

---

## Composite tools to implement

These are the high-level tools Claude calls in response to voice commands.
Each should handle the full flow internally — searching, resolving IDs, checking
devices, starting playback — so Claude just passes natural language arguments.

---

### `play_song(song_name, artist_name=None)`
1. Search Spotify for the track (include artist in query if provided)
2. Get the best match
3. Start playback with that track URI
4. Return dict: {track, artist, album}

---

### `queue_song(song_name, artist_name=None)`
1. Search for the track
2. Add it to the queue (not start playback)
3. Return dict: {track, artist}

---

### `play_album(album_name, artist_name=None)`
1. Search for the album
2. Start playback with album context_uri (plays from track 1)
3. Return dict: {album, artist, total_tracks}


---

### `play_liked_songs_by_artist(artist_name)`
1. Page through the user's saved tracks (handle pagination — fetch all, not just 50)
2. Filter to tracks where artist name matches (case-insensitive)
3. If none found, return an error message string so Claude can tell the user
4. Shuffle the list
5. Start playback with those URIs
6. Return dict: {artist, track_count, now_playing}

---

### `play_liked_songs_shuffled()`
1. Fetch up to 200 liked songs
2. Shuffle them
3. Start playback with the URIs
4. Return dict: {track_count, now_playing}

---

### `get_current_track_info()`
This is the most important composite tool. Claude calls this whenever the user
asks anything about the current song — "who sings this", "what album is this from",
"what year was this released", etc.

Return a rich dict:
```python
{
    "track_name": str,
    "artist_name": str,
    "all_artists": list,
    "album_name": str,
    "release_year": str,
    "release_date": str,
    "duration_seconds": int,
    "progress_seconds": int,
    "is_playing": bool,
    "spotify_url": str,
    "device_name": str,
}
```

Claude then uses its own knowledge or web search to answer follow-up questions
like "where was the artist born" — this function just provides the context.

---

### `find_and_queue_song_by_description(description)`
This is the vague song lookup tool — for when the user says something like
"queue that Radiohead song about paranoia" or "play the one that goes like
something about a creep".

1. Accept a free-text description
2. Search Spotify with the description as a query (type="track")
3. Return the top 3 results as a list of dicts: {track, artist, album, uri}
   so Claude can pick the best match and then call queue_song or play_song with it.

Claude handles the "which one did they mean" logic — this function just does
the Spotify search and returns candidates.

---

### `search_spotify(query, type="track", limit=5)`
General-purpose search. Returns structured results.
Claude can call this directly if none of the above composites fit.
Supports type: "track", "album", "artist"

---

## Error handling

Every function should:
- Catch all exceptions
- Never raise — return None, [], or a dict with an `"error"` key
- Print a brief error to console for debugging

Example pattern:
```python
def pause():
    try:
        sp.pause_playback()
    except Exception as e:
        print(f"[Spotify] pause failed: {e}")
```

---

## Return format consistency

All track dicts returned by any function should use this consistent shape
so Claude always knows what fields to expect:
```python
{
    "name": str,
    "artist": str,
    "album": str,
    "uri": str,
    "duration_seconds": int,
}
```

All album dicts:
```python
{
    "name": str,
    "artist": str,
    "uri": str,
    "total_tracks": int,
    "release_date": str,
}
```

---

## What NOT to include

- No playlist creation (blocked by Spotify family plan account restriction)
- No Get Artist endpoint (blocked — use artist search + artist_albums instead)
- No Get Track by ID (blocked — use search instead)
- No Web Playback SDK (CarPi uses Spotify Connect to control the user's phone,
  not stream audio through the Pi)
- No lyrics fetching (not in Spotify API — Claude uses its own knowledge)

---

## Testing

After writing the file, create a brief `test_spotify_tools.py` that imports
`spotify_tools` and calls each composite tool with hardcoded test values
to verify they work end to end. Use Radiohead as the test artist and
"OK Computer" as the test album.