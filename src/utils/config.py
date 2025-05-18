"""
Configuration management for the job scraper.
"""

import os
import argparse
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def get_args():
    """
    Parse command line arguments.
    
    Returns:
        argparse.Namespace: Parsed arguments
    """
    parser = argparse.ArgumentParser(description='Combined Job Scraper for LinkedIn, Naukri, TimesJobs, Foundit, and Glassdoor')
    
    # General options
    parser.add_argument('--keywords', type=str, default='Data Scientist', help='Job search keywords')
    parser.add_argument('--location', type=str, default='India', help='Job location')
    parser.add_argument('--output', type=str, default='google_sheets', help='Output format: "excel" or "google_sheets"')
    parser.add_argument('--excel-filename', type=str, default='job_listings.xlsx', help='Excel filename if using excel output')
    parser.add_argument('--headless', action='store_true', help='Run browser in headless mode')
    parser.add_argument('--skip-cleanup', action='store_true', help='Skip cleanup of temporary files after successful run')
    parser.add_argument('--experience', type=str, help='Experience level in years for ALL portals')
    parser.add_argument('--cache-dir', type=str, default='cache', help='Directory to store cached files')

    # LinkedIn specific options
    parser.add_argument('--linkedin-pages', type=int, default=8, help='Number of LinkedIn pages to scrape')
    parser.add_argument('--linkedin-min-jobs', type=int, default=75, help='Minimum number of LinkedIn jobs to scrape')
    parser.add_argument('--save-html', action='store_true', help='Save HTML files (LinkedIn only)')
    parser.add_argument('--filter-location', type=str, help='Additional location filter for LinkedIn')
    parser.add_argument('--use-api', action='store_true', help='Use LinkedIn API endpoint instead of normal page')
    parser.add_argument('--skip-linkedin', action='store_true', help='Skip LinkedIn scraping')
    parser.add_argument('--linkedin-experience', type=str, help='Experience value for LinkedIn only')
    
    # Naukri.com specific options
    parser.add_argument('--naukri-limit', type=int, default=50, help='Number of Naukri.com jobs to fetch')
    parser.add_argument('--naukri-experience', type=str, help='Experience value for Naukri.com only')
    parser.add_argument('--skip-naukri', action='store_true', help='Skip Naukri.com scraping')
    
    # TimesJobs specific options
    parser.add_argument('--timesjobs-limit', type=int, default=50, help='Number of TimesJobs jobs to fetch')
    parser.add_argument('--tj-experience', type=str, help='Experience value for TimesJobs only')
    parser.add_argument('--skip-timesjobs', action='store_true', help='Skip TimesJobs scraping')
    
    # Foundit specific options
    parser.add_argument('--foundit-limit', type=int, default=50, help='Number of Foundit jobs to fetch')
    parser.add_argument('--foundit-experience', type=str, help='Experience value for Foundit only')
    parser.add_argument('--skip-foundit', action='store_true', help='Skip Foundit scraping')
    
    # Glassdoor specific options
    parser.add_argument('--glassdoor-limit', type=int, default=50, help='Number of Glassdoor jobs to fetch')
    parser.add_argument('--glassdoor-experience', type=str, help='Experience value for Glassdoor only')
    parser.add_argument('--skip-glassdoor', action='store_true', help='Skip Glassdoor scraping')
    parser.add_argument('--glassdoor-email', type=str, help='Glassdoor login email (optional)')
    parser.add_argument('--glassdoor-password', type=str, help='Glassdoor login password (optional)')
    
    return parser.parse_args()

def get_google_credentials():
    """
    Get Google API credentials from environment or file.
    
    Returns:
        str: Path to credentials file or JSON string
    """
    # Check for credentials in environment variable
    creds_json = os.getenv('GOOGLE_SHEETS_CREDENTIALS')
    if creds_json:
        # Save to temporary file
        creds_dir = 'credentials'
        if not os.path.exists(creds_dir):
            os.makedirs(creds_dir)
        
        creds_path = os.path.join(creds_dir, 'service-account-key.json')
        with open(creds_path, 'w') as f:
            f.write(creds_json)
        
        return creds_path
    
    # Check for credentials file
    creds_path = os.path.join('credentials', 'service-account-key.json')
    if os.path.exists(creds_path):
        return creds_path
    
    return None