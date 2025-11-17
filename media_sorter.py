#!/usr/bin/env python3
"""
Media Sorter - Automatically sort media files into TV and Movies folders
"""
import os
import re
import shutil
import time
import logging
from datetime import datetime
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import requests
from typing import Optional, Dict, Tuple

# Configuration
WATCH_FOLDER = os.getenv('MEDIA_WATCH_FOLDER', '/srv/dev-disk-by-uuid-2f521503-8710-48ab-8e68-17875edf1865/Server/incoming')
TV_FOLDER = os.getenv('MEDIA_TV_FOLDER', '/srv/dev-disk-by-uuid-2f521503-8710-48ab-8e68-17875edf1865/Server/TV')
MOVIES_FOLDER = os.getenv('MEDIA_MOVIES_FOLDER', '/srv/dev-disk-by-uuid-2f521503-8710-48ab-8e68-17875edf1865/Server/Movies')
TMDB_API_KEY = os.getenv('TMDB_API_KEY', '')  # Get free key from themoviedb.org
POLL_INTERVAL = int(os.getenv('POLL_INTERVAL', '60'))  # seconds
LOG_FILE = os.getenv('LOG_FILE', '/var/log/media-sorter.log')

# Video file extensions
VIDEO_EXTENSIONS = {'.mkv', '.mp4', '.avi', '.mov', '.wmv', '.flv', '.m4v', '.mpg', '.mpeg'}

# Subtitle file extensions
SUBTITLE_EXTENSIONS = {'.srt', '.sub', '.ass', '.ssa', '.vtt', '.idx', '.sup'}


class MediaParser:
    """Parse media file/folder names and identify TV shows vs Movies"""
    
    # Common patterns for TV shows
    TV_PATTERNS = [
        r'[Ss](\d{1,2})[Ee](\d{1,2})',  # S01E01
        r'(\d{1,2})x(\d{1,2})',  # 1x01
        r'[Ss]eason[\s\._-]*(\d{1,2})[\s\._-]*[Ee]pisode[\s\._-]*(\d{1,2})',  # Season 1 Episode 1
    ]
    
    # Resolution patterns
    RESOLUTION_PATTERNS = [
        (r'2160p|4K|UHD', '2160p'),
        (r'1080p|FHD', '1080p'),
        (r'720p|HD', '720p'),
        (r'480p|SD', '480p'),
    ]
    
    def __init__(self, tmdb_api_key: str = ''):
        self.tmdb_api_key = tmdb_api_key
        self.session = requests.Session()
    
    def clean_name(self, name: str) -> str:
        """Clean up media name by removing common junk"""
        # Remove file extension
        name = os.path.splitext(name)[0]
        
        # Remove common tags
        junk = [
            r'\[.*?\]', r'\(.*?\)',  # Remove brackets
            r'1080p', r'720p', r'2160p', r'4K',  # Quality
            r'BluRay', r'BRRip', r'WEB-DL', r'WEBRip', r'HDTV',  # Source
            r'x264', r'x265', r'H\.264', r'HEVC',  # Codec
            r'AAC', r'AC3', r'DTS',  # Audio
            r'YIFY', r'RARBG', r'ETRG',  # Release groups
        ]
        
        for pattern in junk:
            name = re.sub(pattern, '', name, flags=re.IGNORECASE)
        
        # Replace dots, underscores with spaces
        name = re.sub(r'[\._]', ' ', name)
        
        # Remove extra spaces
        name = re.sub(r'\s+', ' ', name).strip()
        
        return name
    
    def is_tv_show(self, name: str) -> Tuple[bool, Optional[Dict]]:
        """Check if name matches TV show patterns"""
        for pattern in self.TV_PATTERNS:
            match = re.search(pattern, name, re.IGNORECASE)
            if match:
                season = int(match.group(1))
                episode = int(match.group(2))
                # Extract show name (everything before the pattern)
                show_name = name[:match.start()].strip()
                show_name = self.clean_name(show_name)
                
                return True, {
                    'show_name': show_name,
                    'season': season,
                    'episode': episode
                }
        
        return False, None
    
    def search_tmdb(self, query: str, media_type: str) -> Optional[Dict]:
        """Search TMDB for media info"""
        if not self.tmdb_api_key:
            return None
        
        try:
            url = f'https://api.themoviedb.org/3/search/{media_type}'
            params = {
                'api_key': self.tmdb_api_key,
                'query': query
            }
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            results = response.json().get('results', [])
            
            if results:
                return results[0]  # Return first match
        except Exception as e:
            print(f"TMDB search error: {e}")
        
        return None
    
    def get_proper_name(self, name: str, media_type: str) -> str:
        """Get proper formatted name from TMDB"""
        cleaned = self.clean_name(name)
        
        if media_type == 'tv':
            result = self.search_tmdb(cleaned, 'tv')
            if result:
                return result.get('name', cleaned)
        else:
            result = self.search_tmdb(cleaned, 'movie')
            if result:
                title = result.get('title', cleaned)
                year = result.get('release_date', '')[:4]
                if year:
                    return f"{title} ({year})"
                return title
        
        return cleaned
    
    def detect_resolution(self, filename: str) -> Optional[str]:
        """Detect video resolution from filename"""
        for pattern, resolution in self.RESOLUTION_PATTERNS:
            if re.search(pattern, filename, re.IGNORECASE):
                return resolution
        return None


