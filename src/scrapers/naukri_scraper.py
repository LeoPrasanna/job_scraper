"""
Naukri.com job scraper implementation using Selenium.
"""

import os
import time
import random
import json
import logging
import shutil
import re
from typing import Dict, List, Any, Optional
from pathlib import Path
import subprocess

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from urllib.parse import quote

from src.scrapers.base_scraper import BaseJobScraper
from src.utils.html_parser import clean_html, create_description_summary


class NaukriScraper(BaseJobScraper):
    """
    Naukri.com job scraper using Selenium WebDriver.
    """
    
    def __init__(self, cache_dir: str = "cache", headless: bool = False):
        """
        Initialize Naukri.com scraper.
        
        Args:
            cache_dir: Directory to store cached data
            headless: Whether to run browser in headless mode
        """
        super().__init__("Naukri", cache_dir)
        
        self.base_url = "https://www.naukri.com"
        self.driver = None
        self.headless = headless
        
        # Create a unique user data directory for this instance
        self.user_data_dir = os.path.abspath("./chrome_user_data_naukri")
        
        # Initialize WebDriver
        self.setup_driver()
    
    def setup_driver(self) -> None:
        """
        Set up Selenium WebDriver.
        """
        try:
            # Clean up any existing user data directory
            self.cleanup_user_data_dir()
            
            options = Options()
            
            # Set user data directory
            options.add_argument(f"--user-data-dir={self.user_data_dir}")
            
            # Set headless mode if requested
            if self.headless:
                self.logger.info("Running in headless mode")
                options.add_argument("--headless=new")
            
            # Add common options
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_argument("--disable-extensions")
            options.add_argument("--window-size=1920,1080")
            
            # Set user agent
            options.add_argument(
                "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )
            
            # Initialize WebDriver
            self.driver = webdriver.Chrome(options=options)
            self.driver.set_page_load_timeout(30)
            
            self.logger.info("Selenium WebDriver initialized for Naukri.com")
            
        except Exception as e:
            self.logger.error(f"Error setting up WebDriver: {e}")
            if self.driver:
                self.driver.quit()
            raise
    
    def cleanup_user_data_dir(self) -> None:
        """
        Clean up Chrome user data directory.
        """
        try:
            if os.path.exists(self.user_data_dir):
                self.logger.info(f"Cleaning up existing user data directory: {self.user_data_dir}")
                shutil.rmtree(self.user_data_dir, ignore_errors=True)
            
            # Create fresh directory
            os.makedirs(self.user_data_dir, exist_ok=True)
            
            # Try to kill any existing Chrome processes
            try:
                subprocess.run(['pkill', '-f', 'chrome'], stderr=subprocess.DEVNULL)
                time.sleep(1)
            except:
                pass
                
        except Exception as e:
            self.logger.error(f"Error cleaning up user data directory: {e}")
    
    def close_popups(self) -> None:
        """
        Close any popups that appear on Naukri.com.
        """
        try:
            # Common popup selectors
            popup_selectors = [
                "div.crossIcon", 
                "button.modal-close", 
                "a.close", 
                ".naukicon-cross", 
                ".closeLayerBox", 
                ".popUpHideBtn",
                "button.hideWalk",
                ".buttonGhost",
                ".ni-close-icon"
            ]
            
            for selector in popup_selectors:
                try:
                    popup_close_btns = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    for btn in popup_close_btns:
                        if btn.is_displayed():
                            self.driver.execute_script("arguments[0].click();", btn)
                            time.sleep(1)
                except Exception:
                    continue
                    
            # Handle login overlay if it appears
            try:
                login_close = self.driver.find_element(By.CSS_SELECTOR, ".crossIcon, .grayBtnClose, .noBGButton, .cancelLayer")
                self.driver.execute_script("arguments[0].click();", login_close)
                time.sleep(1)
            except Exception:
                pass
                
        except Exception as e:
            self.logger.error(f"Error closing popups: {e}")
    
    def scroll_page(self, scroll_count: int = 5) -> None:
        """
        Scroll down the page to load all content.
        
        Args:
            scroll_count: Number of scroll steps
        """
        try:
            # Scroll down in steps
            for i in range(scroll_count):
                self.driver.execute_script(f"window.scrollBy(0, 500);")
                # Add a small random delay between scrolls
                time.sleep(random.uniform(0.5, 1.0))
                
            # Scroll back up a bit (human-like behavior)
            self.driver.execute_script("window.scrollBy(0, -300);")
            
        except Exception as e:
            self.logger.error(f"Error scrolling page: {e}")
    
    def extract_job_cards(self) -> List:
        """
        Extract all job card elements from the page.
        
        Returns:
            List of job card elements
        """
        # Try multiple selectors to find job cards
        selectors = [
            "article.jobTuple", 
            "div.jobTupleHeader", 
            ".jobTuple",
            ".job-card",
            ".srpJobCard"
        ]
        
        for selector in selectors:
            cards = self.driver.find_elements(By.CSS_SELECTOR, selector)
            if cards:
                self.logger.info(f"Found {len(cards)} job cards with selector: {selector}")
                return cards
                
        self.logger.warning("No job cards found with standard selectors, trying alternatives")
        
        # Try more generic selectors as fallback
        fallback_selectors = [
            "div[data-job-id]",
            "div.rec_details",
            "li.desktopItem"
        ]
        
        for selector in fallback_selectors:
            cards = self.driver.find_elements(By.CSS_SELECTOR, selector)
            if cards:
                self.logger.info(f"Found {len(cards)} job cards with fallback selector: {selector}")
                return cards
        
        self.logger.warning("No job cards found with any selector")
        return []
    
    def extract_job_data(self, card, idx: int) -> Dict[str, Any]:
        """
        Extract all relevant data from a job card.
        
        Args:
            card: Job card element
            idx: Job index
            
        Returns:
            Job data dictionary
        """
        job_data = {}
        job_data['job_id'] = f"naukri_{idx}"
        
        try:
            # Job Title - try multiple selectors
            try:
                title_elem = card.find_element(By.CSS_SELECTOR, "a.title, .jobTupleHeader a, .desig, .job-title, a.title.ellipsis")
                job_data['title'] = title_elem.text.strip()
                
                # Try to get URL
                job_data['apply_url'] = title_elem.get_attribute("href")
            except NoSuchElementException:
                try:
                    # Try another selector pattern
                    title_elem = card.find_element(By.CSS_SELECTOR, "a")
                    job_data['title'] = title_elem.text.strip()
                    job_data['apply_url'] = title_elem.get_attribute("href")
                except:
                    job_data['title'] = "Not available"
                    job_data['apply_url'] = None
            
            # Company Name
            company_selectors = [
                ".companyName", 
                ".companyInfo", 
                ".comp-name", 
                ".company-name",
                ".subTitle"
            ]
            
            for selector in company_selectors:
                try:
                    company_elem = card.find_element(By.CSS_SELECTOR, selector)
                    job_data['company'] = company_elem.text.strip()
                    break
                except:
                    continue
                    
            if 'company' not in job_data:
                job_data['company'] = "Not available"
            
            # Location
            location_selectors = [
                ".location", 
                ".loc", 
                "[title='Location']",
                ".locWdth"
            ]
            
            for selector in location_selectors:
                try:
                    location_elem = card.find_element(By.CSS_SELECTOR, selector)
                    job_data['location'] = location_elem.text.strip()
                    break
                except:
                    continue
                    
            if 'location' not in job_data:
                job_data['location'] = "Not specified"
            
            # Experience
            exp_selectors = [
                ".experience", 
                ".exp",
                "[title='Experience']",
                ".expwdth"
            ]
            
            for selector in exp_selectors:
                try:
                    exp_elem = card.find_element(By.CSS_SELECTOR, selector)
                    job_data['experience'] = exp_elem.text.strip()
                    break
                except:
                    continue
                    
            if 'experience' not in job_data:
                job_data['experience'] = "Not specified"
            
            # Salary
            salary_selectors = [
                ".salary",
                ".sal",
                "[title='salary']",
                ".sal-range"
            ]
            
            for selector in salary_selectors:
                try:
                    salary_elem = card.find_element(By.CSS_SELECTOR, selector)
                    job_data['salary'] = salary_elem.text.strip()
                    break
                except:
                    continue
                    
            if 'salary' not in job_data:
                job_data['salary'] = "Not disclosed"
            
            # Posted Date
            date_selectors = [
                ".date",
                ".jobDate",
                ".timeStamp"
            ]
            
            for selector in date_selectors:
                try:
                    date_elem = card.find_element(By.CSS_SELECTOR, selector)
                    job_data['posted_date'] = date_elem.text.strip()
                    break
                except:
                    continue
                    
            if 'posted_date' not in job_data:
                job_data['posted_date'] = "Not specified"
            
            # Description snippet
            desc_selectors = [
                ".job-description",
                ".job-desc",
                ".jd"
            ]
            
            for selector in desc_selectors:
                try:
                    desc_elem = card.find_element(By.CSS_SELECTOR, selector)
                    job_data['description'] = desc_elem.text.strip()
                    break
                except:
                    continue
                    
            if 'description' not in job_data:
                job_data['description'] = "See full details at apply URL"
            
            # Add source field
            job_data['source'] = 'Naukri.com'
            
            return job_data
            
        except Exception as e:
            self.logger.error(f"Error extracting job data: {e}")
            # Return job_id and source at minimum
            job_data['title'] = "Error extracting job data"
            job_data['company'] = "Unknown"
            job_data['source'] = 'Naukri.com'
            return job_data
    
    def scrape_jobs(self, 
                   keywords: str, 
                   location: str, 
                   limit: int = 50, 
                   experience: Optional[str] = None, 
                   **kwargs) -> List[Dict[str, Any]]:
        """
        Scrape job listings from Naukri.com.
        
        Args:
            keywords: Job search keywords
            location: Job location
            limit: Maximum number of jobs to fetch
            experience: Experience level in years
            **kwargs: Additional parameters
            
        Returns:
            List of job dictionaries
        """
        jobs = []
        
        # Check cache first
        cache_id = f"naukri_{keywords}_{location}_exp{experience or 'all'}"
        cached_data = self.load_from_cache(cache_id)
        
        if cached_data and len(cached_data) >= limit:
            self.logger.info(f"Using cached data for {keywords} in {location} ({len(cached_data)} jobs)")
            return cached_data[:limit]
        
        try:
            # Format keywords and location for URL
            keywords_encoded = quote(keywords.lower())
            location_encoded = quote(location.lower())
            
            # Base URL format
            if "hyderabad" in location.lower():
                base_url = f"{self.base_url}/{keywords_encoded}-jobs-in-{location_encoded}-secunderabad"
            else:
                base_url = f"{self.base_url}/{keywords_encoded}-jobs-in-{location_encoded}"
            
            # Common query parameters
            query_params = f"?k={keywords_encoded}&l={location_encoded}"
            
            # Add experience parameter if provided
            if experience:
                query_params += f"&experience={experience}"
                
            # Add tracking parameter
            query_params += "&nignbevent_src=jobsearchDeskGNB"
            
            # Pagination loop - using direct URL with page number
            page_num = 1
            max_pages = 10  # Set a reasonable limit
            
            while len(jobs) < limit and page_num <= max_pages:
                # Construct URL for current page
                if page_num == 1:
                    # First page doesn't have a page number in the URL
                    current_url = f"{base_url}{query_params}"
                else:
                    # Pages 2+ have the page number before the query params
                    current_url = f"{base_url}-{page_num}{query_params}"
                
                self.logger.info(f"Navigating to page {page_num}: {current_url}")
                
                # Navigate to the URL
                self.driver.get(current_url)
                self.add_random_delay(3, 5)
                
                # Close any popups
                self.close_popups()
                
                # Wait for job results to load
                try:
                    WebDriverWait(self.driver, 15).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "article.jobTuple, div.jobTupleHeader, .jobTuple, .job-container"))
                    )
                except TimeoutException:
                    self.logger.warning(f"Timed out waiting for job cards on page {page_num}")
                
                # Scroll to load all content
                self.scroll_page(scroll_count=8)
                
                # Get job cards
                job_cards = self.extract_job_cards()
                
                if not job_cards:
                    self.logger.warning(f"No job cards found on page {page_num}")
                    
                    # Take screenshot for debugging on first failed page
                    if page_num == 1:
                        self.driver.save_screenshot(f"naukri_debug_page{page_num}.png")
                        self.logger.info(f"Saved debug screenshot to naukri_debug_page{page_num}.png")
                    
                    # Move to next page
                    page_num += 1
                    continue
                
                self.logger.info(f"Found {len(job_cards)} job cards on page {page_num}")
                
                # Process each job card
                for idx, card in enumerate(job_cards):
                    if len(jobs) >= limit:
                        break
                    
                    try:
                        # Extract job data
                        job_data = self.extract_job_data(card, len(jobs))
                        
                        # Standardize job data
                        std_job_data = self.standardize_job_data(job_data)
                        
                        jobs.append(std_job_data)
                        self.logger.info(f"Added job {len(jobs)}: {std_job_data['title']} at {std_job_data['company']}")
                        
                    except Exception as e:
                        self.logger.error(f"Error extracting job data: {e}")
                        continue
                
                # Move to next page
                page_num += 1
                
                # Add delay between pages
                if page_num <= max_pages and len(jobs) < limit:
                    self.add_random_delay(4, 6)
            
            # Save all jobs to cache
            if jobs:
                self.save_to_cache(jobs, cache_id)
            
            return jobs[:limit]
            
        except Exception as e:
            self.logger.error(f"Error in scraping jobs: {e}")
            return jobs[:limit]
        
    def close(self) -> None:
        """
        Clean up resources.
        """
        if self.driver:
            try:
                self.driver.quit()
                self.logger.info("WebDriver closed")
            except Exception as e:
                self.logger.error(f"Error closing WebDriver: {e}")
            
            # Clean up user data directory after use
            try:
                if os.path.exists(self.user_data_dir):
                    shutil.rmtree(self.user_data_dir, ignore_errors=True)
                    self.logger.info("Cleaned up user data directory")
            except Exception as e:
                self.logger.error(f"Error cleaning up user data directory: {e}")