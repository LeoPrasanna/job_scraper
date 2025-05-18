"""
Caching utilities for job scrapers.
"""

import os
import json
import time
import shutil
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional, Union, Callable
from functools import wraps
from pathlib import Path

logger = logging.getLogger(__name__)

class CacheManager:
    """
    Manages cached data for job scrapers.
    """
    
    def __init__(self, cache_dir: str = "cache"):
        """
        Initialize the cache manager.
        
        Args:
            cache_dir: Base directory for cache files
        """
        self.cache_dir = cache_dir
        
        # Create cache directory if it doesn't exist
        if not os.path.exists(cache_dir):
            os.makedirs(cache_dir)
    
    def get_cache_path(self, cache_id: str, sub_dir: Optional[str] = None) -> str:
        """
        Get the full path for a cache file.
        
        Args:
            cache_id: Unique identifier for the cached data
            sub_dir: Optional subdirectory within cache_dir
            
        Returns:
            Full path to the cache file
        """
        if sub_dir:
            directory = os.path.join(self.cache_dir, sub_dir)
            if not os.path.exists(directory):
                os.makedirs(directory)
            return os.path.join(directory, f"{cache_id}.json")
        else:
            return os.path.join(self.cache_dir, f"{cache_id}.json")
    
    def load(self, cache_id: str, sub_dir: Optional[str] = None) -> Optional[Any]:
        """
        Load data from cache if available.
        
        Args:
            cache_id: Unique identifier for the cached data
            sub_dir: Optional subdirectory within cache_dir
            
        Returns:
            Cached data or None if not found/invalid
        """
        cache_path = self.get_cache_path(cache_id, sub_dir)
        if os.path.exists(cache_path):
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    logger.info(f"Loading from cache: {cache_path}")
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading from cache {cache_path}: {e}")
        return None
    
    def save(self, data: Any, cache_id: str, sub_dir: Optional[str] = None) -> bool:
        """
        Save data to cache.
        
        Args:
            data: Data to cache
            cache_id: Unique identifier for the cached data
            sub_dir: Optional subdirectory within cache_dir
            
        Returns:
            True if successful, False otherwise
        """
        cache_path = self.get_cache_path(cache_id, sub_dir)
        try:
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info(f"Saved data to cache: {cache_path}")
            return True
        except Exception as e:
            logger.error(f"Error saving to cache {cache_path}: {e}")
            return False
    
    def is_fresh(self, cache_id: str, max_age_hours: int = 24, sub_dir: Optional[str] = None) -> bool:
        """
        Check if a cache entry is fresh (not older than max_age_hours).
        
        Args:
            cache_id: Unique identifier for the cached data
            max_age_hours: Maximum age in hours for the cache to be considered fresh
            sub_dir: Optional subdirectory within cache_dir
            
        Returns:
            True if cache is fresh, False otherwise
        """
        cache_path = self.get_cache_path(cache_id, sub_dir)
        if not os.path.exists(cache_path):
            return False
        
        # Check file modification time
        file_time = os.path.getmtime(cache_path)
        file_datetime = datetime.fromtimestamp(file_time)
        now = datetime.now()
        
        # Calculate age in hours
        age_hours = (now - file_datetime).total_seconds() / 3600
        
        return age_hours <= max_age_hours
    
    def delete(self, cache_id: str, sub_dir: Optional[str] = None) -> bool:
        """
        Delete a cache entry.
        
        Args:
            cache_id: Unique identifier for the cached data
            sub_dir: Optional subdirectory within cache_dir
            
        Returns:
            True if successful, False otherwise
        """
        cache_path = self.get_cache_path(cache_id, sub_dir)
        if os.path.exists(cache_path):
            try:
                os.remove(cache_path)
                logger.info(f"Deleted cache file: {cache_path}")
                return True
            except Exception as e:
                logger.error(f"Error deleting cache file {cache_path}: {e}")
        return False
    
    def cleanup(self, max_age_hours: int = 72, sub_dir: Optional[str] = None) -> int:
        """
        Clean up old cache files.
        
        Args:
            max_age_hours: Maximum age in hours for cache files to keep
            sub_dir: Optional subdirectory within cache_dir
            
        Returns:
            Number of files deleted
        """
        directory = os.path.join(self.cache_dir, sub_dir) if sub_dir else self.cache_dir
        if not os.path.exists(directory):
            return 0
        
        count = 0
        now = time.time()
        
        for filename in os.listdir(directory):
            if filename.endswith(".json"):
                filepath = os.path.join(directory, filename)
                file_time = os.path.getmtime(filepath)
                
                # Calculate age in hours
                age_hours = (now - file_time) / 3600
                
                if age_hours > max_age_hours:
                    try:
                        os.remove(filepath)
                        count += 1
                    except Exception as e:
                        logger.error(f"Error deleting old cache file {filepath}: {e}")
        
        logger.info(f"Cleaned up {count} old cache files from {directory}")
        return count
    
    def purge(self, sub_dir: Optional[str] = None) -> bool:
        """
        Purge all cache files.
        
        Args:
            sub_dir: Optional subdirectory within cache_dir to purge
            
        Returns:
            True if successful, False otherwise
        """
        try:
            directory = os.path.join(self.cache_dir, sub_dir) if sub_dir else self.cache_dir
            if os.path.exists(directory):
                if sub_dir:
                    # Only delete contents if it's a subdirectory
                    for filename in os.listdir(directory):
                        file_path = os.path.join(directory, filename)
                        if os.path.isfile(file_path):
                            os.remove(file_path)
                    logger.info(f"Purged all cache files from {directory}")
                else:
                    # Delete and recreate the entire cache dir
                    shutil.rmtree(directory)
                    os.makedirs(directory)
                    logger.info("Purged entire cache directory")
                return True
            return False
        except Exception as e:
            logger.error(f"Error purging cache: {e}")
            return False
    
    def get_stats(self, sub_dir: Optional[str] = None) -> Dict[str, Any]:
        """
        Get statistics about the cache.
        
        Args:
            sub_dir: Optional subdirectory within cache_dir
            
        Returns:
            Dictionary with cache statistics
        """
        directory = os.path.join(self.cache_dir, sub_dir) if sub_dir else self.cache_dir
        
        stats = {
            "total_files": 0,
            "total_size_bytes": 0,
            "oldest_file_age_hours": 0,
            "newest_file_age_hours": float('inf'),
            "average_file_size_bytes": 0
        }
        
        if not os.path.exists(directory):
            return stats
        
        files = [f for f in os.listdir(directory) if f.endswith(".json")]
        stats["total_files"] = len(files)
        
        if not files:
            return stats
        
        now = time.time()
        file_sizes = []
        file_ages = []
        
        for filename in files:
            filepath = os.path.join(directory, filename)
            size = os.path.getsize(filepath)
            file_sizes.append(size)
            
            mtime = os.path.getmtime(filepath)
            age_hours = (now - mtime) / 3600
            file_ages.append(age_hours)
        
        stats["total_size_bytes"] = sum(file_sizes)
        stats["average_file_size_bytes"] = stats["total_size_bytes"] / len(file_sizes) if file_sizes else 0
        stats["oldest_file_age_hours"] = max(file_ages) if file_ages else 0
        stats["newest_file_age_hours"] = min(file_ages) if file_ages else float('inf')
        
        return stats