class MediaSorter:
    """Sort media files into TV and Movies folders"""
    
    def __init__(self, watch_folder: str, tv_folder: str, movies_folder: str, tmdb_api_key: str = '', log_file: str = ''):
        self.watch_folder = Path(watch_folder)
        self.tv_folder = Path(tv_folder)
        self.movies_folder = Path(movies_folder)
        self.parser = MediaParser(tmdb_api_key)
        self.log_file = log_file
        
        # Set umask to allow group write (002 = rwxrwxr-x)
        os.umask(0o002)
        
        # Create folders if they don't exist
        self.watch_folder.mkdir(parents=True, exist_ok=True)
        self.tv_folder.mkdir(parents=True, exist_ok=True)
        self.movies_folder.mkdir(parents=True, exist_ok=True)
        
        # Setup file logging
        if self.log_file:
            self._setup_file_logger()
    
    def _setup_file_logger(self):
        """Setup file logger for movement tracking"""
        try:
            # Create log directory if it doesn't exist
            log_path = Path(self.log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Setup file handler
            file_handler = logging.FileHandler(self.log_file)
            file_handler.setLevel(logging.INFO)
            formatter = logging.Formatter('%(asctime)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
            file_handler.setFormatter(formatter)
            
            # Get logger
            self.logger = logging.getLogger('media_sorter')
            self.logger.setLevel(logging.INFO)
            self.logger.addHandler(file_handler)
        except Exception as e:
            print(f"Warning: Could not setup file logging: {e}")
            self.logger = None
    
    def log_move(self, source: str, destination: str, media_type: str):
        """Log a file movement"""
        if self.logger:
            self.logger.info(f"{media_type} | {source} -> {destination}")
    
    def find_video_files(self, folder: Path) -> list:
        """Find all video files in folder"""
        video_files = []
        for root, dirs, files in os.walk(folder):
            for file in files:
                if Path(file).suffix.lower() in VIDEO_EXTENSIONS:
                    video_files.append(Path(root) / file)
        return video_files
    
    def find_subtitle_files(self, folder: Path) -> list:
        """Find all subtitle files in folder and subfolders"""
        subtitle_files = []
        for root, dirs, files in os.walk(folder):
            for file in files:
                if Path(file).suffix.lower() in SUBTITLE_EXTENSIONS:
                    subtitle_files.append(Path(root) / file)
        return subtitle_files
    
    def match_subtitle_to_video(self, subtitle_path: Path, video_files: list) -> Optional[Path]:
        """Try to match a subtitle file to a video file"""
        sub_name = subtitle_path.stem.lower()
        
        # Remove common subtitle tags
        sub_name_clean = re.sub(r'\.(eng|english|forced|sdh|cc|hi)$', '', sub_name, flags=re.IGNORECASE)
        
        # Try exact match first
        for video in video_files:
            video_name = video.stem.lower()
            if sub_name_clean == video_name or sub_name == video_name:
                return video
        
        # Try partial match (subtitle name contains video name or vice versa)
        for video in video_files:
            video_name = video.stem.lower()
            if sub_name_clean in video_name or video_name in sub_name_clean:
                return video
        
        return None
    
    def get_unique_filename(self, dest_folder: Path, base_name: str, extension: str, resolution: Optional[str] = None) -> Path:
        """Generate unique filename handling duplicates with resolution and version suffixes"""
        # Start with base name
        if resolution:
            candidate_name = f"{base_name}.{resolution}{extension}"
        else:
            candidate_name = f"{base_name}{extension}"
        
        candidate_path = dest_folder / candidate_name
        
        # If file doesn't exist, we're done
        if not candidate_path.exists():
            return candidate_path
        
        # File exists - check if it has the same resolution
        existing_name = candidate_path.stem
        existing_has_resolution = any(res in existing_name for _, res in self.parser.RESOLUTION_PATTERNS)
        
        # If we have a resolution and existing file doesn't, rename existing file
        if resolution and not existing_has_resolution:
            # Try to detect resolution of existing file (might be in original filename)
            # For now, assume it's unknown quality, add version suffix to new file
            pass
        
        # Same resolution or both without resolution - add version suffix
        version = 2
        while True:
            if resolution:
                versioned_name = f"{base_name}.{resolution}.v{version}{extension}"
            else:
                versioned_name = f"{base_name}.v{version}{extension}"
            
            versioned_path = dest_folder / versioned_name
            if not versioned_path.exists():
                return versioned_path
            version += 1
    
    def copy_subtitles(self, source_folder: Path, dest_folder: Path, video_name_base: str, resolution: Optional[str] = None):
        """Find and copy all subtitle files to destination with proper naming"""
        subtitle_files = self.find_subtitle_files(source_folder)
        
        if not subtitle_files:
            return
        
        print(f"Found {len(subtitle_files)} subtitle file(s)")
        
        for sub_file in subtitle_files:
            sub_ext = sub_file.suffix
            sub_stem = sub_file.stem.lower()
            
            # Detect language/type from filename
            lang_suffix = ""
            if re.search(r'\.(eng|english)', sub_stem, re.IGNORECASE):
                lang_suffix = ".en"
            elif re.search(r'\.(spa|spanish)', sub_stem, re.IGNORECASE):
                lang_suffix = ".es"
            elif re.search(r'\.(fre|french)', sub_stem, re.IGNORECASE):
                lang_suffix = ".fr"
            elif re.search(r'\.(ger|german)', sub_stem, re.IGNORECASE):
                lang_suffix = ".de"
            
            # Detect forced/SDH/CC
            if re.search(r'\.(forced)', sub_stem, re.IGNORECASE):
                lang_suffix += ".forced"
            elif re.search(r'\.(sdh|cc|hi)', sub_stem, re.IGNORECASE):
                lang_suffix += ".sdh"
            
            # Build subtitle name with resolution if present
            if resolution:
                new_name = f"{video_name_base}.{resolution}{lang_suffix}{sub_ext}"
            else:
                new_name = f"{video_name_base}{lang_suffix}{sub_ext}"
            
            dest_path = dest_folder / new_name
            
            # Handle duplicates for subtitles too
            if dest_path.exists():
                base = f"{video_name_base}{lang_suffix}"
                dest_path = self.get_unique_filename(dest_folder, base, sub_ext, resolution)
            
            print(f"Moving subtitle: {sub_file.name} -> {dest_path.name}")
            shutil.copy2(str(sub_file), str(dest_path))
    
    def sort_tv_episodes(self, source_folder: Path):
        """Sort TV episodes - handles multiple episodes in one folder"""
        video_files = self.find_video_files(source_folder)
        
        for video_file in video_files:
            # Check each video file for TV pattern
            is_tv, tv_info = self.parser.is_tv_show(video_file.name)
            
            if not is_tv:
                # Skip files that don't match TV pattern
                print(f"Skipping non-TV file: {video_file.name}")
                continue
            
            show_name = self.parser.get_proper_name(tv_info['show_name'], 'tv')
            season = tv_info['season']
            episode = tv_info['episode']
            
            # Create: TV/Show Name/Season 01/
            show_folder = self.tv_folder / show_name
            season_folder = show_folder / f"Season {season:02d}"
            season_folder.mkdir(parents=True, exist_ok=True)
            
            ext = video_file.suffix
            
            # Detect resolution from filename
            resolution = self.parser.detect_resolution(video_file.name)
            
            # Base name for the episode
            base_name = f"{show_name} - S{season:02d}E{episode:02d}"
            
            # Get unique filename (handles duplicates)
            dest_path = self.get_unique_filename(season_folder, base_name, ext, resolution)
            
            print(f"Moving TV: {video_file.name} -> {dest_path.name}")
            self.log_move(str(video_file), str(dest_path), "TV")
            shutil.move(str(video_file), str(dest_path))
            # Ensure group write permissions
            dest_path.chmod(0o664)
            
            # Copy subtitles for this episode
            self.copy_subtitles(source_folder, season_folder, base_name, resolution)
        
        # Clean up empty source folder
        self._cleanup_folder(source_folder)
    
    def sort_movie(self, source_folder: Path):
        """Sort movie into Movies folder"""
        folder_name = source_folder.name
        movie_name = self.parser.get_proper_name(folder_name, 'movie')
        
        # Create: Movies/Movie Name (Year)/
        movie_folder = self.movies_folder / movie_name
        movie_folder.mkdir(parents=True, exist_ok=True)
        
        # Find video files
        video_files = self.find_video_files(source_folder)
        
        for video_file in video_files:
            ext = video_file.suffix
            
            # Detect resolution from filename
            resolution = self.parser.detect_resolution(video_file.name)
            
            # Get unique filename (handles duplicates)
            dest_path = self.get_unique_filename(movie_folder, movie_name, ext, resolution)
            
            print(f"Moving Movie: {video_file} -> {dest_path}")
            self.log_move(str(video_file), str(dest_path), "MOVIE")
            shutil.move(str(video_file), str(dest_path))
            # Ensure group write permissions
            dest_path.chmod(0o664)
            
            # Copy subtitles for this movie
            self.copy_subtitles(source_folder, movie_folder, movie_name, resolution)
        
        # Clean up empty source folder
        self._cleanup_folder(source_folder)
    
    def _cleanup_folder(self, folder: Path):
        """Remove empty folder and parent if empty"""
        try:
            if folder.exists() and folder.is_dir():
                # Remove empty subdirectories
                for root, dirs, files in os.walk(folder, topdown=False):
                    for dir_name in dirs:
                        dir_path = Path(root) / dir_name
                        if not any(dir_path.iterdir()):
                            dir_path.rmdir()
                
                # Remove main folder if empty
                if not any(folder.iterdir()):
                    folder.rmdir()
                    print(f"Cleaned up: {folder}")
        except Exception as e:
            print(f"Cleanup error: {e}")
    
    def process_folder(self, folder: Path):
        """Process a single folder"""
        if not folder.is_dir():
            return
        
        print(f"\nProcessing: {folder.name}")
        
        # Check if folder name indicates TV show
        is_tv, tv_info = self.parser.is_tv_show(folder.name)
        
        # If not detected from folder, check video file names
        if not is_tv:
            video_files = self.find_video_files(folder)
            if video_files:
                # Check first video file for TV pattern
                first_video = video_files[0]
                is_tv, tv_info = self.parser.is_tv_show(first_video.name)
        
        if is_tv:
            print(f"Detected TV Show: {tv_info['show_name']} S{tv_info['season']:02d}E{tv_info['episode']:02d}")
            # Process each episode file individually
            self.sort_tv_episodes(folder)
        else:
            print(f"Detected Movie: {folder.name}")
            self.sort_movie(folder)
    
    def scan_watch_folder(self):
        """Scan watch folder for new media"""
        print(f"Scanning: {self.watch_folder}")
        
        for item in self.watch_folder.iterdir():
            if item.is_dir() and not item.name.startswith('.'):
                try:
                    self.process_folder(item)
                except Exception as e:
                    print(f"Error processing {item.name}: {e}")


class MediaWatchHandler(FileSystemEventHandler):
    """Handle file system events for auto-detection"""
    
    def __init__(self, sorter: MediaSorter):
        self.sorter = sorter
        self.pending_folders = set()
    
    def on_created(self, event):
        if event.is_directory:
            folder = Path(event.src_path)
            if not folder.name.startswith('.'):
                print(f"New folder detected: {folder.name}")
                self.pending_folders.add(folder)
    
    def process_pending(self):
        """Process folders that have been stable for a while"""
        for folder in list(self.pending_folders):
            if folder.exists():
                try:
                    self.sorter.process_folder(folder)
                    self.pending_folders.remove(folder)
                except Exception as e:
                    print(f"Error processing {folder.name}: {e}")


def main():
    print("=" * 60)
    print("Media Sorter - Starting")
    print("=" * 60)
    print(f"Watch Folder: {WATCH_FOLDER}")
    print(f"TV Folder: {TV_FOLDER}")
    print(f"Movies Folder: {MOVIES_FOLDER}")
    print(f"TMDB API: {'Enabled' if TMDB_API_KEY else 'Disabled (using basic naming)'}")
    print(f"Log File: {LOG_FILE}")
    print("=" * 60)
    
    sorter = MediaSorter(WATCH_FOLDER, TV_FOLDER, MOVIES_FOLDER, TMDB_API_KEY, LOG_FILE)
    
    # Initial scan
    sorter.scan_watch_folder()
    
    # Set up file system watcher
    event_handler = MediaWatchHandler(sorter)
    observer = Observer()
    observer.schedule(event_handler, str(sorter.watch_folder), recursive=False)
    observer.start()
    
    print("\nWatching for new folders... (Press Ctrl+C to stop)")
    
    try:
        while True:
            time.sleep(POLL_INTERVAL)
            # Periodic scan for any missed folders
            sorter.scan_watch_folder()
            # Process pending folders from watcher
            event_handler.process_pending()
    except KeyboardInterrupt:
        print("\nStopping...")
        observer.stop()
    
    observer.join()


if __name__ == '__main__':
    main()
