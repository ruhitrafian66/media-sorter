# Media Sorter

Automatically sort media files into TV and Movies folders with proper naming conventions.

## Features

- **Auto-detection**: Monitors a watch folder for new media
- **Smart parsing**: Identifies TV shows vs Movies from folder/file names
- **Pattern matching**: Handles various naming formats (S01E01, 1x01, etc.)
- **TMDB integration**: Optional API integration for accurate titles and metadata
- **Proper naming**: Renames files according to standard conventions
- **Clean organization**: Creates proper folder structures
- **Subtitle support**: Automatically finds and sorts subtitle files from any subfolder
- **Language detection**: Identifies subtitle language and type (forced, SDH, CC)

## Quick Start

### Installation

```bash
# Install dependencies
sudo apt-get update
sudo apt-get install python3 python3-pip
pip3 install -r requirements.txt

# Or use the install script
sudo bash install.sh
```

### Manual Run

```bash
# Set your folders
export MEDIA_WATCH_FOLDER=/path/to/incoming
export MEDIA_TV_FOLDER=/path/to/TV
export MEDIA_MOVIES_FOLDER=/path/to/Movies

# Optional: Add TMDB API key for better naming
export TMDB_API_KEY=your_key_here

# Run
python3 media_sorter.py
```

### Run as Service

```bash
# Edit the service file with your settings
sudo nano /etc/systemd/system/media-sorter.service

# Enable and start
sudo systemctl enable media-sorter
sudo systemctl start media-sorter

# Check status
sudo systemctl status media-sorter

# View logs
sudo journalctl -u media-sorter -f
```

## Configuration

Set these environment variables:

- `MEDIA_WATCH_FOLDER`: Folder to monitor for new media (default: `/media/incoming`)
- `MEDIA_TV_FOLDER`: Destination for TV shows (default: `/media/TV`)
- `MEDIA_MOVIES_FOLDER`: Destination for movies (default: `/media/Movies`)
- `TMDB_API_KEY`: Optional TMDB API key for accurate naming
- `POLL_INTERVAL`: Scan interval in seconds (default: `60`)
- `LOG_FILE`: Path to movement log file (default: `/var/log/media-sorter.log`)

## How It Works

### TV Shows

Input: `The.Office.S02E05.1080p.BluRay.x264/`
Output: `TV/The Office/Season 02/The Office - S02E05.mkv`

Supported patterns:
- S01E01, s01e01
- 1x01
- Season 1 Episode 1

### Movies

Input: `Inception.2010.1080p.BluRay.x264/`
Output: `Movies/Inception (2010)/Inception (2010).mkv`

## TMDB API Key (Optional)

Get a free API key:
1. Sign up at https://www.themoviedb.org
2. Go to Settings > API
3. Request an API key (choose "Developer")
4. Add to your environment or service file

## Movement Log

All file movements are logged to `/var/log/media-sorter.log` with timestamps:

```bash
# View recent movements
sudo tail -f /var/log/media-sorter.log

# Search for specific show/movie
sudo grep "Breaking Bad" /var/log/media-sorter.log

# View all TV show movements
sudo grep "TV |" /var/log/media-sorter.log

# View all movie movements
sudo grep "MOVIE |" /var/log/media-sorter.log
```

**Log format:**
```
2025-11-17 18:30:45 - TV | /path/to/source.mkv -> /path/to/destination.mkv
2025-11-17 18:31:12 - MOVIE | /path/to/source.mp4 -> /path/to/destination.mp4
```

## Troubleshooting

```bash
# Check service status
sudo systemctl status media-sorter

# View recent logs
sudo journalctl -u media-sorter -n 50

# View movement log
sudo tail -f /var/log/media-sorter.log

# Restart service
sudo systemctl restart media-sorter

# Test manually
python3 media_sorter.py
```

## Supported Formats

**Video**: mkv, mp4, avi, mov, wmv, flv, m4v, mpg, mpeg

**Subtitles**: srt, sub, ass, ssa, vtt, idx, sup

## Duplicate Handling

The sorter intelligently handles duplicate files:

**Different Resolutions** - Keeps both with resolution suffix:
- `Movie (2010).2160p.mkv` and `Movie (2010).1080p.mkv`
- `Show - S01E01.1080p.mkv` and `Show - S01E01.720p.mkv`

**Same Resolution** - Adds version suffix:
- `Movie (2010).1080p.mkv` and `Movie (2010).1080p.v2.mkv`
- `Show - S01E01.mkv` and `Show - S01E01.v2.mkv`

Supported resolutions: 2160p (4K/UHD), 1080p (FHD), 720p (HD), 480p (SD)

## Subtitle Handling

The sorter automatically finds subtitle files in any subfolder and moves them alongside the video file with proper naming:

**Examples:**
- `movie.srt` → `Movie Name (2010).srt`
- `movie.english.srt` → `Movie Name (2010).en.srt`
- `movie.forced.srt` → `Movie Name (2010).en.forced.srt`
- `movie.sdh.srt` → `Movie Name (2010).en.sdh.srt`

Supported languages: English (en), Spanish (es), French (fr), German (de)

The sorter will search through all subfolders (like `Subs/`, `Subtitles/`, etc.) to find subtitle files.
