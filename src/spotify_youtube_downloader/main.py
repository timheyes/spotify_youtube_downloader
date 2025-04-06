import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import re
import os
import sys
import subprocess
import string
import argparse
from urllib.parse import urlparse, parse_qs
from dotenv import load_dotenv

# Load environment variables from .env file, if it exists
load_dotenv()

# --- Configuration ---
client_id = os.getenv('SPOTIPY_CLIENT_ID')
client_secret = os.getenv('SPOTIPY_CLIENT_SECRET')

# --- Constants ---
# YT_DLP_EXECUTABLE = 'yt-dlp' # Defined within run() now based on args if needed

# --- Helper Functions ---

def get_id_and_type_from_url(url):
    """Extracts the ID/URL and type (spotify_playlist, spotify_show, youtube_playlist) from a URL."""
    parsed_url = urlparse(url)
    netloc = parsed_url.netloc.lower()
    path_parts = [part for part in parsed_url.path.split('/') if part]

    # Spotify Check
    if netloc in ["open.spotify.com", "spotify.link"]:
        try:
            # Prioritize specific types if multiple keywords exist (e.g., playlist over track in path)
            if 'playlist' in path_parts:
                id_index = path_parts.index('playlist') + 1
                if id_index < len(path_parts): return path_parts[id_index].split('?')[0], 'spotify_playlist'
            elif 'show' in path_parts:
                id_index = path_parts.index('show') + 1
                if id_index < len(path_parts): return path_parts[id_index].split('?')[0], 'spotify_show'
            elif 'episode' in path_parts: # Can add handling for single episodes later if needed
                 id_index = path_parts.index('episode') + 1
                 if id_index < len(path_parts): return path_parts[id_index].split('?')[0], 'spotify_episode' # Example type
                 pass
        except (ValueError, IndexError): pass

    # YouTube Playlist Check
    elif netloc in ["www.youtube.com", "youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"]:
        query_params = parse_qs(parsed_url.query)
        if 'list' in query_params and query_params['list']:
            return url, 'youtube_playlist'

    return None, None

def find_youtube_links(text):
    """Finds all YouTube links in a given string using regex."""
    if not text: return []
    regex = r'(https?://(?:www\.)?(?:youtube\.com/(?:watch\?v=|embed/)|youtu\.be/)[\w-]+(?:\?[^\s<]*)?)'
    return re.findall(regex, text)

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
    """Fetches episodes from Spotify show."""
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

def fetch_youtube_playlist_items(playlist_url, yt_dlp_executable):
    """Fetches Video ID, Title, and URL for items in a YouTube playlist using yt-dlp."""
    print(f"\nFetching video list from YouTube playlist: {playlist_url}")
    items = []
    command = [yt_dlp_executable, '--flat-playlist', '--print', '%(id)s;%(title)s;%(webpage_url)s', playlist_url]
    print(f"  Running: {' '.join(command)}")
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False, encoding='utf-8')
        if result.returncode != 0: print(f"\nERROR: yt-dlp failed (Exit Code: {result.returncode}).\nStderr: {result.stderr}"); return None
        if not result.stdout: return []
        lines = result.stdout.strip().split('\n')
        for line in lines:
            parts = line.split(';', 2)
            if len(parts) == 3: items.append({'link': parts[2].strip(), 'episode_name': parts[1].strip(), 'episode_id': parts[0].strip()})
            else: print(f"  Warning: Skipping malformed line: {line}")
        print(f"  Successfully fetched info for {len(items)} videos.")
        return items
    except FileNotFoundError: print(f"\nERROR: '{yt_dlp_executable}' not found."); return None
    except Exception as e: print(f"\nUnexpected error fetching YT playlist: {e}"); return None

