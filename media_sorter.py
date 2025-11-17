#!/usr/bin/env python3
"""
Media Sorter - Automatically sort media files into TV and Movies folders
"""
import os
import re
import shutil
import time
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import requests
from typing import Optional, Dict, Tuple

# Configuration
WATCH_FOLDER = os.getenv('MEDIA_WATCH_FOLDER', '/media/incoming')
TV_FOLDER = os.getenv('MEDIA_TV_FOLDER', '/media/TV')
MOVIES_FOLDER = os.getenv('MEDIA_MOVIES_FOLDER', '/media/Movies')
TMDB_API_KEY = os.getenv('TMDB_API_KEY', '')  # Get free key from themoviedb.org
POLL_INTERVAL = int(os.getenv('POLL_INTERVAL', '60'))  # seconds

# Video file extensions
VIDEO_EXTENSIONS = {'.mkv', '.mp4', '.avi', '.mov', '.wmv', '.flv', '.m4v', '.mpg', '.mpeg'}


class MediaParser:
    """Parse media file/folder names and identify TV shows vs Movies"""
    
    # Common patterns for TV shows
    TV_PATTERNS = [
        r'[Ss](\d{1,2})[Ee](\d{1,2})',  # S01E01
        r'(\d{1,2})x(\d{1,2})',  # 1x01
        r'[Ss]eason[\s\._-]*(\d{1,2})[\s\._-]*[Ee]pisode[\s\._-]*(\d{1,2})',  # Season 1 Episode 1
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


class MediaSorter:
    """Sort media files into TV and Movies folders"""
    
    def __init__(self, watch_folder: str, tv_folder: str, movies_folder: str, tmdb_api_key: str = ''):
        self.watch_folder = Path(watch_folder)
        self.tv_folder = Path(tv_folder)
        self.movies_folder = Path(movies_folder)
        self.parser = MediaParser(tmdb_api_key)
        
        # Create folders if they don't exist
        self.watch_folder.mkdir(parents=True, exist_ok=True)
        self.tv_folder.mkdir(parents=True, exist_ok=True)
        self.movies_folder.mkdir(parents=True, exist_ok=True)
    
    def find_video_files(self, folder: Path) -> list:
        """Find all video files in folder"""
        video_files = []
        for root, dirs, files in os.walk(folder):
            for file in files:
                if Path(file).suffix.lower() in VIDEO_EXTENSIONS:
                    video_files.append(Path(root) / file)
        return video_files
    
    def sort_tv_show(self, source_folder: Path, tv_info: Dict):
        """Sort TV show into proper folder structure"""
        show_name = self.parser.get_proper_name(tv_info['show_name'], 'tv')
        season = tv_info['season']
        episode = tv_info['episode']
        
        # Create: TV/Show Name/Season 01/
        show_folder = self.tv_folder / show_name
        season_folder = show_folder / f"Season {season:02d}"
        season_folder.mkdir(parents=True, exist_ok=True)
        
        # Find video files
        video_files = self.find_video_files(source_folder)
        
        for video_file in video_files:
            ext = video_file.suffix
            new_name = f"{show_name} - S{season:02d}E{episode:02d}{ext}"
            dest_path = season_folder / new_name
            
            print(f"Moving TV: {video_file} -> {dest_path}")
            shutil.move(str(video_file), str(dest_path))
        
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
            new_name = f"{movie_name}{ext}"
            dest_path = movie_folder / new_name
            
            print(f"Moving Movie: {video_file} -> {dest_path}")
            shutil.move(str(video_file), str(dest_path))
        
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
        
        # Check if it's a TV show
        is_tv, tv_info = self.parser.is_tv_show(folder.name)
        
        if is_tv:
            print(f"Detected TV Show: {tv_info['show_name']} S{tv_info['season']:02d}E{tv_info['episode']:02d}")
            self.sort_tv_show(folder, tv_info)
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
    print("=" * 60)
    
    sorter = MediaSorter(WATCH_FOLDER, TV_FOLDER, MOVIES_FOLDER, TMDB_API_KEY)
    
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