def cached(cache_dir: str = "cache", sub_dir: Optional[str] = None, 
          cache_key_fn: Optional[Callable] = None, max_age_hours: int = 24):
    """
    Decorator to cache function results.
    
    Args:
        cache_dir: Base directory for cache files
        sub_dir: Optional subdirectory within cache_dir
        cache_key_fn: Function to generate cache key from function arguments
        max_age_hours: Maximum age in hours for the cache to be considered fresh
        
    Returns:
        Decorated function
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Create cache manager
            cache_manager = CacheManager(cache_dir)
            
            # Generate cache key
            if cache_key_fn:
                cache_id = cache_key_fn(*args, **kwargs)
            else:
                # Default: Use function name and args as cache key
                arg_str = '_'.join(str(arg) for arg in args)
                kwarg_str = '_'.join(f"{k}_{v}" for k, v in sorted(kwargs.items()))
                cache_id = f"{func.__name__}_{arg_str}_{kwarg_str}"
                
                # Sanitize cache_id to be filesystem-friendly
                cache_id = "".join(c if c.isalnum() or c in '-_' else '_' for c in cache_id)
                if len(cache_id) > 200:  # Avoid filename too long errors
                    import hashlib
                    m = hashlib.md5(cache_id.encode())
                    cache_id = f"{cache_id[:150]}_{m.hexdigest()}"
            
            # Check if we have fresh cached results
            if cache_manager.is_fresh(cache_id, max_age_hours, sub_dir):
                cached_data = cache_manager.load(cache_id, sub_dir)
                if cached_data is not None:
                    logger.info(f"Using cached results for {func.__name__}")
                    return cached_data
            
            # Execute function and cache results
            result = func(*args, **kwargs)
            cache_manager.save(result, cache_id, sub_dir)
            
            return result
        return wrapper
    return decorator


def get_cache_size(cache_dir: str = "cache") -> int:
    """
    Get the total size of the cache directory in bytes.
    
    Args:
        cache_dir: Cache directory path
        
    Returns:
        Total size in bytes
    """
    total_size = 0
    
    if not os.path.exists(cache_dir):
        return total_size
    
    for dirpath, _, filenames in os.walk(cache_dir):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            if not os.path.islink(fp):
                total_size += os.path.getsize(fp)
    
    return total_size