# --- Download & Tracking Helpers ---
def sanitize_filename(name):
    """Removes or replaces characters illegal in filenames."""
    # Allow alphanumeric, spaces, hyphens, underscores, periods. Replace others.
    # Limit length and handle potential edge cases.
    name = re.sub(r'[^\w\s\-\.]', '_', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name[:150] if name else "Untitled"

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

def run_yt_dlp_command(command_list, yt_dlp_executable):
    # Ensure first element is the correct executable path if needed
    if command_list[0] != yt_dlp_executable:
        command_list.insert(0, yt_dlp_executable)

    # print(f"  DEBUG: Running command: {' '.join(command_list)}") # Uncomment for debug
    try:
        result = subprocess.run(command_list, capture_output=True, text=True, check=False, encoding='utf-8')
        return result
    except FileNotFoundError: print(f"\nERROR: '{yt_dlp_executable}' command not found."); return None
    except Exception as e: print(f"  Error running subprocess: {e}"); return None

def build_yt_dlp_command(link, output_template_path, download_format, use_cookies=False):
    """Builds the yt-dlp command list based on user choices."""
    # Base command starts with executable placeholder, link added later
    # We will prepend the actual executable path in run_yt_dlp_command if needed
    base_command = ['yt-dlp'] # Placeholder

    # Add cookie option if needed
    if use_cookies:
        base_command.extend(['--cookies-from-browser', 'firefox'])

    # Add format-specific options
    if download_format == 'audio':
        base_command.extend([
            '-x',                     # Extract audio
            '--audio-format', 'mp3',  # Specify audio format
            '--audio-quality', '0',   # Best audio quality
        ])
    elif download_format == 'video':
        base_command.extend([
            # Example format selector: best mp4 video + best m4a audio, fallback to best mp4, fallback to best overall
            '-f', 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            '--merge-output-format', 'mp4', # Prefer MP4 container if merging occurs
        ])
    else:
        # Default or fallback (shouldn't happen with argparse choices)
         print(f"Warning: Unknown download format '{download_format}', defaulting to audio.")
         base_command.extend(['-x', '--audio-format', 'mp3', '--audio-quality', '0'])


    # Add output template and the link URL
    base_command.extend(['-o', output_template_path, link])

    return base_command


# --- Argument Parser Setup ---

def setup_arg_parser():
    """Sets up the argparse parser."""
    parser = argparse.ArgumentParser(
        description="Download media (audio/video) from Spotify playlists/shows or YouTube playlists.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter # Shows default values in help
    )
    parser.add_argument(
        "url",
        nargs='?', # Makes the URL optional
        help="The URL of the Spotify Playlist/Show or YouTube Playlist."
    )
    parser.add_argument(
        "-o", "--output",
        default=".", # Default to current directory
        help="Path to the directory where downloads and log file will be saved."
    )
    parser.add_argument(
        "-f", "--format",
        choices=['audio', 'video'],
        default='audio',
        help="Download format: 'audio' (mp3) or 'video' (best mp4)."
    )
    parser.add_argument(
        "--yt-dlp-path",
        default="yt-dlp", # Default assumes yt-dlp is in PATH
        help="Path to the yt-dlp executable if not in system PATH."
    )
    return parser

# --- Main Application Logic ---

def run():
    """
    Main function to handle arguments, setup, fetching, task generation, and downloading.
    """
    parser = setup_arg_parser()
    args = parser.parse_args()

    # === Step 1: Get URL (from args or prompt) ===
    input_url = args.url
    if not input_url:
        input_url = input("Enter the Spotify Playlist/Show URL or YouTube Playlist URL: ")

    item_id, item_type = get_id_and_type_from_url(input_url)

    if not item_type:
        print(f"\nERROR: Could not recognize URL type or invalid URL: {input_url}")
        sys.exit(1)
    print(f"\nDetected Type: {item_type.replace('_', ' ').title()}")
    if item_type != 'youtube_playlist': print(f"Detected ID: {item_id}")

    # === Step 1.5: Prepare Output Directory and Paths ===
    output_dir = args.output
    tracking_file_name = "downloaded_media.log"
    tracking_file_path = os.path.join(output_dir, tracking_file_name)
    yt_dlp_executable = args.yt_dlp_path # Use provided path or default 'yt-dlp'

    try:
        os.makedirs(output_dir, exist_ok=True)
        print(f"Using output directory: {os.path.abspath(output_dir)}")
    except OSError as e:
        print(f"ERROR: Could not create output directory '{output_dir}': {e}")
        sys.exit(1)

    # === Step 2: Initialize Spotify client only if needed ===
    sp = None
    if item_type.startswith('spotify_'):
        if not client_id or not client_secret:
            print("\nERROR: Spotify Client ID/Secret not found. Set via .env or environment variables.")
            sys.exit(1)
        try:
            auth_manager = SpotifyClientCredentials(client_id=client_id, client_secret=client_secret)
            sp = spotipy.Spotify(auth_manager=auth_manager)
            print("Successfully authenticated with Spotify API.")
        except Exception as e: print(f"ERROR: Spotify Auth Failed: {e}"); sys.exit(1)

    # === Step 3: Prepare Download Tasks ===
    download_tasks = []
    source_episodes = []
    print(f"\nPreparing download tasks (Format: {args.format})...")

    if item_type == 'spotify_playlist': source_episodes = fetch_episodes_from_playlist(sp, item_id)
    elif item_type == 'spotify_show': source_episodes = fetch_episodes_from_show(sp, item_id)
    elif item_type == 'youtube_playlist':
        youtube_items = fetch_youtube_playlist_items(item_id, yt_dlp_executable) # item_id is URL here
        if youtube_items is None: print("Failed to fetch YouTube playlist items. Exiting."); sys.exit(1)
        download_tasks = youtube_items

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
                        download_tasks.append({'link': clean_link, 'episode_name': episode['name'], 'episode_id': episode['id']})
                        unique_links_found.add(clean_link)
        if not download_tasks and not item_type == 'youtube_playlist': print("\nNo YouTube links found in Spotify descriptions."); sys.exit(0)
        if unique_links_found: print(f"\n--- Found {len(unique_links_found)} unique YouTube links from Spotify descriptions ---")

    # === Step 4: Check Tasks ===
    if not download_tasks: print("\nNo download tasks generated. Nothing to do."); sys.exit(0)
    print(f"\n--- Total download tasks generated: {len(download_tasks)} ---")

    # === Step 5: Download Media ===
    print(f"\n--- Starting Downloads to '{os.path.abspath(output_dir)}' (Tracking via '{tracking_file_path}') ---")
    downloaded_ids = load_downloaded_ids(tracking_file_path) # Use full path
    success_count, skipped_count, failed_count = 0, 0, 0
    yt_dlp_missing_error = False

    for i, task in enumerate(download_tasks):
        link = task['link']
        item_name = task.get('episode_name', 'Unknown Item')
        tracking_id = task.get('episode_id', 'UnknownID')

        print(f"\n[{i+1}/{len(download_tasks)}] Processing Task:")
        print(f"  Name: {item_name}")
        print(f"  ID (for tracking): {tracking_id}")
        print(f"  Source Link: {link}")

        if tracking_id == 'UnknownID': print("  WARNING: Skipping item - cannot track without a valid ID."); failed_count += 1; continue
        if tracking_id in downloaded_ids: print("  Status: SKIPPED (ID already in tracking file)"); skipped_count += 1; continue

        # Construct output template *relative* to output dir
        sanitized_name = sanitize_filename(item_name)
        # Filename pattern - yt-dlp handles the extension based on format
        base_filename_pattern = f"%(upload_date)s - {sanitized_name} [{tracking_id}].%(ext)s"
        # Full path for yt-dlp's -o argument
        full_output_template = os.path.join(output_dir, base_filename_pattern)
        print(f"  Output Pattern: {full_output_template}")

        # --- Download Attempts ---
        download_successful = False
        # Attempt 1: Standard
        cmd1 = build_yt_dlp_command(link, full_output_template, args.format, use_cookies=False)
        print(f"  Attempt 1: Standard Download ({args.format})...")
        result1 = run_yt_dlp_command(cmd1, yt_dlp_executable)
        if result1 is None: yt_dlp_missing_error = True; break

        if result1.returncode == 0:
            print("  Status: SUCCESS (Standard)")
            download_successful = True
        else:
            print(f"  Attempt 1 Failed (Exit Code: {result1.returncode}).")
            # Attempt 2: With Cookies
            cmd2 = build_yt_dlp_command(link, full_output_template, args.format, use_cookies=True)
            print(f"  Attempt 2: Trying with Firefox cookies ({args.format})...")
            result2 = run_yt_dlp_command(cmd2, yt_dlp_executable)
            if result2 is None: yt_dlp_missing_error = True; break
            if result2.returncode == 0:
                print("  Status: SUCCESS (with Firefox Cookies)")
                download_successful = True
            else:
                print(f"  Attempt 2 Failed (Exit Code: {result2.returncode}).")

        # --- Update Tracking ---
        if download_successful:
            log_downloaded_id(tracking_file_path, tracking_id) # Use full path
            downloaded_ids.add(tracking_id)
            success_count += 1
        else:
            print(f"  Status: FAILED (Both attempts failed for link: {link})")
            # Optionally log the actual error output from yt-dlp here
            # if result1: print(f"  Stderr 1: {result1.stderr[:300]}...")
            # if result2: print(f"  Stderr 2: {result2.stderr[:300]}...")
            failed_count += 1

        if yt_dlp_missing_error: break

    # === Step 6: Summary ===
    print("\n--- Run Summary ---")
    if yt_dlp_missing_error: print(f"Processing stopped: '{yt_dlp_executable}' command not found or failed to run.")
    print(f"Output directory: {os.path.abspath(output_dir)}")
    print(f"Successfully downloaded: {success_count}")
    print(f"Skipped (already downloaded): {skipped_count}")
    print(f"Failed downloads: {failed_count}")
    print(f"Total tasks processed/attempted: {success_count + skipped_count + failed_count}")

    print("\nScript finished.")


# --- Script Entry Point ---

if __name__ == "__main__":
    run()