"""
Utility modules for the job scraper.
"""

from src.utils.logger import setup_logger, get_scraper_logger
from src.utils.config import get_args, get_google_credentials
from src.utils.html_parser import (
    clean_html, create_description_summary,
    extract_salary, extract_experience, extract_job_type
)
from src.utils.caching import (
    CacheManager, cached, get_cache_size
)

__all__ = [
    'setup_logger',
    'get_scraper_logger',
    'get_args',
    'get_google_credentials',
    'clean_html',
    'create_description_summary',
    'extract_salary',
    'extract_experience',
    'extract_job_type',
    'CacheManager',
    'cached',
    'get_cache_size'
]