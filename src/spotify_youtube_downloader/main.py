import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import re
import os
from dotenv import load_dotenv
import sys
import subprocess # To run yt-dlp
import string     # For filename sanitization
from urllib.parse import urlparse, parse_qs # Added parse_qs

# --- Configuration ---

load_dotenv()

# Spotify Credentials (Only needed if using Spotify URLs)
# Option 1: Environment Variables (Recommended)
client_id = os.getenv('SPOTIPY_CLIENT_ID')
client_secret = os.getenv('SPOTIPY_CLIENT_SECRET')

# --- Constants ---
TRACKING_FILE = "downloaded_media.log" # Renamed for clarity (stores Spotify IDs or YT Video IDs)
YT_DLP_EXECUTABLE = 'yt-dlp' # Assumes yt-dlp is in PATH

# --- Helper Functions ---

def get_id_and_type_from_url(url):
    """Extracts the ID/URL and type (spotify_playlist, spotify_show, youtube_playlist) from a URL."""
    parsed_url = urlparse(url)
    netloc = parsed_url.netloc.lower()
    path_parts = [part for part in parsed_url.path.split('/') if part]

    # Spotify Check
    if netloc in ["open.spotify.com", "spotify.com"]:
        try:
            if 'playlist' in path_parts:
                id_index = path_parts.index('playlist') + 1
                if id_index < len(path_parts): return path_parts[id_index], 'spotify_playlist'
            elif 'show' in path_parts:
                id_index = path_parts.index('show') + 1
                if id_index < len(path_parts): return path_parts[id_index], 'spotify_show'
        except (ValueError, IndexError): pass # Ignore if path structure is unexpected

    # YouTube Playlist Check
    elif netloc in ["www.youtube.com", "youtube.com", "m.youtube.com", "music.youtube.com"]:
        query_params = parse_qs(parsed_url.query)
        if 'list' in query_params and query_params['list']:
             # Return the original URL as the 'ID' for YT playlists
            return url, 'youtube_playlist'
        # Add check for /playlist/ path structure? Less common but possible
        # elif 'playlist' in path_parts: ... logic to extract ID ... return id, 'youtube_playlist'

    # youtu.be links might also contain playlists, but require more complex checking
    # For now, focusing on standard youtube.com playlist URLs

    return None, None # Type not recognized or invalid format

def find_youtube_links(text):
    """Finds all YouTube links in a given string using regex."""
    if not text: return []
    # Regex finds youtube.com watch/embed links and youtu.be links
    regex = r'(https?://(?:www\.)?(?:youtube\.com/(?:watch\?v=|embed/)|youtu\.be/)[\w-]+(?:\?[^\s<]*)?)'
    return re.findall(regex, text)

# --- Spotify Fetching Functions --- (Remain largely unchanged)
def fetch_episodes_from_playlist(sp, playlist_id):
    episodes = []
    offset, limit = 0, 50
    print(f"\nFetching episodes from Spotify playlist ID: {playlist_id}")
    while True:
        try:
            results = sp.playlist_items(playlist_id, fields='items(track(name, id, type, description, episode)), next', additional_types=['episode'], limit=limit, offset=offset)
            if not results or 'items' not in results: break
            items = results.get('items', [])
            if not items: break
            fetched_count = 0
            for item in items:
                track_info = item.get('track')
                if track_info and track_info.get('type') == 'episode':
                    episodes.append({'name': track_info.get('name', 'Unknown Episode'), 'id': track_info.get('id', 'Unknown ID'), 'description': track_info.get('description', '')})
                    fetched_count += 1
            print(f"  Fetched {fetched_count} Spotify episodes (offset {offset}). Total: {len(episodes)}")
            offset += len(items)
            if results.get('next') is None: break
        except spotipy.SpotifyException as e: print(f"Spotify API Error: {e}"); return None
        except Exception as e: print(f"Unexpected error fetching Spotify playlist: {e}"); return None
    print(f"Finished fetching playlist. Total Spotify episodes: {len(episodes)}")
    return episodes

