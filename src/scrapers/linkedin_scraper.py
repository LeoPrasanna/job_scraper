"""
LinkedIn job scraper implementation.
"""

import os
import time
import random
import re
import json
import logging
from typing import Dict, List, Any, Optional
from urllib.parse import quote, urljoin, quote_plus, urlparse
import requests
from bs4 import BeautifulSoup

from src.scrapers.base_scraper import BaseJobScraper
from src.utils.html_parser import (
    clean_html, create_description_summary, 
    extract_salary, extract_experience, extract_job_type
)

class LinkedInScraper(BaseJobScraper):
    """
    LinkedIn job scraper implementation using direct HTTP requests.
    """
    
    def __init__(self, cache_dir: str = "cache", save_html: bool = False):
        """
        Initialize LinkedIn scraper.
        
        Args:
            cache_dir: Directory to store cached data
            save_html: Whether to save HTML responses for debugging
        """
        super().__init__("LinkedIn", cache_dir)
        
        self.save_html = save_html
        
        # LinkedIn-specific headers
        self.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Referer': 'https://www.linkedin.com/jobs/',
            'Alt-Used': 'www.linkedin.com',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'same-origin',
            'Sec-Fetch-User': '?1',
            'TE': 'trailers',
            'Pragma': 'no-cache',
            'Cache-Control': 'no-cache',
        })
        
        self.session = requests.Session()
        self.session.headers.update(self.headers)
    
    def get_soup(self, url: str, max_retries: int = 3, initial_backoff: int = 5) -> Optional[BeautifulSoup]:
        """
        Get BeautifulSoup object from URL with retry mechanism.
        
        Args:
            url: URL to fetch
            max_retries: Maximum number of retry attempts
            initial_backoff: Initial backoff time in seconds
            
        Returns:
            BeautifulSoup object or None if failed
        """
        backoff = initial_backoff
        retries = 0
        
        while retries < max_retries:
            try:
                self.logger.info(f"Fetching URL: {url}")
                response = self.session.get(url, timeout=30)
                
                # Check for rate limiting
                if response.status_code == 429:
                    wait_time = backoff * (2 ** retries)
                    self.logger.warning(f"Rate limited (429). Waiting {wait_time} seconds before retry {retries+1}/{max_retries}")
                    time.sleep(wait_time)
                    retries += 1
                    continue
                
                response.raise_for_status()
                
                # Option to save HTML (disabled by default)
                if self.save_html:
                    filename = f"linkedin_{int(time.time())}.html"
                    with open(filename, 'w', encoding='utf-8') as f:
                        f.write(response.text)
                
                self.logger.info(f"Successfully fetched URL: {url}")
                return BeautifulSoup(response.text, 'html.parser')
                
            except requests.exceptions.RequestException as e:
                if retries < max_retries - 1:
                    wait_time = backoff * (2 ** retries)
                    self.logger.warning(f"Error fetching {url}: {e}. Retrying in {wait_time} seconds.")
                    time.sleep(wait_time)
                    retries += 1
                else:
                    self.logger.error(f"Failed to fetch {url} after {max_retries} retries: {e}")
                    return None
                    
            except Exception as e:
                self.logger.error(f"Unexpected error fetching {url}: {e}")
                return None
    
    def extract_job_description(self, job_url: Optional[str]) -> str:
        """
        Extract job description from job detail page.
        
        Args:
            job_url: URL of the job detail page
            
        Returns:
            Job description text
        """
        try:
            if not job_url:
                return "No job URL available"
                
            if not job_url.startswith('http'):
                job_url = f"https://www.linkedin.com{job_url}"
            
            self.logger.info(f"Extracting job description from: {job_url}")
            
            # Store the URL in case we can't fetch the description
            job_description_url = job_url
                
            # Try to fetch the page with exponential backoff
            soup = self.get_soup(job_url)
            if not soup:
                self.logger.warning(f"Could not fetch job description, storing URL instead: {job_url}")
                return f"URL: {job_description_url}"
            
            # Check for a structured description in JSON-LD format first
            script_elements = soup.select('script[type="application/ld+json"]')
            for script in script_elements:
                try:
                    job_data = json.loads(script.string)
                    if isinstance(job_data, dict) and 'description' in job_data:
                        self.logger.info("Found job description in JSON-LD data")
                        return job_data['description']
                except Exception as e:
                    self.logger.error(f"Error parsing JSON-LD data: {e}")
                
            # Common description selectors
            description_selectors = [
                "div.description__text",
                "div.show-more-less-html__markup",
                "section.description",
                "div.job-details",
                "div.job-description",
                "[data-test-id='job-description']",
                "div.jobs-description-content",
                "div.jobs-box__html-content",
                "div.jobs-description__content",
                "div.jobs-unified-top-card",
                "section.jobs-description",
                "div.jobs-description-content__text",
                "div.jobs-box-html-content",
                "div.jobs-details",
                "div.job-view-layout",
                "div.jobs-details-top-card__content-container",
                "div.job-details-jobs-unified-top-card__content-container",
                "section.core-section-container__content"
            ]
            
            # Try each selector
            for selector in description_selectors:
                element = soup.select_one(selector)
                if element:
                    description_text = element.get_text(strip=True)
                    if description_text and len(description_text) > 100:
                        self.logger.info(f"Found job description using selector: {selector}")
                        return description_text
            
            # If normal selectors didn't work, try a more aggressive approach
            # Look for any large text blocks which might be job descriptions
            paragraphs = soup.select('p, li, div > span')
            if paragraphs and len(paragraphs) > 3:
                description_text = []
                for p in paragraphs:
                    text = p.get_text(strip=True)
                    if len(text) > 30:  # Only include substantial paragraphs
                        description_text.append(text)
                
                if description_text:
                    combined_text = " ".join(description_text)
                    if len(combined_text) > 200:  # Ensure it's long enough to be a description
                        self.logger.info("Found job description by combining paragraph elements")
                        return combined_text
            
            # If we still can't find a description, look for any div with substantial text
            all_divs = soup.select('div')
            for div in all_divs:
                text = div.get_text(strip=True)
                if len(text) > 300:  # This is probably a description based on length
                    self.logger.info("Found job description in generic div with substantial text")
                    return text
                    
            # If we failed to extract text but have the URL, return it
            self.logger.warning(f"Could not find job description content, storing URL instead: {job_url}")
            return f"URL: {job_description_url}"
            
        except Exception as e:
            self.logger.error(f"Error extracting job description: {e}")
            # Return the URL if we have one
            if job_url:
                return f"URL: {job_url}"
            return "Error extracting job description"
    
    def get_experience_filter(self, years: Optional[str]) -> Optional[str]:
        """
        Convert years of experience to LinkedIn experience filter.
        
        Args:
            years: Years of experience as a string
            
        Returns:
            LinkedIn experience filter code
        """
        if not years:
            return None
            
        try:
            years_num = int(years)
            if years_num < 1:
                return "1"  # Less than 1 year
            elif years_num <= 3:
                return "2"  # 1-3 years
            elif years_num <= 5:
                return "3"  # 3-5 years
            elif years_num <= 7:
                return "4"  # 5-7 years
            elif years_num <= 10:
                return "5"  # 7-10 years
            else:
                return "6"  # More than 10 years
        except (ValueError, TypeError):
            return None
    
    def scrape_jobs(self, 
                   keywords: str, 
                   location: str, 
                   limit: int = 50, 
                   experience: Optional[str] = None, 
                   **kwargs) -> List[Dict[str, Any]]:
        """
        Scrape LinkedIn jobs.
        
        Args:
            keywords: Job search keywords
            location: Job location
            limit: Maximum number of jobs to fetch
            experience: Experience level in years
            **kwargs: Additional parameters:
                - num_pages: Number of pages to scrape
                - filter_location: Additional location filter
                - use_api: Whether to use LinkedIn API endpoint
            
        Returns:
            List of job dictionaries
        """
        # Additional parameters
        num_pages = kwargs.get('num_pages', 10)
        filter_location = kwargs.get('filter_location', location)
        use_api = kwargs.get('use_api', False)
        
        # Check cache first
        cache_id = f"linkedin_{keywords}_{location}_exp{experience or 'all'}"
        cached_data = self.load_from_cache(cache_id)
        
        if cached_data and len(cached_data) >= limit:
            self.logger.info(f"Using cached data for {keywords} in {location} ({len(cached_data)} jobs)")
            return cached_data[:limit]
        
        all_jobs = []
        
        # Prepare search URL
        keywords_encoded = quote(keywords)
        location_encoded = quote(location)
        
        # Add experience filter if provided
        experience_filter = ""
        exp_code = self.get_experience_filter(experience)
        if exp_code:
            experience_filter = f"&f_XP={exp_code}"
        
        # Construct search URL based on whether to use API or normal page
        if use_api:
            search_url = (
                f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
                f"?keywords={keywords_encoded}&location={location_encoded}{experience_filter}"
                f"&geoId=102713980&trk=public_jobs_jobs-search-bar_search-submit"
            )
        else:
            search_url = (
                f"https://www.linkedin.com/jobs/search/?keywords={keywords_encoded}"
                f"&location={location_encoded}{experience_filter}"
            )
        
        # Add location filter to the search URL if not already present
        if filter_location and filter_location != location and "location=" not in search_url.lower():
            search_url += f"&location={quote(filter_location)}"
            self.logger.info(f"Added location filter to search URL: {filter_location}")
        
        self.logger.info(f"Starting LinkedIn job search for: {keywords} in {location}")
        self.logger.info(f"Search URL: {search_url}")
        
        # Track jobs that pass initial filtering
        valid_jobs = []
        
        # Process job pages
        for page in range(1, num_pages + 1):
            if len(valid_jobs) >= limit:
                break
                
            # Adjust URL for pagination
            page_url = f"{search_url}&start={(page-1)*25}" if page > 1 else search_url
            self.logger.info(f"Scraping page {page}/{num_pages}: {page_url}")
            
            # Add delay between pages to avoid rate limiting
            if page > 1:
                delay_range = (3, 6) if page > 5 else (5, 8)
                wait_time = random.uniform(delay_range[0], delay_range[1])
                self.logger.info(f"Waiting {wait_time:.2f} seconds between pages to avoid rate limiting")
                time.sleep(wait_time)
            
            # Get the page content
            soup = self.get_soup(page_url)
            if not soup:
                self.logger.error(f"Failed to get page {page}, skipping to next page")
                continue
            
            # Find job listings with different selectors
            job_cards = soup.select(
                "div.job-search-card, li.jobs-search-results__list-item, "
                "[data-tracking-control-name='public_jobs_jserp-result_search-card']"
            )
            
            # Try alternative selectors if no job cards found
            if not job_cards:
                self.logger.warning(f"No job cards found on page {page}, trying alternative selectors")
                job_cards = soup.select(
                    "li.result-card, div.base-card, div.job-card-container, "
                    "div.job-card-list__entity, div.job-card-container--clickable, "
                    "li.jobs-search-results__list-item"
                )
            
            if not job_cards:
                self.logger.warning(f"No job cards found on page {page} with any selector")
                continue
            
            self.logger.info(f"Found {len(job_cards)} job cards on page {page}")
            
            # Process each job card
            for idx, card in enumerate(job_cards):
                try:
                    job = {}
                    
                    # Extract basic job info
                    title_elem = card.select_one(
                        "h3.base-search-card__title, h3.job-result-card__title, "
                        "h3.result-card__title, span.job-card-list__title, h3"
                    )
                    job['title'] = title_elem.get_text(strip=True) if title_elem else "No title found"
                    
                    company_elem = card.select_one(
                        "h4.base-search-card__subtitle, a.job-result-card__subtitle-link, "
                        "h4.result-card__subtitle, span.job-card-container__company-name, "
                        "span.company-name, h4"
                    )
                    job['company'] = company_elem.get_text(strip=True) if company_elem else "No company found"
                    
                    location_elem = card.select_one(
                        "span.job-search-card__location, span.job-result-card__location, "
                        "span.result-card__location, span.job-card-container__location, span.location"
                    )
                    job['location'] = location_elem.get_text(strip=True) if location_elem else "No location found"
                    
                    # Skip entries that don't have proper title or company
                    if job['title'] == "No title found" or job['company'] == "No company found":
                        self.logger.info(f"Skipping incomplete job entry {idx+1}/{len(job_cards)} on page {page}")
                        continue
                    
                    # Get job link
                    job_link = card.select_one(
                        "a.base-card__full-link, a.result-card__full-card-link, "
                        "a.job-card-container__link, a.job-card-list__title-link"
                    )
                    
                    if not job_link:
                        job_link = card.select_one("a[href*='/jobs/view/']")
                        
                    if not job_link:
                        all_links = card.select("a")
                        for link_elem in all_links:
                            if 'href' in link_elem.attrs and '/jobs/view/' in link_elem['href']:
                                job_link = link_elem
                                break
                                
                    job['url'] = job_link['href'] if job_link and 'href' in job_link.attrs else None
                    
                    # Skip jobs without URLs
                    if not job['url']:
                        self.logger.info(f"Skipping job without URL: {job['title']} at {job['company']}")
                        continue
                    
                    # Extract job ID from URL
                    if job['url']:
                        url_parts = urlparse(job['url'])
                        path_segments = url_parts.path.split('/')
                        for segment in path_segments:
                            if segment.isdigit():
                                job['job_id'] = f"linkedin_{segment}"
                                break
                        
                        if 'job_id' not in job:
                            job['job_id'] = f"linkedin_{random.randint(10000, 99999)}"
                    else:
                        job['job_id'] = f"linkedin_{random.randint(10000, 99999)}"
                    
                    # Try to get posted date
                    date_elem = card.select_one("time.job-search-card__listdate, time.job-result-card__listdate, time")
                    if date_elem and 'datetime' in date_elem.attrs:
                        job['posted_date'] = date_elem['datetime']
                    else:
                        date_text_elem = card.select_one(
                            "span.job-search-card__listdate, span.job-result-card__listdate, span.date-range"
                        )
                        job['posted_date'] = date_text_elem.get_text(strip=True) if date_text_elem else "Unknown"
                    
                    # Add the job to valid jobs list
                    valid_jobs.append(job)
                    
                    # Log progress
                    self.logger.info(f"Processed job {idx+1}/{len(job_cards)} on page {page}: {job['title']} at {job['company']}")
                    
                except Exception as e:
                    self.logger.error(f"Error processing job card: {e}")
                    continue
            
            # Break if we've collected enough jobs
            if len(valid_jobs) >= limit:
                break
        
        # Process job descriptions with proper delays
        for job_idx, job in enumerate(valid_jobs):
            if len(all_jobs) >= limit:
                break
                
            # Skip if no URL
            if not job.get('url'):
                job['description'] = "No job URL available"
                job['job_type'] = "Unknown"
                all_jobs.append(self.standardize_job_data(job))
                continue
            
            # Add random delay between job detail requests to avoid rate limiting
            detail_delay = random.uniform(2, 4)
            self.logger.info(f"Waiting {detail_delay:.2f} seconds before fetching job {job_idx+1}/{len(valid_jobs)} details")
            time.sleep(detail_delay)
            
            # Attempt to get job details
            details = self.extract_job_description(job['url'])
            
            # Store full description
            job['description'] = details
            
            # Extract metadata from description
            if details and not details.startswith("URL:"):
                # Try to extract job type from description
                job_type = extract_job_type(details) or "Not specified"
                job['job_type'] = job_type
                
                # Try to extract salary if available
                salary = extract_salary(details) or "Not specified"
                job['salary'] = salary
                
                # Try to extract experience requirements
                experience_req = extract_experience(details) or "Not specified"
                job['experience'] = experience_req
            else:
                job['job_type'] = "See job description"
                job['salary'] = "Not specified"
                job['experience'] = "Not specified"
            
            # Add source field
            job['source'] = "LinkedIn"
            
            # Convert URL to apply_url for consistency
            job['apply_url'] = job['url']
            
            # Standardize and add to final list
            all_jobs.append(self.standardize_job_data(job))
        
        # Ensure we don't exceed the limit
        all_jobs = all_jobs[:limit]
        
        # Cache the results
        if all_jobs:
            self.save_to_cache(all_jobs, cache_id)
        
        self.logger.info(f"Successfully scraped {len(all_jobs)} jobs from LinkedIn")
        return all_jobs
    
    def close(self) -> None:
        """
        Clean up resources.
        """
        self.session.close()
        self.logger.info("LinkedIn scraper resources released")