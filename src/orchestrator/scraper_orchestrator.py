"""
Scraper orchestrator module.

This module coordinates the execution of multiple job scrapers
and handles error management, caching, and result aggregation.
"""

import os
import time
import logging
import concurrent.futures
from typing import Dict, List, Any, Optional, Union, Tuple
from datetime import datetime
import traceback

from src.scrapers import (
    BaseJobScraper,
    LinkedInScraper,
    NaukriScraper,
    TimesJobsScraper,
    FounditScraper,
    GlassdoorScraper
)
from src.utils.logger import setup_logger
from src.output.output_manager import OutputManager


class ScraperOrchestrator:
    """
    Orchestrates the execution of multiple job scrapers.
    
    This class initializes and manages all the job scrapers,
    runs them concurrently or sequentially, and handles
    error management and result aggregation.
    """
    
    def __init__(self, cache_dir: str = "cache", headless: bool = True):
        """
        Initialize the orchestrator.
        
        Args:
            cache_dir: Directory to store cached data
            headless: Whether to run browser-based scrapers in headless mode
        """
        self.cache_dir = cache_dir
        self.headless = headless
        self.logger = setup_logger("orchestrator")
        
        # Dictionary to store scraper instances
        self.scrapers = {}
        
        # Set to track which scrapers have been initialized
        self.initialized_scrapers = set()
        
        # Dictionary to store scraping results
        self.results = {}
        
        # Dictionary to store execution metrics
        self.metrics = {}
        
        # Output manager
        self.output_manager = OutputManager()
        
        # Create cache directory if it doesn't exist
        if not os.path.exists(cache_dir):
            os.makedirs(cache_dir)
    
    def _get_scraper(self, name: str, **kwargs) -> BaseJobScraper:
        """
        Get a scraper instance for the given name.
        
        Args:
            name: Name of the scraper
            **kwargs: Additional parameters for the scraper
            
        Returns:
            Scraper instance
            
        Raises:
            ValueError: If the scraper name is not recognized
        """
        # Check if the scraper instance already exists
        if name in self.scrapers:
            return self.scrapers[name]
        
        # Initialize a new scraper instance
        if name.lower() == "linkedin":
            save_html = kwargs.get('save_html', False)
            scraper = LinkedInScraper(cache_dir=self.cache_dir, save_html=save_html)
        elif name.lower() == "naukri":
            scraper = NaukriScraper(cache_dir=self.cache_dir, headless=self.headless)
        elif name.lower() == "timesjobs":
            scraper = TimesJobsScraper(cache_dir=self.cache_dir)
        elif name.lower() == "foundit":
            scraper = FounditScraper(cache_dir=self.cache_dir)
        elif name.lower() == "glassdoor":
            email = kwargs.get('glassdoor_email')
            password = kwargs.get('glassdoor_password')
            scraper = GlassdoorScraper(
                cache_dir=self.cache_dir, 
                headless=self.headless,
                email=email,
                password=password
            )
        else:
            raise ValueError(f"Unknown scraper: {name}")
        
        # Store the scraper instance
        self.scrapers[name] = scraper
        
        # Add to initialized scrapers set
        self.initialized_scrapers.add(name)
        
        return scraper
    
    def _run_scraper(self, name: str, keywords: str, location: str, limit: int, 
                   experience: Optional[str] = None, **kwargs) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Run a single scraper.
        
        Args:
            name: Name of the scraper
            keywords: Job search keywords
            location: Job location
            limit: Maximum number of jobs to fetch
            experience: Experience level
            **kwargs: Additional parameters for the scraper
            
        Returns:
            Tuple of (scraper name, job results)
        """
        start_time = time.time()
        
        # Initialize metrics for this scraper
        self.metrics[name] = {
            'start_time': start_time,
            'end_time': None,
            'duration': None,
            'success': False,
            'job_count': 0,
            'error': None
        }
        
        try:
            self.logger.info(f"Starting {name} scraper for '{keywords}' in '{location}'")
            
            # Get the scraper instance
            scraper = self._get_scraper(name, **kwargs)
            
            # Extract scraper-specific parameters
            scraper_kwargs = {}
            
            # LinkedIn-specific parameters
            if name.lower() == "linkedin":
                scraper_kwargs['num_pages'] = kwargs.get('linkedin_pages', 10)
                scraper_kwargs['filter_location'] = kwargs.get('filter_location')
                scraper_kwargs['use_api'] = kwargs.get('use_api', False)
            
            # Glassdoor-specific parameters
            if name.lower() == "glassdoor":
                scraper_kwargs['get_full_description'] = not kwargs.get('no_full_descriptions', False)
            
            # Run the scraper
            jobs = scraper.scrape_jobs(keywords, location, limit, experience, **scraper_kwargs)
            
            # Update metrics
            end_time = time.time()
            self.metrics[name]['end_time'] = end_time
            self.metrics[name]['duration'] = end_time - start_time
            self.metrics[name]['success'] = True
            self.metrics[name]['job_count'] = len(jobs)
            
            self.logger.info(f"Successfully scraped {len(jobs)} jobs from {name}")
            return name, jobs
            
        except Exception as e:
            # Log the error
            self.logger.error(f"Error in {name} scraper: {e}")
            self.logger.error(traceback.format_exc())
            
            # Update metrics
            end_time = time.time()
            self.metrics[name]['end_time'] = end_time
            self.metrics[name]['duration'] = end_time - start_time
            self.metrics[name]['success'] = False
            self.metrics[name]['error'] = str(e)
            
            # Return empty results
            return name, []
    
    def run_scrapers(self, 
                    keywords: str, 
                    location: str, 
                    limit_per_site: int = 50,
                    concurrent: bool = True,
                    **kwargs) -> Dict[str, List[Dict[str, Any]]]:
        """
        Run all specified scrapers.
        
        Args:
            keywords: Job search keywords
            location: Job location
            limit_per_site: Maximum number of jobs to fetch per site
            concurrent: Whether to run scrapers concurrently
            **kwargs: Additional parameters:
                - skip_linkedin: Whether to skip LinkedIn scraper
                - skip_naukri: Whether to skip Naukri scraper
                - skip_timesjobs: Whether to skip TimesJobs scraper
                - skip_foundit: Whether to skip Foundit scraper
                - skip_glassdoor: Whether to skip Glassdoor scraper
                - experience: Experience level for all sites
                - linkedin_experience: Experience value for LinkedIn
                - naukri_experience: Experience value for Naukri
                - timesjobs_experience: Experience value for TimesJobs
                - foundit_experience: Experience value for Foundit
                - glassdoor_experience: Experience value for Glassdoor
                - linkedin_pages: Number of LinkedIn pages to scrape
                - linkedin_min_jobs: Minimum number of LinkedIn jobs to scrape
                - filter_location: Additional location filter for LinkedIn
                - use_api: Whether to use LinkedIn API endpoint
                - glassdoor_email: Glassdoor login email
                - glassdoor_password: Glassdoor login password
                
        Returns:
            Dictionary mapping scraper names to lists of jobs
        """
        # Reset results
        self.results = {}
        
        # Determine which scrapers to run
        scrapers_to_run = []
        
        if not kwargs.get('skip_linkedin', False):
            scrapers_to_run.append("linkedin")
            
        if not kwargs.get('skip_naukri', False):
            scrapers_to_run.append("naukri")
            
        if not kwargs.get('skip_timesjobs', False):
            scrapers_to_run.append("timesjobs")
            
        if not kwargs.get('skip_foundit', False):
            scrapers_to_run.append("foundit")
            
        if not kwargs.get('skip_glassdoor', False):
            scrapers_to_run.append("glassdoor")
        
        # Determine experience values for each scraper
        experience_values = {}
        general_experience = kwargs.get('experience')
        
        for scraper in scrapers_to_run:
            # Use scraper-specific experience if provided, otherwise use general experience
            experience_values[scraper] = kwargs.get(f'{scraper}_experience', general_experience)
        
        # Adjust limits for each scraper if specified
        limits = {}
        for scraper in scrapers_to_run:
            limits[scraper] = kwargs.get(f'{scraper}_limit', limit_per_site)
        
        # Run the scrapers
        self.logger.info(f"Starting to scrape jobs for '{keywords}' in '{location}'")
        self.logger.info(f"Scrapers: {', '.join(scrapers_to_run)}")
        
        # Record overall start time
        overall_start_time = time.time()
        
        if concurrent and len(scrapers_to_run) > 1:
            # Run scrapers concurrently
            self.logger.info("Running scrapers concurrently")
            
            # Create tasks for each scraper
            tasks = []
            for scraper in scrapers_to_run:
                tasks.append((
                    scraper, 
                    keywords, 
                    location, 
                    limits[scraper], 
                    experience_values[scraper],
                    kwargs
                ))
            
            # Run tasks with ThreadPoolExecutor
            with concurrent.futures.ThreadPoolExecutor(max_workers=len(scrapers_to_run)) as executor:
                futures = [
                    executor.submit(
                        self._run_scraper, 
                        name, keywords, location, limit, experience, **kwargs
                    ) 
                    for name, keywords, location, limit, experience, kwargs in tasks
                ]
                
                # Collect results as they complete
                for future in concurrent.futures.as_completed(futures):
                    try:
                        name, jobs = future.result()
                        self.results[name] = jobs
                    except Exception as e:
                        self.logger.error(f"Error in concurrent execution: {e}")
        else:
            # Run scrapers sequentially
            self.logger.info("Running scrapers sequentially")
            
            for scraper in scrapers_to_run:
                name, jobs = self._run_scraper(
                    scraper, 
                    keywords, 
                    location, 
                    limits[scraper], 
                    experience_values[scraper],
                    **kwargs
                )
                self.results[name] = jobs
        
        # Record overall end time
        overall_end_time = time.time()
        self.metrics['overall'] = {
            'start_time': overall_start_time,
            'end_time': overall_end_time,
            'duration': overall_end_time - overall_start_time,
            'job_count': sum(len(jobs) for jobs in self.results.values())
        }
        
        # Log results
        total_jobs = sum(len(jobs) for jobs in self.results.values())
        self.logger.info(f"Scraping completed. Found {total_jobs} jobs across {len(scrapers_to_run)} sites.")
        
        for name, jobs in self.results.items():
            self.logger.info(f"{name}: {len(jobs)} jobs")
        
        return self.results
    
    def save_results(self, output_format: str = "excel", filename: str = "job_listings.xlsx", 
                    output_dir: str = "data", **kwargs) -> Optional[str]:
        """
        Save the scraped results to the specified format.
        
        Args:
            output_format: Output format (excel or google_sheets)
            filename: Output filename for Excel
            output_dir: Output directory
            **kwargs: Additional parameters for output
            
        Returns:
            Path to the saved file or URL of the Google Sheet
        """
        # Check if results exist
        if not self.results:
            self.logger.warning("No results to save")
            return None
        
        # Create output directory if it doesn't exist
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        # Save based on the specified format
        if output_format.lower() == "excel":
            excel_path = os.path.join(output_dir, filename)
            self.output_manager.save_to_excel(self.results, excel_path, **kwargs)
            self.logger.info(f"Results saved to Excel: {excel_path}")
            return excel_path
            
        elif output_format.lower() == "google_sheets":
            sheet_title = kwargs.get('sheet_title', f"Job Listings - {datetime.now().strftime('%Y-%m-%d')}")
            sheet_url = self.output_manager.save_to_google_sheets(self.results, sheet_title, **kwargs)
            
            if sheet_url:
                self.logger.info(f"Results saved to Google Sheets: {sheet_url}")
                return sheet_url
            else:
                self.logger.error("Failed to save to Google Sheets")
                
                # Fallback to Excel
                self.logger.info("Falling back to Excel output")
                excel_path = os.path.join(output_dir, filename)
                self.output_manager.save_to_excel(self.results, excel_path, **kwargs)
                self.logger.info(f"Results saved to Excel: {excel_path}")
                return excel_path
        else:
            self.logger.error(f"Unknown output format: {output_format}")
            return None
    
    def close(self) -> None:
        """
        Close all scraper resources.
        """
        for name, scraper in self.scrapers.items():
            try:
                self.logger.info(f"Closing {name} scraper")
                scraper.close()
            except Exception as e:
                self.logger.error(f"Error closing {name} scraper: {e}")
    
    def get_execution_metrics(self) -> Dict[str, Any]:
        """
        Get execution metrics for the scrapers.
        
        Returns:
            Dictionary of execution metrics
        """
        return self.metrics