"""
Glassdoor job scraper implementation using Selenium with anti-detection measures.
"""

import os
import time
import random
import re
import json
import logging
import shutil
from typing import Dict, List, Any, Optional, Union
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException, NoSuchElementException, 
    ElementClickInterceptedException, StaleElementReferenceException
)
from selenium.webdriver.common.action_chains import ActionChains

from src.scrapers.base_scraper import BaseJobScraper
from src.utils.html_parser import (
    clean_html, create_description_summary,
    extract_salary, extract_experience, extract_job_type
)


class GlassdoorScraper(BaseJobScraper):
    """
    Glassdoor job scraper using Selenium with anti-detection measures.
    """
    
    def __init__(self, 
                cache_dir: str = "cache", 
                headless: bool = False, 
                email: Optional[str] = None, 
                password: Optional[str] = None):
        """
        Initialize Glassdoor scraper.
        
        Args:
            cache_dir: Directory to store cached data
            headless: Whether to run browser in headless mode
            email: Glassdoor login email (optional)
            password: Glassdoor login password (optional)
        """
        super().__init__("Glassdoor", cache_dir)
        
        self.base_url = "https://www.glassdoor.com"
        self.driver = None
        self.headless = headless
        self.email = email
        self.password = password
        self.logged_in = False
        
        # Make user_data_dir unique for each instance
        random_id = str(random.randint(10000, 99999))
        self.user_data_dir = os.path.abspath(f"./chrome_user_data_glassdoor_{random_id}")
        
        # Try to kill Chrome processes before starting
        self._kill_chrome_processes()
            
        # Clean up any existing user data directory
        self.cleanup_user_data_dir()
        
        # Setup Selenium WebDriver
        self.setup_driver()
    
    def _kill_chrome_processes(self) -> None:
        """
        Try to kill running Chrome processes to avoid conflicts.
        """
        try:
            # For Linux/Mac
            os.system("pkill -f chrome > /dev/null 2>&1")
            os.system("pkill -f Chrome > /dev/null 2>&1")
            # For Windows
            os.system("taskkill /f /im chrome.exe > nul 2>&1")
            time.sleep(2)
        except:
            pass
    
    def cleanup_user_data_dir(self) -> None:
        """
        Clean up any existing Chrome user data directory.
        """
        try:
            # Add random identifier to user data directory to avoid conflicts
            random_id = str(random.randint(10000, 99999))
            self.user_data_dir = os.path.abspath(f"./chrome_user_data_glassdoor_{random_id}")
            
            if os.path.exists(self.user_data_dir):
                self.logger.info(f"Cleaning up existing user data directory: {self.user_data_dir}")
                shutil.rmtree(self.user_data_dir, ignore_errors=True)
            
            # Create fresh directory
            os.makedirs(self.user_data_dir, exist_ok=True)
                
        except Exception as e:
            self.logger.error(f"Error cleaning up user data directory: {e}")
    
    def setup_driver(self) -> None:
        """
        Set up Selenium WebDriver with anti-detection measures.
        """
        try:
            options = Options()
            
            # Set unique user data directory to avoid conflicts
            options.add_argument(f"--user-data-dir={self.user_data_dir}")
            
            # Add important arguments to prevent conflicts
            options.add_argument("--no-first-run")
            options.add_argument("--no-default-browser-check")
            options.add_argument("--single-process")
            options.add_argument("--disable-gpu")
            
            if self.headless:
                self.logger.warning("Using headless mode (not recommended for Glassdoor)")
                options.add_argument("--headless=new")
                
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-blink-features=AutomationControlled")
            
            # Disable images to speed up loading
            options.add_argument("--blink-settings=imagesEnabled=false")
            
            # Important to avoid detection
            options.add_argument("--disable-extensions")
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option('useAutomationExtension', False)
            options.add_experimental_option("detach", False)
            
            # Set window size
            options.add_argument("--window-size=1920,1080")
            
            # Add "real" user agent
            options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
            
            # Initialize WebDriver with longer timeout
            self.driver = webdriver.Chrome(options=options)
            self.driver.set_page_load_timeout(30)
            
            # Execute CDP Commands to prevent detection
            self.driver.execute_cdp_cmd('Network.setUserAgentOverride', {
                "userAgent": 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
            })
            
            # Execute JavaScript to prevent webdriver detection
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
            self.logger.info("Selenium WebDriver initialized for Glassdoor")
            
        except Exception as e:
            self.logger.error(f"Error setting up WebDriver: {e}")
            if self.driver:
                self.driver.quit()
            raise
    
    def login(self, force: bool = False) -> bool:
        """
        Log in to Glassdoor if credentials are provided.
        
        Args:
            force: Whether to force login even if already logged in
            
        Returns:
            True if login successful, False otherwise
        """
        if (self.logged_in and not force) or not self.email or not self.password:
            return False
            
        try:
            # Go to the Glassdoor homepage
            self.driver.get(f"{self.base_url}/")
            self.add_random_delay(2, 4)
            
            # First, try closing any popups
            self.close_popups()
            
            # Look for the sign in button
            signin_buttons = self.driver.find_elements(By.CSS_SELECTOR, 
                'a[href*="login"], [data-test="sign-in"], .sign-in, .Login, button:contains("Sign In")')
            
            if signin_buttons:
                for button in signin_buttons:
                    if button.is_displayed():
                        try:
                            button.click()
                            self.add_random_delay(2, 4)
                            break
                        except ElementClickInterceptedException:
                            # Try JavaScript click if normal click fails
                            self.driver.execute_script("arguments[0].click();", button)
                            self.add_random_delay(2, 4)
                            break
            
            # Wait for email field to appear
            email_input = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 
                    'input[name="username"], input[id="modalUserEmail"], input[type="email"], [data-test="email-input"]'))
            )
            
            # Enter email
            email_input.clear()
            # Type like a human with random delays
            for char in self.email:
                email_input.send_keys(char)
                time.sleep(random.uniform(0.05, 0.2))
            
            # Find the continue or next button
            continue_buttons = self.driver.find_elements(By.CSS_SELECTOR, 
                'button[type="submit"], [data-test="continue"], #signInBtn, button:contains("Continue")')
            
            if continue_buttons:
                for button in continue_buttons:
                    if button.is_displayed():
                        button.click()
                        self.add_random_delay(3, 5)
                        break
            
            # Wait for password field to appear
            password_input = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 
                    'input[name="password"], input[id="modalUserPassword"], input[type="password"], [data-test="password-input"]'))
            )
            
            # Enter password
            password_input.clear()
            # Type like a human with random delays
            for char in self.password:
                password_input.send_keys(char)
                time.sleep(random.uniform(0.05, 0.2))
            
            # Find the sign in button
            signin_buttons = self.driver.find_elements(By.CSS_SELECTOR, 
                'button[type="submit"], [data-test="sign-in-button"], #signInSubmit, button:contains("Sign In")')
            
            if signin_buttons:
                for button in signin_buttons:
                    if button.is_displayed():
                        button.click()
                        break
            
            # Add longer delay for login to process
            self.add_random_delay(5, 8)
            
            # Check if login was successful (look for user profile elements)
            try:
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 
                        '.user-photo, .UserIcon, [data-test="user-menu"], header [alt="User"]'))
                )
                self.logger.info("Successfully logged in to Glassdoor")
                self.logged_in = True
                return True
            except TimeoutException:
                self.logger.warning("Login to Glassdoor may have failed - profile element not found")
                return False
                
        except Exception as e:
            self.logger.error(f"Error during Glassdoor login: {e}")
            return False
    
    def close_popups(self) -> None:
        """
        Close any popups that appear on Glassdoor.
        """
        try:
            # Common popup selectors
            popup_selectors = [
                "[data-test='modal-close-button']",
                ".modal_closeIcon",
                ".closeButton",
                "button.close",
                ".modal-close",
                ".modal__close",
                "button.modal_closeButton",
                ".fullScreenModalClose",
                "span.SVGInline.modal_closeIcon",
                "[aria-label='Close']",
                "button.v2__ghostButton [alt='close']",
                "button.v2__ghostButton [alt='Close']"
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
            
            # Try to dismiss cookie consent
            cookie_buttons = self.driver.find_elements(By.CSS_SELECTOR, 
                "#onetrust-accept-btn-handler, .acceptCookies, [data-test='cookie-accept'], button:contains('Accept')")
            for button in cookie_buttons:
                if button.is_displayed():
                    try:
                        self.driver.execute_script("arguments[0].click();", button)
                        time.sleep(1)
                    except:
                        pass
            
            # Try to handle the login wall that appears after a few searches
            login_wall_buttons = self.driver.find_elements(By.CSS_SELECTOR, 
                ".ReactModal__Content button.ContinueAsVisitor, button:contains('Continue as Visitor'), [data-test='continue-as-guest']")
            for button in login_wall_buttons:
                if button.is_displayed():
                    try:
                        self.driver.execute_script("arguments[0].click();", button)
                        time.sleep(1)
                    except:
                        pass
                        
        except Exception as e:
            self.logger.error(f"Error closing popups: {e}")
    
    def scroll_page(self, scroll_count: int = 5) -> None:
        """
        Scroll down the page to load all content with human-like behavior.
        
        Args:
            scroll_count: Number of scroll steps
        """
        try:
            # First get original page height
            last_height = self.driver.execute_script("return document.body.scrollHeight")
            
            # Scroll down in steps
            for i in range(scroll_count):
                # Scroll down to the bottom in steps
                self.driver.execute_script(f"window.scrollBy(0, {random.randint(200, 500)});")
                
                # Add a small random delay between scrolls
                time.sleep(random.uniform(0.5, 2.0))
                
                # Add some randomness to the scrolling pattern (like a human)
                if random.random() < 0.2:  # 20% chance to scroll up a bit
                    self.driver.execute_script(f"window.scrollBy(0, {random.randint(-100, -30)});")
                    time.sleep(random.uniform(0.2, 0.7))
                
                # Check if we've reached the bottom
                new_height = self.driver.execute_script("return document.body.scrollHeight")
                if new_height == last_height:
                    # Try a random scroll to trigger any lazy loading
                    self.driver.execute_script(f"window.scrollBy(0, {random.randint(-200, 200)});")
                    time.sleep(random.uniform(1.0, 2.0))
                    
                    # Check again
                    new_height = self.driver.execute_script("return document.body.scrollHeight")
                    if new_height == last_height:
                        break  # Exit if we're definitely at the bottom
                        
                last_height = new_height
                
            # Scroll back up a bit (human-like behavior)
            self.driver.execute_script("window.scrollBy(0, -300);")
            
        except Exception as e:
            self.logger.error(f"Error scrolling page: {e}")
    
    def construct_search_url(self, keywords: str, location: str) -> str:
        """
        Construct the Glassdoor job search URL.
        
        Args:
            keywords: Job search keywords
            location: Job location
            
        Returns:
            Search URL
        """
        keywords_encoded = keywords.replace(' ', '-').lower()
        location_encoded = location.replace(' ', '-').replace(',', '').lower()
        
        # Glassdoor URL format
        url = f"{self.base_url}/Job/jobs.htm?sc.keyword={keywords_encoded}&locT=C&locId=0&locKeyword={location_encoded}"
        
        return url
    
    def extract_job_cards(self) -> List:
        """
        Extract all job card elements from the page.
        
        Returns:
            List of job card elements
        """
        # Try multiple selectors to find job cards
        selectors = [
            ".react-job-listing",
            "[data-test='jobListing']",
            ".jobCard",
            ".css-1reo4c0",
            "li.job-search-key-1mn3dn8",
            "[data-id^='job-listing-']"
        ]
        
        for selector in selectors:
            cards = self.driver.find_elements(By.CSS_SELECTOR, selector)
            if cards:
                self.logger.info(f"Found {len(cards)} job cards with selector: {selector}")
                return cards
                
        self.logger.warning("No job cards found with standard selectors, trying alternatives")
        
        # Try more generic selectors as fallback
        fallback_selectors = [
            "li.react-job-listing",
            ".jobs-list li",
            "article.job-listing",
            ".css-lohvue"
        ]
        
        for selector in fallback_selectors:
            cards = self.driver.find_elements(By.CSS_SELECTOR, selector)
            if cards:
                self.logger.info(f"Found {len(cards)} job cards with fallback selector: {selector}")
                return cards
        
        self.logger.warning("No job cards found with any selector")
        return []
    
    def extract_job_details_from_card(self, card_element, idx: int) -> Dict[str, Any]:
        """
        Extract basic job details from card without opening it.
        
        Args:
            card_element: Job card element
            idx: Job index
            
        Returns:
            Job data dictionary
        """
        job_data = {
            'job_id': f"glassdoor_{idx}",
            'source': 'Glassdoor'
        }
        
        try:
            # Try to get job title
            title_selectors = [
                "a.jobTitle", 
                "[data-test='job-link']", 
                ".job-title", 
                ".css-1j669t1", 
                "[data-test='job-title']",
                "a.job-link"
            ]
            
            for selector in title_selectors:
                title_elem = card_element.find_elements(By.CSS_SELECTOR, selector)
                if title_elem and len(title_elem) > 0:
                    job_data['title'] = title_elem[0].text.strip()
                    
                    # Try to get job link
                    job_data['apply_url'] = title_elem[0].get_attribute("href")
                    
                    # Try to extract job ID from URL
                    if job_data.get('apply_url'):
                        id_match = re.search(r'jobListingId=(\d+)', job_data['apply_url'])
                        if id_match:
                            job_data['job_id'] = f"glassdoor_{id_match.group(1)}"
                    break
            
            # Company name
            company_selectors = [
                ".employer-name", 
                ".css-1vg6q84", 
                "[data-test='employer-name']",
                "a[data-test='company-name']",
                ".companyInfo .companyName"
            ]
            
            for selector in company_selectors:
                company_elem = card_element.find_elements(By.CSS_SELECTOR, selector)
                if company_elem and len(company_elem) > 0:
                    job_data['company'] = company_elem[0].text.strip()
                    break
            
            # Location
            location_selectors = [
                ".location", 
                ".css-129wfiq", 
                "[data-test='location']",
                ".companyInfo [data-test='location']",
                ".companyLocation"
            ]
            
            for selector in location_selectors:
                location_elem = card_element.find_elements(By.CSS_SELECTOR, selector)
                if location_elem and len(location_elem) > 0:
                    job_data['location'] = location_elem[0].text.strip()
                    break
            
            # Salary
            salary_selectors = [
                ".salary-estimate",
                ".css-1ibu8k1",
                "[data-test='salary-estimate']",
                ".salary"
            ]
            
            for selector in salary_selectors:
                salary_elem = card_element.find_elements(By.CSS_SELECTOR, selector)
                if salary_elem and len(salary_elem) > 0 and salary_elem[0].text.strip():
                    job_data['salary'] = salary_elem[0].text.strip()
                    break
            
            if 'salary' not in job_data:
                job_data['salary'] = 'Not disclosed'
            
            # Posted date
            date_selectors = [
                ".css-1gtap9f",
                ".listing-age",
                "[data-test='job-age']",
                ".job-age"
            ]
            
            for selector in date_selectors:
                date_elem = card_element.find_elements(By.CSS_SELECTOR, selector)
                if date_elem and len(date_elem) > 0:
                    job_data['posted_date'] = date_elem[0].text.strip()
                    break
            
            if 'posted_date' not in job_data:
                job_data['posted_date'] = 'Not specified'
            
            # Job type/employment type (may not be available on all cards)
            job_type_selectors = [
                ".css-1wh2hps",
                ".employmentType",
                "[data-test='job-type']"
            ]
            
            for selector in job_type_selectors:
                job_type_elem = card_element.find_elements(By.CSS_SELECTOR, selector)
                if job_type_elem and len(job_type_elem) > 0:
                    job_data['job_type'] = job_type_elem[0].text.strip()
                    break
            
            if 'job_type' not in job_data:
                job_data['job_type'] = 'Not specified'
            
            return job_data
            
        except Exception as e:
            self.logger.error(f"Error extracting job data from card: {e}")
            # Return job_id and source at minimum
            return job_data
    
    def extract_full_job_details(self, job_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Navigate to job detail page and extract full description and details.
        
        Args:
            job_data: Basic job data with URL
            
        Returns:
            Enhanced job data with full details
        """
        if not job_data.get('apply_url'):
            self.logger.warning(f"No URL to extract details for job: {job_data.get('title', 'Unknown')}")
            job_data['description'] = "No job description available"
            return job_data
        
        try:
            # Navigate to the job detail page
            self.driver.get(job_data['apply_url'])
            self.add_random_delay(3, 6)
            
            # Close any popups
            self.close_popups()
            
            # Wait for job description to load
            try:
                WebDriverWait(self.driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 
                        ".jobDesc, .desc, .job-description, [data-test='jobDesc'], .css-1h2od2b"))
                )
            except TimeoutException:
                self.logger.warning(f"Timed out waiting for job description for {job_data.get('title', 'Unknown')}")
            
            # Scroll down to view the full description
            self.scroll_page(scroll_count=3)
            
            # Extract job description
            desc_selectors = [
                ".jobDesc", 
                ".desc", 
                ".job-description", 
                "[data-test='jobDesc']",
                ".css-1h2od2b"
            ]
            
            description = "No job description available"
            
            for selector in desc_selectors:
                desc_elems = self.driver.find_elements(By.CSS_SELECTOR, selector)
                if desc_elems and len(desc_elems) > 0:
                    description = desc_elems[0].text.strip()
                    break
            
            job_data['description'] = description
            
            # Try to get more details that weren't in the card
            
            # Company rating
            rating_selectors = [
                ".employerStats", 
                ".rating", 
                "[data-test='rating']",
                ".css-1buaf54"
            ]
            
            for selector in rating_selectors:
                rating_elems = self.driver.find_elements(By.CSS_SELECTOR, selector)
                if rating_elems and len(rating_elems) > 0:
                    job_data['company_rating'] = rating_elems[0].text.strip()
                    break
            
            # Reviews count
            reviews_selectors = [
                ".count", 
                ".reviews", 
                "[data-test='reviews-count']",
                ".css-165r5b7"
            ]
            
            for selector in reviews_selectors:
                reviews_elems = self.driver.find_elements(By.CSS_SELECTOR, selector)
                if reviews_elems and len(reviews_elems) > 0:
                    job_data['reviews_count'] = reviews_elems[0].text.strip()
                    break
            
            # Company size/employees
            size_selectors = [
                ".infoEntity [data-test='employer-size']",
                ".css-1pldt9b .css-1ywhvd1",
                ".infoEntity:contains('Size') .css-1pldt9b"
            ]
            
            for selector in size_selectors:
                size_elems = self.driver.find_elements(By.CSS_SELECTOR, selector)
                if size_elems and len(size_elems) > 0:
                    job_data['company_size'] = size_elems[0].text.strip()
                    break
            
            # Industry
            industry_selectors = [
                ".infoEntity [data-test='employer-industry']",
                ".css-1pldt9b .css-1ywhvd1",
                ".infoEntity:contains('Industry') .css-1pldt9b"
            ]
            
            for selector in industry_selectors:
                industry_elems = self.driver.find_elements(By.CSS_SELECTOR, selector)
                if industry_elems and len(industry_elems) > 0:
                    job_data['industry'] = industry_elems[0].text.strip()
                    break
            
            return job_data
            
        except Exception as e:
            self.logger.error(f"Error extracting full job details: {e}")
            if 'description' not in job_data:
                job_data['description'] = "Error extracting job description"
            return job_data
    
    def go_to_next_page(self) -> bool:
        """
        Attempt to navigate to the next page of job listings.
        
        Returns:
            True if successfully navigated to next page, False otherwise
        """
        try:
            # Find next page button with various selectors
            next_button_selectors = [
                ".nextButton",
                ".next",
                "[data-test='pagination-next']",
                "button[data-direction='next']",
                ".css-1etjk41",
                "button.css-1qx7vym[aria-label='Next']",
                ".pages li:last-child a"
            ]
            
            for selector in next_button_selectors:
                next_buttons = self.driver.find_elements(By.CSS_SELECTOR, selector)
                for button in next_buttons:
                    if button.is_displayed():
                        # Check if the button is disabled
                        disabled = button.get_attribute("disabled") == "true" or "disabled" in button.get_attribute("class") or not button.is_enabled()
                        
                        if disabled:
                            self.logger.info("Next page button is disabled - reached end of results")
                            return False
                        
                        try:
                            # Scroll the button into view
                            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
                            time.sleep(1)
                            
                            # Try normal click first
                            button.click()
                            self.add_random_delay(3, 6)
                            return True
                        except ElementClickInterceptedException:
                            # If normal click fails, try JavaScript click
                            self.driver.execute_script("arguments[0].click();", button)
                            self.add_random_delay(3, 6)
                            return True
            
            # If we couldn't find a next button, try to find the current page and click the next one
            current_page = 0
            page_links = self.driver.find_elements(By.CSS_SELECTOR, ".paginationFooter li, .pagination li, [data-test='pagination-link']")
            
            for link in page_links:
                if "selected" in link.get_attribute("class") or "active" in link.get_attribute("class"):
                    try:
                        current_page = int(link.text.strip())
                        break
                    except:
                        pass
            
            if current_page > 0:
                # Try to find and click the next page number
                next_page = current_page + 1
                next_page_links = self.driver.find_elements(By.CSS_SELECTOR, f".paginationFooter li, .pagination li, [data-test='pagination-link']")
                
                for link in next_page_links:
                    try:
                        if int(link.text.strip()) == next_page:
                            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", link)
                            time.sleep(1)
                            link.click()
                            self.add_random_delay(3, 6)
                            return True
                    except:
                        pass
            
            # If all above methods fail, try URL-based pagination
            current_url = self.driver.current_url
            if "p=" in current_url:
                # Extract current page number from URL
                match = re.search(r'p=(\d+)', current_url)
                if match:
                    current_page = int(match.group(1))
                    next_page = current_page + 1
                    next_url = current_url.replace(f"p={current_page}", f"p={next_page}")
                    self.driver.get(next_url)
                    self.add_random_delay(3, 6)
                    return True
            else:
                # Add page parameter to URL
                if "?" in current_url:
                    next_url = f"{current_url}&p=2"
                else:
                    next_url = f"{current_url}?p=2"
                self.driver.get(next_url)
                self.add_random_delay(3, 6)
                return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"Error navigating to next page: {e}")
            return False
    
    def scrape_jobs(self, 
                   keywords: str, 
                   location: str, 
                   limit: int = 50, 
                   experience: Optional[str] = None, 
                   **kwargs) -> List[Dict[str, Any]]:
        """
        Scrape job listings from Glassdoor.
        
        Args:
            keywords: Job search keywords
            location: Job location
            limit: Maximum number of jobs to fetch
            experience: Experience level in years
            **kwargs: Additional parameters:
                - get_full_description: Whether to navigate to each job's detail page
                
        Returns:
            List of job dictionaries
        """
        # Get additional parameters
        get_full_description = kwargs.get('get_full_description', True)
        
        # Check cache first
        cache_id = f"glassdoor_{keywords}_{location}_exp{experience or 'all'}"
        cached_data = self.load_from_cache(cache_id)
        
        if cached_data and len(cached_data) >= limit:
            self.logger.info(f"Using cached data for {keywords} in {location} ({len(cached_data)} jobs)")
            return cached_data[:limit]
        
        jobs = []
        
        try:
            # Construct the search URL
            search_url = self.construct_search_url(keywords, location)
            self.logger.info(f"Using search URL: {search_url}")
            
            # Navigate to the search URL
            self.driver.get(search_url)
            self.add_random_delay(3, 6)
            
            # Close any popups
            self.close_popups()
            
            # Check if we should try to log in
            if self.email and self.password and not self.logged_in:
                self.login()
            
            # Handle the initial page
            page_num = 1
            max_pages = 10  # Set a reasonable limit
            
            while len(jobs) < limit and page_num <= max_pages:
                # Wait for job listings to load
                try:
                    self.logger.info(f"Waiting for job listings on page {page_num}")
                    WebDriverWait(self.driver, 15).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, 
                            ".react-job-listing, [data-test='jobListing'], .jobCard"))
                    )
                except TimeoutException:
                    self.logger.warning(f"Timed out waiting for job cards on page {page_num}")
                
                # Scroll to load all content
                self.scroll_page(scroll_count=5)
                
                # Close any popups again (they can appear during scrolling)
                self.close_popups()
                
                # Get job cards
                job_cards = self.extract_job_cards()
                
                if not job_cards:
                    self.logger.warning(f"No job cards found on page {page_num}")
                    
                    # Take screenshot for debugging on first failed page
                    if page_num == 1:
                        screenshot_path = os.path.join(self.cache_dir, f"glassdoor_debug_page{page_num}.png")
                        self.driver.save_screenshot(screenshot_path)
                        self.logger.info(f"Saved debug screenshot to {screenshot_path}")
                    
                    # Try to move to next page
                    if not self.go_to_next_page():
                        self.logger.info("Cannot go to next page - reached end of results or error")
                        break
                    
                    page_num += 1
                    continue
                
                self.logger.info(f"Found {len(job_cards)} job cards on page {page_num}")
                
                # Process each job card
                for idx, card in enumerate(job_cards):
                    if len(jobs) >= limit:
                        break
                    
                    try:
                        # Extract basic job data from card
                        job_data = self.extract_job_details_from_card(card, len(jobs))
                        
                        # Get full job description if requested
                        if get_full_description and job_data.get('apply_url'):
                            job_data = self.extract_full_job_details(job_data)
                            # Return to search results
                            self.driver.back()
                            self.add_random_delay(2, 4)
                            # Close any popups again
                            self.close_popups()
                        
                        # Standardize job data
                        std_job_data = self.standardize_job_data(job_data)
                        
                        jobs.append(std_job_data)
                        self.logger.info(f"Added job {len(jobs)}: {std_job_data.get('title', 'Unknown')} at {std_job_data.get('company', 'Unknown')}")
                        
                        # Add a small delay between processing cards (appear more human-like)
                        time.sleep(random.uniform(0.5, 1.5))
                        
                    except Exception as e:
                        self.logger.error(f"Error processing job card {idx}: {e}")
                        continue
                
                # Try to move to next page if we haven't reached the limit
                if len(jobs) < limit:
                    if not self.go_to_next_page():
                        self.logger.info("Cannot go to next page - reached end of results or error")
                        break
                    
                    page_num += 1
                else:
                    break
            
            # Save to cache
            if jobs:
                self.save_to_cache(jobs, cache_id)
            
            return jobs[:limit]
            
        except Exception as e:
            self.logger.error(f"Error in scraping Glassdoor jobs: {e}")
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