"""
Base Scraper module that defines the interface and common functionality for all job scrapers.
"""

import os
import time
import random
import json
import re
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional, Union
import logging
from bs4 import BeautifulSoup
from pathlib import Path
from datetime import datetime
from tenacity import retry, stop_after_attempt, wait_exponential

from src.utils.logger import setup_logger

class BaseJobScraper(ABC):
    """
    Abstract base class for all job scrapers.
    
    This class defines the interface that all concrete scraper implementations must follow
    and provides common utility methods for caching, HTML parsing, and error handling.
    """
    
    def __init__(self, 
                 name: str, 
                 cache_dir: str = "cache",
                 max_retries: int = 3) -> None:
        """
        Initialize the base scraper with common attributes.
        
        Args:
            name: The name of the scraper (used for logging and caching)
            cache_dir: Directory to store cached data
            max_retries: Maximum number of retry attempts for network operations
        """
        self.name = name
        self.cache_dir = os.path.join(cache_dir, name.lower())
        self.max_retries = max_retries
        
        # Set up logger
        self.logger = setup_logger(f"scraper.{name.lower()}")
        
        # Create cache directory if it doesn't exist
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)
        
        # Set common headers for HTTP requests
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Cache-Control': 'max-age=0',
        }
    
    @abstractmethod
    def scrape_jobs(self, 
                    keywords: str, 
                    location: str, 
                    limit: int = 50, 
                    experience: Optional[str] = None, 
                    **kwargs) -> List[Dict[str, Any]]:
        """
        Scrape job listings based on search parameters.
        
        Args:
            keywords: Job search keywords
            location: Job location
            limit: Maximum number of jobs to fetch
            experience: Experience level (if applicable)
            **kwargs: Additional scraper-specific parameters
            
        Returns:
            List of job dictionaries
        """
        pass
    
    @abstractmethod
    def close(self) -> None:
        """
        Clean up resources (e.g., close browser sessions, etc.).
        """
        pass
    
    def add_random_delay(self, min_seconds: float = 2.0, max_seconds: float = 5.0) -> None:
        """
        Add a random delay to simulate human behavior and avoid rate limiting.
        
        Args:
            min_seconds: Minimum delay in seconds
            max_seconds: Maximum delay in seconds
        """
        delay = random.uniform(min_seconds, max_seconds)
        self.logger.info(f"Waiting {delay:.2f}s")
        time.sleep(delay)
    
    def load_from_cache(self, cache_id: str) -> Optional[Any]:
        """
        Load data from cache if available.
        
        Args:
            cache_id: Unique identifier for the cached data
            
        Returns:
            Cached data or None if not found/invalid
        """
        cache_path = os.path.join(self.cache_dir, f"{cache_id}.json")
        if os.path.exists(cache_path):
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    self.logger.info(f"Loading from cache: {cache_id}")
                    return json.load(f)
            except Exception as e:
                self.logger.error(f"Error loading from cache: {e}")
        return None
    
    def save_to_cache(self, data: Any, cache_id: str) -> bool:
        """
        Save data to cache.
        
        Args:
            data: Data to cache
            cache_id: Unique identifier for the cached data
            
        Returns:
            True if successful, False otherwise
        """
        cache_path = os.path.join(self.cache_dir, f"{cache_id}.json")
        try:
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self.logger.info(f"Saved data to cache: {cache_id}")
            return True
        except Exception as e:
            self.logger.error(f"Error saving to cache: {e}")
            return False
    
    def cache_is_fresh(self, cache_id: str, max_age_hours: int = 24) -> bool:
        """
        Check if a cache entry is fresh (not older than max_age_hours).
        
        Args:
            cache_id: Unique identifier for the cached data
            max_age_hours: Maximum age in hours for the cache to be considered fresh
            
        Returns:
            True if cache is fresh, False otherwise
        """
        cache_path = os.path.join(self.cache_dir, f"{cache_id}.json")
        if not os.path.exists(cache_path):
            return False
        
        # Check file modification time
        file_time = os.path.getmtime(cache_path)
        file_datetime = datetime.fromtimestamp(file_time)
        now = datetime.now()
        
        # Calculate age in hours
        age_hours = (now - file_datetime).total_seconds() / 3600
        
        return age_hours <= max_age_hours
    
    def clean_html_content(self, html_text: Optional[str]) -> str:
        """
        Clean HTML content to extract plain text.
        
        Args:
            html_text: HTML text to clean
            
        Returns:
            Cleaned text
        """
        if not html_text:
            return ""
        
        # If it's a URL reference, return as is
        if isinstance(html_text, str) and html_text.startswith("URL:"):
            return html_text
                
        try:
            # Parse with BeautifulSoup
            soup = BeautifulSoup(str(html_text), 'html.parser')
            text = soup.get_text(separator=' ', strip=True)
            
            # Remove HTML tags
            text = re.sub(r'<[^>]+>', ' ', text)
            
            # Replace HTML entities
            text = re.sub(r'&amp;', '&', text)
            text = re.sub(r'&lt;', '<', text)
            text = re.sub(r'&gt;', '>', text)
            text = re.sub(r'&quot;', '"', text)
            text = re.sub(r'&#39;', "'", text)
            
            # Remove control characters
            text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', text)
            
            # Normalize whitespace
            text = re.sub(r'\s+', ' ', text).strip()
            
            # Truncate if too long (Excel has a 32,767 character limit per cell)
            if len(text) > 32000:
                text = text[:32000] + "... (text truncated)"
            
            return text
        except Exception as e:
            self.logger.error(f"Error cleaning HTML: {e}")
            
            # Fallback: simple cleanup
            safe_text = re.sub(r'<[^>]+>', ' ', str(html_text))
            safe_text = re.sub(r'&[^;]+;', ' ', safe_text)
            safe_text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', safe_text)
            safe_text = re.sub(r'\s+', ' ', safe_text).strip()
            
            if len(safe_text) > 32000:
                safe_text = safe_text[:32000] + "... (text truncated)"
                
            return safe_text
    
    def create_description_summary(self, text: str, max_length: int = 500) -> str:
        """
        Create a summary of job description text.
        
        Args:
            text: Full description text
            max_length: Maximum length of the summary
            
        Returns:
            Summary text
        """
        if not text:
            return ""
                
        if text.startswith("URL:"):
            return "See URL for details"
                
        if len(text) > max_length:
            summary = text[:max_length]
            # Try to end at a sentence
            last_period = summary.rfind('.')
            if last_period > 300:  # Only if we have a reasonable length sentence
                summary = summary[:last_period+1]
            summary += "..."
            return summary
        return text
    
    def standardize_job_data(self, job: Dict[str, Any]) -> Dict[str, Any]:
        """
        Standardize job data to ensure consistent format across all scrapers.
        
        Args:
            job: Raw job data
            
        Returns:
            Standardized job data
        """
        standard_job = job.copy()
        
        # Ensure source field is set
        if 'source' not in standard_job:
            standard_job['source'] = self.name
        
        # Standardize field names
        field_mappings = {
            'job_description': 'description',
            'url': 'apply_url',
            'experience_required': 'experience',
            'job_type': 'employment_type'
        }
        
        for old_field, new_field in field_mappings.items():
            if old_field in standard_job and new_field not in standard_job:
                standard_job[new_field] = standard_job[old_field]
        
        # Clean HTML in description
        if 'description' in standard_job:
            standard_job['description'] = self.clean_html_content(standard_job['description'])
            standard_job['description_summary'] = self.create_description_summary(standard_job['description'])
        
        # Ensure all standard fields exist
        standard_fields = [
            'job_id', 'title', 'company', 'location', 'experience',
            'salary', 'posted_date', 'description', 'apply_url', 'source'
        ]
        
        for field in standard_fields:
            if field not in standard_job:
                standard_job[field] = "Not available"
        
        return standard_job
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    def make_http_request(self, 
                         url: str, 
                         method: str = 'GET', 
                         headers: Optional[Dict[str, str]] = None, 
                         data: Optional[Dict[str, Any]] = None,
                         timeout: int = 30) -> Optional[str]:
        """
        Make an HTTP request with retry logic.
        
        Args:
            url: URL to request
            method: HTTP method (GET or POST)
            headers: Request headers
            data: Request data (for POST)
            timeout: Request timeout in seconds
            
        Returns:
            Response text if successful, None otherwise
        """
        import requests
        
        try:
            _headers = headers or self.headers
            
            self.logger.info(f"Making {method} request to {url}")
            
            if method.upper() == 'GET':
                response = requests.get(url, headers=_headers, timeout=timeout)
            elif method.upper() == 'POST':
                response = requests.post(url, headers=_headers, json=data, timeout=timeout)
            else:
                self.logger.error(f"Unsupported HTTP method: {method}")
                return None
            
            # Check if we got a successful response
            response.raise_for_status()
            
            self.logger.info(f"Received {len(response.text)} bytes response")
            return response.text
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"HTTP request failed: {e}")
            raise  # Let the retry decorator handle it
        except Exception as e:
            self.logger.error(f"Unexpected error in HTTP request: {e}")
            return None