def fetch_episodes_from_show(sp, show_id):
    episodes = []
    offset, limit = 0, 50
    print(f"\nFetching episodes from Spotify show ID: {show_id}")
    while True:
        try:
            results = sp.show_episodes(show_id, limit=limit, offset=offset)
            if not results or 'items' not in results: break
            items = results.get('items', [])
            if not items: break
            for item in items: episodes.append({'name': item.get('name', 'Unknown Episode'), 'id': item.get('id', 'Unknown ID'), 'description': item.get('description', '')})
            print(f"  Fetched {len(items)} Spotify episodes (offset {offset}). Total: {len(episodes)}")
            offset += len(items)
            if results.get('next') is None: break
        except spotipy.SpotifyException as e: print(f"Spotify API Error: {e}"); return None
        except Exception as e: print(f"Unexpected error fetching Spotify show: {e}"); return None
    print(f"Finished fetching show. Total Spotify episodes: {len(episodes)}")
    return episodes

# --- YouTube Playlist Fetching Function ---
def fetch_youtube_playlist_items(playlist_url):
    """Fetches Video ID, Title, and URL for items in a YouTube playlist using yt-dlp."""
    print(f"\nFetching video list from YouTube playlist: {playlist_url}")
    items = []
    # Command to get info without downloading, one line per video: ID;Title;URL
    command = [
        YT_DLP_EXECUTABLE,
        '--flat-playlist',        # Don't extract videos from nested playlists
        '--print', '%(id)s;%(title)s;%(webpage_url)s', # Print fields separated by ';'
        playlist_url
    ]
    print(f"  Running: {' '.join(command)}") # Show the command being run

    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False, encoding='utf-8')

        if result.returncode != 0:
            print(f"\nERROR: yt-dlp failed to get playlist info (Exit Code: {result.returncode}).")
            print("--- yt-dlp Error Output ---")
            print(result.stderr or "No stderr captured.")
            print("---------------------------")
            return None # Indicate failure

        if not result.stdout:
            print("  Warning: yt-dlp returned no output for this playlist.")
            return [] # Return empty list, maybe playlist is empty or private

        # Process the output
        lines = result.stdout.strip().split('\n')
        for line in lines:
            parts = line.split(';', 2) # Split only twice on ';'
            if len(parts) == 3:
                video_id, title, video_url = parts
                items.append({
                    # Use youtube video url as the 'link' to download
                    'link': video_url.strip(),
                    # Use youtube title as the 'name'
                    'episode_name': title.strip(),
                    # Use youtube video id as the 'id' for tracking
                    'episode_id': video_id.strip()
                })
            else:
                print(f"  Warning: Skipping malformed line from yt-dlp output: {line}")

        print(f"  Successfully fetched info for {len(items)} videos from the playlist.")
        return items

    except FileNotFoundError:
        print(f"\nERROR: '{YT_DLP_EXECUTABLE}' command not found.")
        print("Please ensure yt-dlp is installed and in your system's PATH.")
        return None # Indicate yt-dlp missing
    except Exception as e:
        print(f"\nAn unexpected error occurred while fetching YouTube playlist items: {e}")
        return None

# --- Download & Tracking Helpers --- (Remain largely unchanged)
def sanitize_filename(name):
    """Removes or replaces characters illegal in filenames."""
    # Allow alphanumeric, spaces, hyphens, underscores, periods. Replace others.
    # Limit length and handle potential edge cases.
    name = re.sub(r'[^\w\s\-\.]', '_', name) # Replace illegal chars with underscore
    name = re.sub(r'\s+', ' ', name).strip() # Consolidate whitespace
    return name[:150] if name else "Untitled" # Limit length and provide default

def load_downloaded_ids(tracking_file):
    """Loads already downloaded IDs (Spotify or YouTube) from the tracking file."""
    downloaded = set()
    try:
        with open(tracking_file, 'r', encoding='utf-8') as f:
            for line in f:
                clean_id = line.strip()
                if clean_id: downloaded.add(clean_id)
        print(f"\nLoaded {len(downloaded)} previously downloaded IDs from {tracking_file}.")
    except FileNotFoundError: print(f"\nTracking file '{tracking_file}' not found. Starting fresh.")
    except Exception as e: print(f"\nError reading tracking file {tracking_file}: {e}")
    return downloaded

