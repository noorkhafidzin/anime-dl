# Anime-DL

**Anime-DL** is a comprehensive automation system for managing anime downloads, from grabbing latest episodes to organizing files and sending notifications. It integrates episode grabbing, download queuing via MyJDownloader, file watching/moving, and a web interface.

## Features

- **Episode Grabber**: Automatically fetch latest episode links and download URLs from anime sites (configurable extractors).
- **Download Queuing**: Send download links to MyJDownloader API for automated downloading.
- **File Watcher & Organizer**: Monitor download directories, rename, and move files to library folders with Discord notifications.
- **Web Interface**: Streamlit-based UI for monitoring and configuration.
- **Scheduling**: Support for daily/weekly/interval scheduling per component.
- **Notifications**: Discord webhook notifications for updates, errors, and completions.
- **Configurable Extractors**: Regex, custom functions, or built-in types for scraping.

## Installation

1. Clone or download the repository.

2. Create a virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Configure `config/config.yaml` (copy from `config.yaml.example` and edit).

## Configuration

Edit `config/config.yaml` to set:
- `watch_dir`: Directory to monitor for new downloads.
- `log_file`: Path for logs.
- `discord_webhook`: URL for Discord notifications.
- `titles`: Mapping of anime keys to display names.
- `library_dirs`: Target directories for organized files.
- `mappings`: Rules for matching files to anime, with patterns, aliases, and offsets.
- `scheduler`: Global scheduler config (optional).
- For grabber: Add `source` URLs and extractor configs per mapping.

Example mapping:
```yaml
mappings:
  - pattern: "GK.*S5"
    anime_key: golden_kamuy
    season: 5
    source: "https://example.com/anime/golden-kamuy-s5"
    extract_latest:
      type: "smokelister"
    extract_download:
      type: "quality_block"
      quality: "1080p"
    scheduler:
      type: "weekly"
      time: "19:00"
      days: [0]  # Monday
```

## Usage

Use `main.py` as the entry point for all components:

### Grabber Mode
Fetch latest episodes and queue downloads:
```bash
python3 main.py grabber
```

### API Mode
Run the MyJDownloader API server:
```bash
python3 main.py api --host 0.0.0.0 --port 5000
```

### Watch Mode
Monitor and organize downloaded files:
```bash
python3 main.py watch
```

### Web Mode
Launch the web interface:
```bash
python3 main.py web --host 0.0.0.0 --port 8501
```

## Notes

- The system uses a SQLite database (`data/episodes.db`) to track processed episodes.
- Ensure MyJDownloader credentials are set as environment variables (`JD_EMAIL`, `JD_PASSWORD`, `JD_DEVICE`) for API mode.
- For scheduling, configure `scheduler` in `config.yaml` or per mapping.
- Discord notifications require a valid webhook URL.
- If `watchdog` is not installed, watch mode will only perform initial scan.

## Troubleshooting

- **Import Errors**: Ensure virtual environment is activated and dependencies are installed.
- **No Updates**: Check `source` URLs and extractor configs in mappings.
- **File Not Moved**: Verify `watch_dir`, `library_dirs`, and file patterns.

## Contributing

Feel free to submit issues or pull requests for improvements.