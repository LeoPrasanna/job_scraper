"""
Main entry point for the job scraper application.
"""

import os
import sys
import logging
import argparse
from typing import Dict, List, Any, Optional
import time

from src.utils.logger import setup_logger
from src.utils.config import get_args
from src.orchestrator.scraper_orchestrator import ScraperOrchestrator


def main() -> int:
    """
    Main function to run the job scraper.
    
    Returns:
        Exit code (0 for success, non-zero for failure)
    """
    try:
        # Set up logger
        logger = setup_logger("main")
        
        # Get command line arguments
        args = get_args()
        
        # Print startup banner
        print("\n" + "="*80)
        print(f"  Job Scraper - Search for '{args.keywords}' in '{args.location}'")
        print("="*80 + "\n")
        
        logger.info(f"Starting job scraper for '{args.keywords}' in '{args.location}'")
        
        # Record start time
        start_time = time.time()
        
        # Create orchestrator
        orchestrator = ScraperOrchestrator(
            cache_dir=args.cache_dir,
            headless=args.headless
        )
        
        try:
            # Run scrapers
            results = orchestrator.run_scrapers(
                keywords=args.keywords,
                location=args.location,
                limit_per_site=50,
                concurrent=True,
                skip_linkedin=args.skip_linkedin,
                skip_naukri=args.skip_naukri,
                skip_timesjobs=args.skip_timesjobs,
                skip_foundit=args.skip_foundit,
                skip_glassdoor=args.skip_glassdoor,
                experience=args.experience,
                linkedin_experience=args.linkedin_experience,
                naukri_experience=args.naukri_experience,
                timesjobs_experience=args.tj_experience,
                foundit_experience=args.foundit_experience,
                glassdoor_experience=args.glassdoor_experience,
                linkedin_pages=args.linkedin_pages,
                linkedin_min_jobs=args.linkedin_min_jobs,
                filter_location=args.filter_location,
                use_api=args.use_api,
                save_html=args.save_html,
                naukri_limit=args.naukri_limit,
                timesjobs_limit=args.timesjobs_limit,
                foundit_limit=args.foundit_limit,
                glassdoor_limit=args.glassdoor_limit,
                glassdoor_email=args.glassdoor_email,
                glassdoor_password=args.glassdoor_password,
                no_full_descriptions=getattr(args, 'no_full_descriptions', False)
            )
            
            # Save results
            output_path = orchestrator.save_results(
                output_format=args.output,
                filename=args.excel_filename,
                output_dir="data",
                keywords=args.keywords
            )
            
            # Print summary
            total_jobs = sum(len(jobs) for jobs in results.values())
            
            print("\n" + "="*80)
            print(f"  Job Scraper Results")
            print("="*80)
            print(f"  Total jobs found: {total_jobs}")
            
            for source, jobs in results.items():
                print(f"  - {source}: {len(jobs)} jobs")
            
            if output_path:
                if args.output.lower() == "google_sheets":
                    print(f"\n  Results saved to Google Sheets: {output_path}")
                else:
                    print(f"\n  Results saved to Excel: {output_path}")
            
            # Calculate and print elapsed time
            elapsed_time = time.time() - start_time
            minutes, seconds = divmod(elapsed_time, 60)
            print(f"\n  Time elapsed: {int(minutes)}m {int(seconds)}s")
            print("="*80 + "\n")
            
            return 0
            
        finally:
            # Always close the orchestrator to release resources
            orchestrator.close()
            
    except KeyboardInterrupt:
        print("\n\nJob scraper interrupted by user.")
        return 130
    except Exception as e:
        logger = logging.getLogger("main")
        logger.error(f"Error running job scraper: {e}", exc_info=True)
        print(f"\nError: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())