def log_downloaded_id(tracking_file, item_id):
    """Appends a successfully downloaded ID (Spotify or YouTube) to the tracking file."""
    try:
        with open(tracking_file, 'a', encoding='utf-8') as f:
            f.write(item_id + '\n')
    except Exception as e: print(f"Error writing ID {item_id} to tracking file {tracking_file}: {e}")

def run_yt_dlp_command(command_list):
    """Runs a yt-dlp command using subprocess and returns the result object."""
    # print(f"  DEBUG: Running command: {' '.join(command_list)}")
    try:
        result = subprocess.run(command_list, capture_output=True, text=True, check=False, encoding='utf-8')
        return result
    except FileNotFoundError: print(f"\nERROR: '{YT_DLP_EXECUTABLE}' command not found."); return None
    except Exception as e: print(f"  Error running subprocess: {e}"); return None

# --- Main Execution ---

def run():
    """
    Main function to handle URL input, fetching, task generation, and downloading.
    """

    # 1. Get URL from User
    input_url = input("Enter the Spotify Playlist/Show URL or YouTube Playlist URL: ")
    item_id, item_type = get_id_and_type_from_url(input_url)

    if not item_type:
        print(f"\nERROR: Could not recognize URL type or invalid URL: {input_url}"); sys.exit(1)
    print(f"\nDetected Type: {item_type.replace('_', ' ').title()}")
    # For YT Playlists, item_id holds the URL, otherwise it's the Spotify ID
    if item_type != 'youtube_playlist': print(f"Detected ID: {item_id}")

    # 2. Initialize Spotify client only if needed
    sp = None
    if item_type.startswith('spotify_'):
        if not client_id or not client_secret or \
           client_id == 'YOUR_SPOTIFY_CLIENT_ID' or client_secret == 'YOUR_SPOTIFY_CLIENT_SECRET':
            print("\nERROR: Spotify Client ID/Secret not set (needed for Spotify URLs)."); sys.exit(1)
        try:
            auth_manager = SpotifyClientCredentials(client_id=client_id, client_secret=client_secret)
            sp = spotipy.Spotify(auth_manager=auth_manager)
            print("Successfully authenticated with Spotify API.")
        except Exception as e: print(f"ERROR: Spotify Auth Failed: {e}"); sys.exit(1)

    # 3. Prepare Download Tasks based on input type
    download_tasks = []
    source_episodes = [] # List to hold Spotify episodes if applicable

    if item_type == 'spotify_playlist':
        source_episodes = fetch_episodes_from_playlist(sp, item_id)
    elif item_type == 'spotify_show':
        source_episodes = fetch_episodes_from_show(sp, item_id)
    elif item_type == 'youtube_playlist':
        # Fetch YT playlist items directly into download_tasks format
        youtube_items = fetch_youtube_playlist_items(item_id) # item_id is the URL here
        if youtube_items is None: print("Failed to fetch YouTube playlist items. Exiting."); sys.exit(1)
        download_tasks = youtube_items # Assign directly

    # If source was Spotify, now extract links and create tasks
    if item_type.startswith('spotify_'):
        if source_episodes is None: print("Failed to fetch Spotify episodes. Exiting."); sys.exit(1)
        if not source_episodes: print("No episodes found in the Spotify source."); sys.exit(0)

        print("\n--- Scanning Spotify Episode Descriptions for YouTube Links ---")
        unique_links_found = set()
        for episode in source_episodes:
            if not episode['description']: continue
            youtube_links = find_youtube_links(episode['description'])
            if youtube_links:
                print(f"  Found {len(youtube_links)} link(s) in: {episode['name']} (ID: {episode['id']})")
                for link in youtube_links:
                    clean_link = link.strip()
                    if clean_link and clean_link not in unique_links_found:
                        download_tasks.append({
                            'link': clean_link,
                            'episode_name': episode['name'],
                            'episode_id': episode['id'] # Spotify ID for tracking
                        })
                        unique_links_found.add(clean_link)
        if not download_tasks: print("\nNo YouTube links found in any Spotify episode descriptions."); sys.exit(0)
        print(f"\n--- Found {len(unique_links_found)} unique YouTube links to process from Spotify descriptions ---")


    # 4. Check if there are any tasks to process
    if not download_tasks:
        print("\nNo download tasks generated. Nothing to do.")
        sys.exit(0)
    print(f"\n--- Total download tasks generated: {len(download_tasks)} ---")

    # 5. Download Audio using yt-dlp with Tracking
    print(f"\n--- Starting Downloads (Tracking via '{TRACKING_FILE}') ---")
    downloaded_ids = load_downloaded_ids(TRACKING_FILE)
    success_count, skipped_count, failed_count = 0, 0, 0
    yt_dlp_missing_error = False

    for i, task in enumerate(download_tasks):
        link = task['link']
        # Use 'name' if input was Spotify, 'episode_name' if YT playlist (already mapped)
        item_name = task.get('episode_name', task.get('name', 'Unknown Item'))
        # Use 'id' if input was Spotify, 'episode_id' if YT playlist (already mapped)
        tracking_id = task.get('episode_id', task.get('id', 'UnknownID'))

        print(f"\n[{i+1}/{len(download_tasks)}] Processing Task:")
        print(f"  Name: {item_name}")
        print(f"  ID (for tracking): {tracking_id}")
        print(f"  Source Link: {link}")

        if tracking_id == 'UnknownID':
             print("  WARNING: Cannot track item without a valid ID. Skipping download attempt.")
             failed_count += 1
             continue

        if tracking_id in downloaded_ids:
            print("  Status: SKIPPED (ID already in tracking file)")
            skipped_count += 1
            continue

        # Sanitize name for filename
        sanitized_name = sanitize_filename(item_name)

        # Output template: YYYYMMDD - Sanitized Name [TrackingID].<ext>
        # Using %(upload_date)s for date consistency across sources if available
        output_template = f"%(upload_date)s - {sanitized_name} [{tracking_id}].%(ext)s"
        print(f"  Output Pattern: {output_template}")

        # --- Download Attempts ---
        download_successful = False

        # Command 1: Standard
        cmd1 = [YT_DLP_EXECUTABLE, '-x', '--audio-format', 'mp3', '--audio-quality', '0', '-o', output_template, link]
        print(f"  Attempt 1: Standard Download...")
        result1 = run_yt_dlp_command(cmd1)
        if result1 is None: yt_dlp_missing_error = True; break # Stop if yt-dlp not found
        if result1.returncode == 0:
            print("  Status: SUCCESS (Standard)")
            download_successful = True
        else:
            print(f"  Attempt 1 Failed (Exit Code: {result1.returncode}).")
            # print(f"  Stderr: {result1.stderr[:500]}...") # Optionally show partial errors

            # Command 2: With Firefox Cookies
            cmd2 = [YT_DLP_EXECUTABLE, '--cookies-from-browser', 'firefox', '-x', '--audio-format', 'mp3', '--audio-quality', '0', '-o', output_template, link]
            print(f"  Attempt 2: Trying with Firefox cookies...")
            result2 = run_yt_dlp_command(cmd2)
            if result2 is None: yt_dlp_missing_error = True; break # Stop if yt-dlp not found
            if result2.returncode == 0:
                print("  Status: SUCCESS (with Firefox Cookies)")
                download_successful = True
            else:
                print(f"  Attempt 2 Failed (Exit Code: {result2.returncode}).")
                # print(f"  Stderr: {result2.stderr[:500]}...") # Optionally show partial errors

        # --- Update Tracking ---
        if download_successful:
            log_downloaded_id(TRACKING_FILE, tracking_id)
            downloaded_ids.add(tracking_id) # Update in-memory set for this run
            success_count += 1
        else:
            print(f"  Status: FAILED (Both attempts failed for link: {link})")
            failed_count += 1

        # End loop if yt-dlp was missing
        if yt_dlp_missing_error: break


    # --- Summary ---
    print("\n--- Run Summary ---")
    if yt_dlp_missing_error: print("Processing stopped: 'yt-dlp' command not found.")
    print(f"Successfully downloaded: {success_count}")
    print(f"Skipped (already downloaded): {skipped_count}")
    print(f"Failed downloads: {failed_count}")
    print(f"Total tasks processed/attempted: {success_count + skipped_count + failed_count}")

    print("\nScript finished.")

if __name__ == "__main__":
    run()
