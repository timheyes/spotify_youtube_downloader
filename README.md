# Spotify / YouTube Audio Downloader

Downloads audio from YouTube links found in Spotify playlist/show descriptions or directly from YouTube playlists. It uses `yt-dlp` for downloading and keeps track of downloaded items to avoid duplicates on subsequent runs.

## Features

* Accepts Spotify Playlist URLs.
* Accepts Spotify Show URLs.
* Accepts YouTube Playlist URLs.
* Extracts YouTube links from Spotify episode descriptions (if applicable).
* Downloads audio using `yt-dlp`.
* Attempts download using Firefox cookies as a fallback if the standard download fails.
* Tracks successfully downloaded items (using Spotify Episode ID or YouTube Video ID) in `downloaded_media.log` to prevent re-downloads.
* Generates filenames based on upload date, item title, and ID.

## Prerequisites

* **Python:** Version 3.9 or newer.
* **Poetry:** For managing Python dependencies ([Installation Guide](https://python-poetry.org/docs/#installation)).
* **yt-dlp:** The core downloading tool. Must be installed and accessible in your system's PATH ([Installation Guide](https://github.com/yt-dlp/yt-dlp#installation)).
* **Spotify API Credentials (Required for Spotify URLs):**
    1.  Go to the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard/).
    2.  Create an App.
    3.  Note down your `Client ID` and `Client Secret`.
* **Firefox (Optional):** Required if you need the cookie-based download fallback mechanism.

## Installation & Setup

1.  **Clone the repository:**
    ```bash
    git clone [https://github.com/your-username/spotify-yt-downloader.git](https://github.com/your-username/spotify-yt-downloader.git) # <-- CHANGE THIS
    cd spotify-yt-downloader
    ```

2.  **Install dependencies using Poetry:**
    ```bash
    poetry install
    ```

3.  **Configure Spotify Credentials (if using Spotify features):**
    * **Recommended:** Create a file named `.env` in the project root directory (where `pyproject.toml` is).
    * Add your credentials to the `.env` file like this:
        ```dotenv
        # .env
        SPOTIPY_CLIENT_ID='YOUR_SPOTIFY_CLIENT_ID'
        SPOTIPY_CLIENT_SECRET='YOUR_SPOTIFY_CLIENT_SECRET'
        ```
    * Replace `'YOUR_SPOTIFY_CLIENT_ID'` and `'YOUR_SPOTIFY_CLIENT_SECRET'` with your actual credentials.
    * *Alternatively*, you can set these as system environment variables. The script will prioritize `.env` if it exists.

## Usage

1.  **Activate the virtual environment (optional but recommended):**
    ```bash
    poetry shell
    ```

2.  **Run the script:**

    * **If using `poetry shell`:**
        ```bash
        # Using the script entry point defined in pyproject.toml (requires code refactoring)
        # spotify-downloader "URL"

        # OR running the script directly (adjust path if needed)
        python src/spotify_yt_downloader/main.py
        # or if still in root: python downloader.py
        ```

    * **If *not* using `poetry shell`:**
        ```bash
        # Using the script entry point
        # poetry run spotify-downloader "URL"

        # OR running the script directly
        poetry run python src/spotify_yt_downloader/main.py
        # or if still in root: poetry run python downloader.py
        ```

3.  **Enter URL:** When prompted, paste the full URL of the Spotify Playlist, Spotify Show, or YouTube Playlist you want to process.

4.  **Output:**
    * The script will print progress messages to the console.
    * Downloaded audio files (defaulting to `.mp3`) will be saved in the directory where you run the script.
    * A `downloaded_media.log` file will be created/updated in the same directory, tracking successful downloads.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Disclaimer

Please respect copyright laws and the terms of service of Spotify and YouTube when using this tool. Download content only if you have the necessary rights or permissions.f
