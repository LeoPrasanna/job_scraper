"""
Output manager for job scraper results.

This module contains the OutputManager class that handles
saving job data to different formats.
"""

import os
import logging
from typing import Dict, List, Any, Optional, Union

from src.utils.logger import setup_logger
from src.output.excel_handler import ExcelHandler
from src.output.gsheets_handler import GoogleSheetsHandler


class OutputManager:
    """
    Manages output of job scraper results to different formats.
    
    This class uses a factory pattern to create appropriate
    handlers for different output formats.
    """
    
    def __init__(self):
        """
        Initialize the output manager.
        """
        self.logger = setup_logger("output.manager")
        self.excel_handler = ExcelHandler()
        self.gsheets_handler = GoogleSheetsHandler()
    
    def save_to_excel(self, results: Dict[str, List[Dict[str, Any]]], 
                     filename: str = "job_listings.xlsx", **kwargs) -> str:
        """
        Save results to Excel file.
        
        Args:
            results: Dictionary mapping scraper names to lists of jobs
            filename: Output filename
            **kwargs: Additional parameters for Excel output
            
        Returns:
            Path to the saved Excel file
        """
        try:
            self.logger.info(f"Saving results to Excel: {filename}")
            
            total_jobs = sum(len(jobs) for jobs in results.values())
            if total_jobs == 0:
                self.logger.warning("No jobs to save")
                return ""
            
            # Use the Excel handler to save the results
            excel_path = self.excel_handler.save(results, filename, **kwargs)
            
            self.logger.info(f"Successfully saved {total_jobs} jobs to Excel: {excel_path}")
            return excel_path
            
        except Exception as e:
            self.logger.error(f"Error saving to Excel: {e}")
            return ""
    
    def save_to_google_sheets(self, results: Dict[str, List[Dict[str, Any]]], 
                             sheet_title: Optional[str] = None, **kwargs) -> str:
        """
        Save results to Google Sheets.
        
        Args:
            results: Dictionary mapping scraper names to lists of jobs
            sheet_title: Title of the Google Sheet
            **kwargs: Additional parameters for Google Sheets output
            
        Returns:
            URL of the Google Sheet
        """
        try:
            self.logger.info("Saving results to Google Sheets")
            
            total_jobs = sum(len(jobs) for jobs in results.values())
            if total_jobs == 0:
                self.logger.warning("No jobs to save")
                return ""
            
            # Use the Google Sheets handler to save the results
            sheet_url = self.gsheets_handler.save(results, sheet_title, **kwargs)
            
            if sheet_url:
                self.logger.info(f"Successfully saved {total_jobs} jobs to Google Sheets: {sheet_url}")
                return sheet_url
            else:
                self.logger.error("Failed to save to Google Sheets")
                return ""
                
        except Exception as e:
            self.logger.error(f"Error saving to Google Sheets: {e}")
            return ""