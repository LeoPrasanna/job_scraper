"""
Foundit job scraper implementation using hybrid approach.
"""

import os
import time
import random
import re
import json
import logging
from typing import Dict, List, Any, Optional, Union
from urllib.parse import quote, urljoin, quote_plus
import requests
from bs4 import BeautifulSoup

from src.scrapers.base_scraper import BaseJobScraper
from src.utils.html_parser import clean_html, create_description_summary


class FounditScraper(BaseJobScraper):
    """
    Foundit job scraper implementation with multiple fallback methods.
    """
    
    def __init__(self, cache_dir: str = "cache"):
        """
        Initialize Foundit scraper.
        
        Args:
            cache_dir: Directory to store cached data
        """
        super().__init__("Foundit", cache_dir)
        
        self.base_url = "https://www.foundit.in"
        self.search_url = f"{self.base_url}/srp/results"
        self.api_url = f"{self.base_url}/api-srp/results"
        
        # Initialize requests session
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.foundit.in/",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1"
        })
        
        # Store collected jobs
        self.jobs = []
    
    def get_experience_filter(self, years: Optional[str]) -> Optional[str]:
        """
        Convert years of experience to Foundit experience filter.
        
        Args:
            years: Years of experience as a string
            
        Returns:
            Foundit experience filter code
        """
        if not years:
            return None
            
        try:
            years_num = int(years)
            if years_num < 2:
                return "0~2"  # 0-2 years
            elif years_num < 5:
                return "2~5"  # 2-5 years
            elif years_num < 7:
                return "5~7"  # 5-7 years
            elif years_num < 10:
                return "7~10"  # 7-10 years
            elif years_num < 15:
                return "10~15"  # 10-15 years
            else:
                return "15~999"  # 15+ years
        except (ValueError, TypeError):
            return None
    
    def build_url(self, 
                 keyword: str, 
                 location: str, 
                 experience: Optional[str] = None, 
                 limit: int = 50, 
                 page: int = 1) -> str:
        """
        Build URL for job search.
        
        Args:
            keyword: Job search keyword
            location: Job location
            experience: Experience range
            limit: Results per page
            page: Page number
            
        Returns:
            Search URL
        """
        # Format the location parameter
        formatted_location = location.replace(" ", "+")
        
        # Build the URL
        url = (
            f"{self.search_url}?"
            f"sort=1&"
            f"limit={limit}&"
            f"query={keyword}&"
            f"locations={formatted_location}&"
            f"pageNo={page}"
        )
        
        # Add experience range if provided
        if experience:
            url += f"&experienceRanges={experience}"
        
        return url
    
    def build_api_url(self, 
                     keyword: str, 
                     location: str, 
                     experience: Optional[str] = None, 
                     limit: int = 50, 
                     page: int = 1) -> str:
        """
        Build API URL for job search.
        
        Args:
            keyword: Job search keyword
            location: Job location
            experience: Experience range
            limit: Results per page
            page: Page number
            
        Returns:
            API URL
        """
        # For the API url sometimes it's better to use encoded parameters
        keyword_encoded = quote(keyword)
        location_encoded = quote(location)
        
        # Build the URL
        url = (
            f"{self.api_url}?"
            f"sort=1&"
            f"limit={limit}&"
            f"query={keyword_encoded}&"
            f"locations={location_encoded}&"
            f"pageNo={page}"
        )
        
        # Add experience range if provided
        if experience:
            url += f"&experienceRanges={experience}"
        
        return url
    
    def scrape_jobs(self, 
                   keywords: str, 
                   location: str, 
                   limit: int = 50, 
                   experience: Optional[str] = None, 
                   **kwargs) -> List[Dict[str, Any]]:
        """
        Scrape job listings from Foundit.
        
        Args:
            keywords: Job search keywords
            location: Job location
            limit: Maximum number of jobs to fetch
            experience: Experience level (can be years or Foundit-specific format)
            **kwargs: Additional parameters
            
        Returns:
            List of job dictionaries
        """
        # Reset jobs list
        self.jobs = []
        
        # Convert experience to Foundit format if needed
        if experience and not '~' in experience:
            experience = self.get_experience_filter(experience)
        
        # Check if we have cached results
        cache_id = f"foundit_{keywords}_{location}_exp{experience or 'all'}"
        cached_data = self.load_from_cache(cache_id)
        
        if cached_data and len(cached_data) >= limit:
            self.logger.info(f"Using cached data for {keywords} in {location} ({len(cached_data)} jobs)")
            return cached_data[:limit]
        
        self.logger.info(f"Starting to scrape jobs for keyword: '{keywords}' in location: '{location}'")
        if experience:
            self.logger.info(f"Experience filter: {experience}")
        self.logger.info(f"Will gather up to {limit} jobs")
        
        # Try different scraping methods in sequence until we get enough jobs
        try:
            self.logger.info("Trying HTML scraping method...")
            self._scrape_via_html(keywords, location, experience, limit)
        except Exception as e:
            self.logger.error(f"Error in HTML scraping method: {e}")
        
        # If we don't have enough jobs, try the API method
        if not self.jobs or len(self.jobs) < limit:
            try:
                self.logger.info("Trying API scraping method...")
                self._scrape_via_api(keywords, location, experience, limit)
            except Exception as e:
                self.logger.error(f"Error in API scraping method: {e}")
        
        # If we still don't have jobs, try direct parsing method
        if not self.jobs:
            try:
                self.logger.info("Trying direct parsing method...")
                self._scrape_via_direct_parsing(keywords, location, experience, limit)
            except Exception as e:
                self.logger.error(f"Error in direct parsing method: {e}")
        
        # Standardize all jobs
        standardized_jobs = []
        for job in self.jobs[:limit]:
            standardized_jobs.append(self.standardize_job_data(job))
        
        # Save to cache if we have jobs
        if standardized_jobs:
            self.save_to_cache(standardized_jobs, cache_id)
            self.logger.info(f"Scraping complete! Collected {len(standardized_jobs)} jobs.")
        else:
            self.logger.warning("No jobs were collected.")
        
        return standardized_jobs
    
    def _scrape_via_html(self, 
                        keyword: str, 
                        location: str, 
                        experience: Optional[str] = None, 
                        max_jobs: int = 50) -> None:
        """
        Scrape jobs using standard HTML requests.
        
        Args:
            keyword: Job search keyword
            location: Job location
            experience: Experience range
            max_jobs: Maximum number of jobs to fetch
        """
        page = 1
        max_pages = 10
        
        while len(self.jobs) < max_jobs and page <= max_pages:
            url = self.build_url(keyword, location, experience, limit=50, page=page)
            self.logger.info(f"Fetching page {page}: {url}")
            
            try:
                # Add a random delay to avoid rate limiting
                self.add_random_delay(2, 4)
                
                # Get the page
                response = self.session.get(url, timeout=15)
                response.raise_for_status()
                
                # Extract job data from HTML
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Try to find the INITIAL_STATE in the script tags
                initial_state = None
                for script in soup.find_all('script'):
                    if script.string and 'window.__INITIAL_STATE__' in script.string:
                        try:
                            # Extract JSON from script
                            match = re.search(r'window\.__INITIAL_STATE__\s*=\s*({.*});', script.string)
                            if match:
                                initial_state = json.loads(match.group(1))
                                break
                        except:
                            continue
                
                # Process job data from INITIAL_STATE
                if initial_state and 'srp' in initial_state and 'jobList' in initial_state['srp']:
                    job_list = initial_state['srp']['jobList']
                    
                    if not job_list:
                        self.logger.warning(f"No jobs found on page {page}")
                        break
                    
                    self.logger.info(f"Found {len(job_list)} jobs on page {page}")
                    
                    # Process each job
                    for job in job_list:
                        if len(self.jobs) >= max_jobs:
                            break
                        
                        try:
                            job_info = {
                                'job_id': f"foundit_{job.get('jobId')}",
                                'title': job.get('title'),
                                'company': job.get('companyName'),
                                'location': ', '.join([loc.get('label', '') for loc in job.get('locations', [])]),
                                'experience': job.get('experience', ''),
                                'salary': job.get('salary', ''),
                                'posted_date': job.get('postedDate', ''),
                                'description': job.get('description', ''),
                                'skills': ', '.join(job.get('skills', [])),
                                'apply_url': f"https://www.foundit.in/job/{job.get('jobId')}",
                                'source': 'Foundit'
                            }
                            
                            self.jobs.append(job_info)
                            self.logger.info(f"Added job {len(self.jobs)}: {job_info['title']} at {job_info['company']}")
                        except Exception as e:
                            self.logger.error(f"Error processing job: {e}")
                            continue
                    
                    # Move to next page if needed
                    page += 1
                else:
                    # Try to extract job cards directly from HTML
                    job_cards = soup.select('.job-result-card, .job-card, .srpJobCard')
                    
                    if job_cards:
                        self.logger.info(f"Found {len(job_cards)} job cards on page {page}")
                        
                        for card in job_cards:
                            if len(self.jobs) >= max_jobs:
                                break
                            
                            try:
                                # Extract job details from card
                                title_elem = card.select_one('.job-title, .title, h2, h3, a[title]')
                                company_elem = card.select_one('.company-name, .company, .subtitle')
                                
                                if not title_elem or not company_elem:
                                    continue
                                
                                job_url = title_elem.get('href', '')
                                if job_url and not job_url.startswith('http'):
                                    job_url = f"{self.base_url}{job_url}"
                                
                                job_id = job_url.split('/')[-1] if job_url else f"foundit_{len(self.jobs)}"
                                
                                # Get location and experience
                                location_elem = card.select_one('.location-name, .location, .loc')
                                exp_elem = card.select_one('.exp-name, .experience, .exp')
                                
                                job_info = {
                                    'job_id': f"foundit_{job_id}",
                                    'title': title_elem.text.strip(),
                                    'company': company_elem.text.strip(),
                                    'location': location_elem.text.strip() if location_elem else '',
                                    'experience': exp_elem.text.strip() if exp_elem else '',
                                    'apply_url': job_url,
                                    'source': 'Foundit'
                                }
                                
                                self.jobs.append(job_info)
                                self.logger.info(f"Added job {len(self.jobs)}: {job_info['title']} at {job_info['company']}")
                            except Exception as e:
                                self.logger.error(f"Error processing job card: {e}")
                                continue
                        
                        # Move to next page
                        page += 1
                    else:
                        self.logger.warning(f"No job data found on page {page}")
                        break
            except Exception as e:
                self.logger.error(f"Error fetching page {page}: {e}")
                page += 1
    
    def _scrape_via_api(self, 
                       keyword: str, 
                       location: str, 
                       experience: Optional[str] = None, 
                       max_jobs: int = 50) -> None:
        """
        Scrape jobs using API requests.
        
        Args:
            keyword: Job search keyword
            location: Job location
            experience: Experience range
            max_jobs: Maximum number of jobs to fetch
        """
        page = 1
        max_pages = 10
        
        # Set up API headers
        api_headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        }
        self.session.headers.update(api_headers)
        
        while len(self.jobs) < max_jobs and page <= max_pages:
            url = self.build_api_url(keyword, location, experience, limit=50, page=page)
            self.logger.info(f"Fetching API page {page}: {url}")
            
            try:
                # Add a random delay to avoid rate limiting
                self.add_random_delay(2, 4)
                
                # Get the API response
                response = self.session.get(url, timeout=15)
                response.raise_for_status()
                
                # Parse JSON response
                data = response.json()
                
                # Extract job data
                if data and 'jobList' in data:
                    job_list = data['jobList']
                    
                    if not job_list:
                        self.logger.warning(f"No jobs found on API page {page}")
                        break
                    
                    self.logger.info(f"Found {len(job_list)} jobs on API page {page}")
                    
                    # Process each job
                    for job in job_list:
                        if len(self.jobs) >= max_jobs:
                            break
                        
                        try:
                            job_info = {
                                'job_id': f"foundit_{job.get('jobId')}",
                                'title': job.get('title'),
                                'company': job.get('companyName'),
                                'location': ', '.join([loc.get('label', '') for loc in job.get('locations', [])]),
                                'experience': job.get('experience', ''),
                                'salary': job.get('salary', ''),
                                'posted_date': job.get('postedDate', ''),
                                'description': job.get('description', ''),
                                'skills': ', '.join(job.get('skills', [])),
                                'apply_url': f"https://www.foundit.in/job/{job.get('jobId')}",
                                'source': 'Foundit'
                            }
                            
                            self.jobs.append(job_info)
                            self.logger.info(f"Added job {len(self.jobs)}: {job_info['title']} at {job_info['company']}")
                        except Exception as e:
                            self.logger.error(f"Error processing job: {e}")
                            continue
                    
                    # Move to next page
                    page += 1
                else:
                    self.logger.warning(f"No job data found in API response on page {page}")
                    break
            except Exception as e:
                self.logger.error(f"Error fetching API page {page}: {e}")
                page += 1
    
    def _scrape_via_direct_parsing(self, 
                                 keyword: str, 
                                 location: str, 
                                 experience: Optional[str] = None, 
                                 max_jobs: int = 50) -> None:
        """
        Fallback method that directly parses the page content.
        
        Args:
            keyword: Job search keyword
            location: Job location
            experience: Experience range
            max_jobs: Maximum number of jobs to fetch
        """
        url = self.build_url(keyword, location, experience, limit=max_jobs)
        self.logger.info(f"Using direct parsing method: {url}")
        
        try:
            # Add a random delay to avoid rate limiting
            self.add_random_delay(2, 4)
            
            # Get the page with a modified user agent (sometimes helps)
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            }
            response = requests.get(url, headers=headers, timeout=20)
            
            # Check if we got a successful response
            if response.status_code != 200:
                self.logger.error(f"Failed to get page: HTTP {response.status_code}")
                return
            
            # Save the HTML for debugging (optional)
            with open(os.path.join(self.cache_dir, "foundit_debug.html"), "w", encoding="utf-8") as f:
                f.write(response.text)
            
            # Parse the HTML
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Look for job cards
            job_cards = soup.select('.job-result-card, .job-card, .srpJobCard, [data-job-id]')
            
            if job_cards:
                self.logger.info(f"Found {len(job_cards)} job cards using direct parsing")
                
                for card in job_cards:
                    try:
                        # Extract job details from card
                        title_elem = card.select_one('.job-title, .title, h2, h3, a[title]')
                        company_elem = card.select_one('.company-name, .company, .subtitle')
                        
                        if not title_elem or not company_elem:
                            continue
                        
                        job_url = title_elem.get('href', '')
                        if job_url and not job_url.startswith('http'):
                            job_url = f"{self.base_url}{job_url}"
                        
                        job_id = job_url.split('/')[-1] if job_url else f"foundit_{len(self.jobs)}"
                        
                        # Get location and experience
                        location_elem = card.select_one('.location-name, .location, .loc')
                        exp_elem = card.select_one('.exp-name, .experience, .exp')
                        
                        job_info = {
                            'job_id': f"foundit_{job_id}",
                            'title': title_elem.text.strip(),
                            'company': company_elem.text.strip(),
                            'location': location_elem.text.strip() if location_elem else '',
                            'experience': exp_elem.text.strip() if exp_elem else '',
                            'apply_url': job_url,
                            'source': 'Foundit'
                        }
                        
                        self.jobs.append(job_info)
                        self.logger.info(f"Added job {len(self.jobs)}: {job_info['title']} at {job_info['company']}")
                        
                        if len(self.jobs) >= max_jobs:
                            break
                    except Exception as e:
                        self.logger.error(f"Error processing job card: {e}")
                        continue
            else:
                self.logger.warning("No job cards found using direct parsing")
                
                # Try to find the jobs in the page content as JSON
                script_tags = soup.find_all('script')
                for script in script_tags:
                    if script.string and ("jobList" in script.string or "INITIAL_STATE" in script.string):
                        try:
                            # Try to extract JSON data from the script
                            match = re.search(r'(window\.__INITIAL_STATE__|window\.__REDUX_STATE__)\s*=\s*({.*})[;\s]*', script.string)
                            if match:
                                data = json.loads(match.group(2))
                                
                                if 'srp' in data and 'jobList' in data['srp']:
                                    job_list = data['srp']['jobList']
                                    self.logger.info(f"Found {len(job_list)} jobs in script data")
                                    
                                    for job in job_list:
                                        if len(self.jobs) >= max_jobs:
                                            break
                                        
                                        try:
                                            job_info = {
                                                'job_id': f"foundit_{job.get('jobId')}",
                                                'title': job.get('title'),
                                                'company': job.get('companyName'),
                                                'location': ', '.join([loc.get('label', '') for loc in job.get('locations', [])]),
                                                'experience': job.get('experience', ''),
                                                'salary': job.get('salary', ''),
                                                'posted_date': job.get('postedDate', ''),
                                                'description': job.get('description', ''),
                                                'skills': ', '.join(job.get('skills', [])),
                                                'apply_url': f"https://www.foundit.in/job/{job.get('jobId')}",
                                                'source': 'Foundit'
                                            }
                                            
                                            self.jobs.append(job_info)
                                            self.logger.info(f"Added job {len(self.jobs)}: {job_info['title']} at {job_info['company']}")
                                        except Exception as e:
                                            self.logger.error(f"Error processing job from script data: {e}")
                                            continue
                                    
                                    break  # Stop after finding jobs in a script
                        except Exception as e:
                            self.logger.error(f"Error extracting JSON from script: {e}")
                            continue
        except Exception as e:
            self.logger.error(f"Error in direct parsing method: {e}")
    
    def close(self) -> None:
        """
        Clean up resources.
        """
        self.session.close()
        self.logger.info("Foundit scraper resources released")