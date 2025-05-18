"""
TimesJobs scraper implementation using requests and BeautifulSoup.
"""

import time
import random
import os
import re
import logging
from typing import Dict, List, Any, Optional, Union
from urllib.parse import quote_plus
import requests
from bs4 import BeautifulSoup

from src.scrapers.base_scraper import BaseJobScraper
from src.utils.html_parser import (
    clean_html, create_description_summary,
    extract_salary, extract_experience, extract_job_type
)


class TimesJobsScraper(BaseJobScraper):
    """
    TimesJobs job scraper implementation using HTTP requests.
    """
    
    def __init__(self, cache_dir: str = "cache"):
        """
        Initialize TimesJobs scraper.
        
        Args:
            cache_dir: Directory to store cached data
        """
        super().__init__("TimesJobs", cache_dir)
        
        self.base_url = "https://www.timesjobs.com"
        
        # Set up session
        self.session = requests.Session()
        
        # User agents to rotate
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Safari/605.1.15"
        ]
    
    def get_random_user_agent(self) -> str:
        """
        Get a random user agent from the list.
        
        Returns:
            Random user agent string
        """
        return random.choice(self.user_agents)
    
    def get_page(self, url: str, cache_id: Optional[str] = None, use_cache: bool = True) -> Optional[str]:
        """
        Get a web page with caching.
        
        Args:
            url: URL to fetch
            cache_id: Cache identifier (if None, generated from URL)
            use_cache: Whether to use cache
            
        Returns:
            HTML content or None if failed
        """
        # Generate cache ID from URL if not provided
        if cache_id is None:
            # Create safe filename from URL
            cache_id = url.replace("https://", "").replace("http://", "")
            cache_id = cache_id.replace("/", "_").replace("?", "_").replace("&", "_")
            # Truncate if too long
            if len(cache_id) > 200:
                cache_id = cache_id[:190] + str(hash(url) % 10000)
        
        # Check if we have a cached version
        if use_cache:
            cached_data = self.load_from_cache(cache_id)
            if cached_data:
                self.logger.info(f"Using cached page: {cache_id}")
                return cached_data
        
        # Random delay before request (2-5 seconds)
        delay = random.uniform(2, 5)
        self.logger.info(f"Waiting {delay:.2f}s before request")
        time.sleep(delay)
        
        # Prepare request headers
        headers = {
            "User-Agent": self.get_random_user_agent(),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": self.base_url,
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Cache-Control": "max-age=0"
        }
        
        try:
            self.logger.info(f"Fetching URL: {url}")
            response = self.session.get(url, headers=headers, timeout=30)
            
            if response.status_code == 200:
                html_content = response.text
                
                # Cache the response
                self.save_to_cache(html_content, cache_id)
                
                return html_content
            else:
                self.logger.error(f"Failed to fetch URL: {url}, Status code: {response.status_code}")
                return None
                
        except Exception as e:
            self.logger.error(f"Error fetching URL: {url}, Error: {e}")
            return None
    
    def extract_job_details_from_url(self, job_url: str, job_id: str) -> Dict[str, Any]:
        """
        Extract detailed job information from job detail page.
        
        Args:
            job_url: Job detail page URL
            job_id: Job ID for caching
            
        Returns:
            Dictionary of job details
        """
        details = {}
        
        cache_id = f"timesjobs_job_{job_id}"
        job_desc_html = self.get_page(job_url, cache_id=cache_id)
        
        if not job_desc_html:
            return details
        
        soup = BeautifulSoup(job_desc_html, 'html.parser')
        
        # Look for detailed description elements
        detail_desc_elem = soup.select_one('.job-desc, #jobdescription, .detail-job-dec, .desc, .job-description')
        if detail_desc_elem:
            details['description'] = detail_desc_elem.text.strip()
        
        # Get salary information
        salary_elem = soup.select_one('.salary-range, .salary, .sal')
        if salary_elem:
            details['salary'] = salary_elem.text.strip()
        
        # Get other job details
        industry_elem = soup.select_one('.industry, .jd-sec-info')
        if industry_elem:
            details['industry'] = industry_elem.text.strip()
        
        # Get education requirements
        education_elem = soup.select_one('.education, .qualification, .edu')
        if education_elem:
            details['education'] = education_elem.text.strip()
        
        # Extract job type if available
        job_type_elem = soup.select_one('.jobtype, .employment-type, .job-type')
        if job_type_elem:
            details['job_type'] = job_type_elem.text.strip()
        else:
            # Try to extract from description
            if 'description' in details:
                job_type = extract_job_type(details['description'])
                if job_type:
                    details['job_type'] = job_type
        
        return details
    
    def scrape_jobs(self, 
                   keywords: str, 
                   location: str, 
                   limit: int = 50, 
                   experience: Optional[str] = None, 
                   **kwargs) -> List[Dict[str, Any]]:
        """
        Scrape job listings from TimesJobs.
        
        Args:
            keywords: Job search keywords
            location: Job location
            limit: Maximum number of jobs to fetch
            experience: Experience level (0 for freshers, or number of years)
            **kwargs: Additional parameters
            
        Returns:
            List of job dictionaries
        """
        all_jobs = []
        page = 1
        exp_value = experience or "0"  # Default to 0 (fresher) if not specified
        
        # Check cache first
        cache_id = f"timesjobs_{keywords}_{location}_exp{exp_value}"
        cached_data = self.load_from_cache(cache_id)
        
        if cached_data and len(cached_data) >= limit:
            self.logger.info(f"Using cached data for {keywords} in {location} ({len(cached_data)} jobs)")
            return cached_data[:limit]
        
        # Prepare URL parameters
        keywords_encoded = quote_plus(keywords)
        location_encoded = quote_plus(location)
        
        self.logger.info(f"Scraping TimesJobs for '{keywords}' in '{location}' with experience: {exp_value}")
        
        while len(all_jobs) < limit:
            # Construct URL with experience filter
            url = (
                f"https://www.timesjobs.com/candidate/job-search.html?"
                f"searchType=personalizedSearch&from=submit&txtKeywords={keywords_encoded}"
                f"&txtLocation={location_encoded}&cboWorkExp1={exp_value}"
                f"&sequence={page}&startPage={page}"
            )
            
            page_cache_id = f"timesjobs_{keywords_encoded}_{location_encoded}_{exp_value}_{page}"
            html_content = self.get_page(url, cache_id=page_cache_id)
            
            if not html_content:
                self.logger.warning(f"Failed to get page from TimesJobs at page={page}")
                break
            
            # Parse HTML with BeautifulSoup
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Extract job cards - try different selectors in case the site structure changes
            job_cards = soup.select('.job-bx-info, .joblist-comp-info, .clearfix.job-bx')
            
            if not job_cards:
                # Try alternative selectors
                job_cards = soup.select('.joblist, li.clearfix, .jobs-list li')
                
                if not job_cards:
                    self.logger.info("No more job listings found on TimesJobs")
                    break
            
            self.logger.info(f"Found {len(job_cards)} jobs on page {page}")
            
            # Process each job card
            for card_idx, card in enumerate(job_cards):
                if len(all_jobs) >= limit:
                    break
                
                try:
                    # Extract job data with fallback options
                    # Title
                    title_elem = card.select_one('h2 a, h3 a, .clearfix h2 a, .job-listing-job-title a, a[title]')
                    
                    # Skip if no title element
                    if not title_elem:
                        continue
                    
                    # Company
                    company_elem = card.select_one('.job-bx-company span, .company-name span, h3 ~ h4, .list-job-dtl .joblist-comp-name, .company')
                    
                    # Skip if no company element
                    if not company_elem:
                        continue
                    
                    # Get job link
                    job_link = None
                    if title_elem and 'href' in title_elem.attrs:
                        job_link = title_elem['href']
                        # Make sure it's an absolute URL
                        if not job_link.startswith('http'):
                            job_link = f"https://www.timesjobs.com{job_link}"
                    
                    # Skip if no job link
                    if not job_link:
                        continue
                    
                    # Extract job ID from URL or generate one
                    job_id = None
                    if job_link:
                        match = re.search(r'(?:jobid|jdid)=(\d+)', job_link)
                        if match:
                            job_id = f"timesjobs_{match.group(1)}"
                        else:
                            job_id = f"timesjobs_{len(all_jobs)}"
                    else:
                        job_id = f"timesjobs_{len(all_jobs)}"
                    
                    # Location
                    location_elem = card.select_one('.locations, .list-job-dtl .joblist-loc, ul.top-jd-dtl li span[title^="Location"], .location')
                    
                    # Experience
                    exp_elem = card.select_one('.top-jd-dtl li:nth-child(1) span, .list-job-dtl .exp li span, .exp-salary')
                    
                    # Posted date
                    posted_elem = card.select_one('.joblist-date, .sim-posted, span.sim-posted, .post-date')
                    
                    # Job description
                    description_elem = card.select_one('.job-desc, .job-list-desc, .joblist-desc, .job-discription')
                    
                    # Skills
                    skills_elem = card.select_one('.skill-requirements, .srp-keyskills, .key-skill')
                    
                    # Create job data dictionary
                    job_data = {
                        'job_id': job_id,
                        'title': title_elem.text.strip() if title_elem else 'Not available',
                        'company': company_elem.text.strip() if company_elem else 'Not available',
                        'location': location_elem.text.strip() if location_elem else 'Not available',
                        'experience': exp_elem.text.strip() if exp_elem else 'Not available',
                        'posted_date': posted_elem.text.strip() if posted_elem else 'Not available',
                        'skills': skills_elem.text.strip() if skills_elem else 'Not available',
                        'description': description_elem.text.strip() if description_elem else 'Not available',
                        'apply_url': job_link,
                        'source': 'TimesJobs'
                    }
                    
                    # Get detailed job description if available and not already present
                    if job_link and (not description_elem or len(job_data['description']) < 100):
                        details = self.extract_job_details_from_url(job_link, job_id)
                        
                        # Update job data with details
                        for key, value in details.items():
                            if value and (key not in job_data or not job_data[key] or key == 'description'):
                                job_data[key] = value
                    
                    # Ensure salary field exists
                    if 'salary' not in job_data:
                        job_data['salary'] = "Not disclosed"
                    
                    # Ensure job_type field exists
                    if 'job_type' not in job_data:
                        job_data['job_type'] = "Not specified"
                    
                    # Standardize job data
                    std_job_data = self.standardize_job_data(job_data)
                    
                    all_jobs.append(std_job_data)
                    self.logger.info(f"Added job {len(all_jobs)}: {std_job_data['title']} at {std_job_data['company']}")
                    
                except Exception as e:
                    self.logger.error(f"Error parsing TimesJobs job card: {e}")
                    continue
            
            # Check if we should continue to next page
            if len(job_cards) < 10:  # TimesJobs typically shows 10 jobs per page
                # We've reached the end of results
                break
            
            # Move to next page
            page += 1
            
            # Add a longer delay between pages (5-10 seconds)
            if len(all_jobs) < limit:
                delay = random.uniform(5, 10)
                self.logger.info(f"Waiting {delay:.2f}s before next page request")
                time.sleep(delay)
        
        # Save to cache
        if all_jobs:
            self.save_to_cache(all_jobs, cache_id)
        
        self.logger.info(f"Collected {len(all_jobs)} jobs from TimesJobs")
        return all_jobs[:limit]
    
    def close(self) -> None:
        """
        Clean up resources.
        """
        self.session.close()
        self.logger.info("TimesJobs scraper resources released")