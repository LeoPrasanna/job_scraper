"""
Google Sheets output handler for job scraper results.
"""

import os
import logging
import re
from typing import Dict, List, Any, Optional, Union
import pandas as pd
from datetime import datetime
import json
from tenacity import retry, stop_after_attempt, wait_exponential, before_sleep_log, retry_if_exception_type
from googleapiclient.errors import HttpError

from src.utils.logger import setup_logger
from src.utils.config import get_google_credentials


class GoogleSheetsHandler:
    """
    Handler for saving job data to Google Sheets.
    """
    
    def __init__(self):
        """
        Initialize the Google Sheets handler.
        """
        self.logger = setup_logger("output.gsheets")
    
    def authenticate(self):
        """
        Authenticate with Google Sheets API.
        
        Tries multiple authentication methods in the following order:
        1. Workload Identity Federation (for GitHub Actions)
        2. Application Default Credentials
        3. Service account key file
        
        Returns:
            Tuple of (sheets_service, drive_service) or None if authentication fails
        """
        try:
            from googleapiclient.discovery import build
            from google.oauth2 import service_account
            import google.auth
            from google.auth.exceptions import DefaultCredentialsError
            
            # First, try Workload Identity Federation or Application Default Credentials
            try:
                self.logger.info("Attempting to authenticate using default credentials (e.g., Workload Identity)")
                credentials, project = google.auth.default(
                    scopes=['https://www.googleapis.com/auth/spreadsheets',
                           'https://www.googleapis.com/auth/drive']
                )
                
                if credentials:
                    sheets_service = build('sheets', 'v4', credentials=credentials)
                    drive_service = build('drive', 'v3', credentials=credentials)
                    
                    self.logger.info("Successfully authenticated using default credentials")
                    return sheets_service, drive_service
            except (DefaultCredentialsError, Exception) as e:
                self.logger.warning(f"Default credentials authentication failed: {e}")
            
            # Fall back to service account key file
            creds_path = get_google_credentials()
            
            if not creds_path:
                self.logger.error("No Google Sheets credentials found and default auth failed")
                return None, None
            
            # Try service account authentication
            try:
                if os.path.isfile(creds_path):
                    # Use service account credentials from file
                    scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
                    creds = service_account.Credentials.from_service_account_file(creds_path, scopes=scopes)
                else:
                    # The credentials are provided as JSON string
                    try:
                        service_account_info = json.loads(creds_path)
                        scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
                        creds = service_account.Credentials.from_service_account_info(
                            service_account_info, scopes=scopes)
                    except json.JSONDecodeError:
                        self.logger.error("Invalid credentials JSON")
                        return None, None
                
                # Build services
                sheets_service = build('sheets', 'v4', credentials=creds)
                drive_service = build('drive', 'v3', credentials=creds)
                
                self.logger.info("Successfully authenticated using service account")
                return sheets_service, drive_service
                
            except Exception as auth_err:
                self.logger.error(f"Service account authentication failed: {auth_err}")
                return None, None
                
        except ImportError:
            self.logger.error("Google API client libraries not installed")
            return None, None
        except Exception as e:
            self.logger.error(f"Error authenticating with Google Sheets API: {e}")
            return None, None
    
    @retry(
        stop=stop_after_attempt(3), 
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((HttpError, ConnectionError)),
        before_sleep=before_sleep_log(logging.getLogger("output.gsheets"), logging.WARNING)
    )
    def _create_spreadsheet(self, sheets_service, title):
        """
        Create a new Google Spreadsheet with retry logic.
        
        Args:
            sheets_service: Google Sheets service
            title: Spreadsheet title
            
        Returns:
            Spreadsheet ID
        """
        spreadsheet = {
            'properties': {'title': title},
            'sheets': [
                {'properties': {'title': 'All Jobs'}},
                {'properties': {'title': 'LinkedIn'}},
                {'properties': {'title': 'Naukri.com'}},
                {'properties': {'title': 'TimesJobs'}},
                {'properties': {'title': 'Foundit'}},
                {'properties': {'title': 'Glassdoor'}}
            ]
        }
        
        spreadsheet = sheets_service.spreadsheets().create(body=spreadsheet).execute()
        return spreadsheet['spreadsheetId']
    
    @retry(
        stop=stop_after_attempt(3), 
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((HttpError, ConnectionError)),
        before_sleep=before_sleep_log(logging.getLogger("output.gsheets"), logging.WARNING)
    )
    def _create_sharing_permission(self, drive_service, file_id):
        """
        Create a view-only sharing permission for the spreadsheet with retry logic.
        
        Args:
            drive_service: Google Drive service
            file_id: Spreadsheet ID
            
        Returns:
            Permission ID
        """
        permission = {
            'type': 'anyone',
            'role': 'reader'
        }
        
        permission = drive_service.permissions().create(
            fileId=file_id,
            body=permission
        ).execute()
        
        return permission.get('id')
    
    @retry(
        stop=stop_after_attempt(3), 
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((HttpError, ConnectionError)),
        before_sleep=before_sleep_log(logging.getLogger("output.gsheets"), logging.WARNING)
    )
    def _get_sharing_link(self, drive_service, file_id):
        """
        Get the sharing link for the spreadsheet with retry logic.
        
        Args:
            drive_service: Google Drive service
            file_id: Spreadsheet ID
            
        Returns:
            Shareable link
        """
        file = drive_service.files().get(
            fileId=file_id,
            fields='webViewLink'
        ).execute()
        
        return file.get('webViewLink')
    
    @retry(
        stop=stop_after_attempt(3), 
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((HttpError, ConnectionError)),
        before_sleep=before_sleep_log(logging.getLogger("output.gsheets"), logging.WARNING)
    )
    def _update_sheet(self, sheets_service, spreadsheet_id, sheet_name, data_df):
        """
        Update a sheet in the spreadsheet with data using retry logic.
        
        Args:
            sheets_service: Google Sheets service
            spreadsheet_id: Spreadsheet ID
            sheet_name: Sheet name
            data_df: DataFrame with data to update
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Check if the sheet exists
            sheet_metadata = sheets_service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
            sheets = sheet_metadata.get('sheets', [])
            sheet_exists = False
            sheet_id = None
            
            # Find the sheet ID
            for sheet in sheets:
                if sheet['properties']['title'] == sheet_name:
                    sheet_exists = True
                    sheet_id = sheet['properties']['sheetId']
                    break
            
            # If the sheet doesn't exist, create it
            if not sheet_exists:
                request = {
                    'addSheet': {
                        'properties': {
                            'title': sheet_name
                        }
                    }
                }
                
                response = sheets_service.spreadsheets().batchUpdate(
                    spreadsheetId=spreadsheet_id,
                    body={'requests': [request]}
                ).execute()
                
                sheet_id = response['replies'][0]['addSheet']['properties']['sheetId']
            
            # Convert DataFrame to values
            values = [data_df.columns.tolist()]
            values.extend(data_df.values.tolist())
            
            # Clean the values to handle complex objects
            for i in range(len(values)):
                for j in range(len(values[i])):
                    if not isinstance(values[i][j], (str, int, float, bool)) or values[i][j] is None:
                        values[i][j] = str(values[i][j])
            
            # Clear the sheet first
            sheets_service.spreadsheets().values().clear(
                spreadsheetId=spreadsheet_id,
                range=f"{sheet_name}!A1:Z50000"
            ).execute()
            
            # Update the sheet with values
            sheets_service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range=f"{sheet_name}!A1",
                valueInputOption="RAW",
                body={"values": values}
            ).execute()
            
            # Apply formatting
            requests = [
                # Format header row
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": 0,
                            "endRowIndex": 1
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "backgroundColor": {
                                    "red": 0.2,
                                    "green": 0.2,
                                    "blue": 0.8,
                                    "alpha": 1
                                },
                                "textFormat": {
                                    "bold": True,
                                    "foregroundColor": {
                                        "red": 1.0,
                                        "green": 1.0,
                                        "blue": 1.0,
                                        "alpha": 1
                                    }
                                },
                                "horizontalAlignment": "CENTER",
                                "verticalAlignment": "MIDDLE",
                                "wrapStrategy": "WRAP"
                            }
                        },
                        "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment,wrapStrategy)"
                    }
                },
                # Freeze header row
                {
                    "updateSheetProperties": {
                        "properties": {
                            "sheetId": sheet_id,
                            "gridProperties": {
                                "frozenRowCount": 1
                            }
                        },
                        "fields": "gridProperties.frozenRowCount"
                    }
                }
            ]
            
            # Add column width adjustments
            column_width_requests = []
            
            for idx, column in enumerate(data_df.columns):
                # Set width based on content type
                if column == 'description':
                    width = 400
                elif column == 'description_summary':
                    width = 300
                elif column in ['title', 'company', 'skills']:
                    width = 200
                elif column in ['location', 'source', 'job_type']:
                    width = 150
                elif column in ['salary', 'experience', 'posted_date']:
                    width = 120
                else:
                    width = 150
                
                column_width_requests.append({
                    "updateDimensionProperties": {
                        "range": {
                            "sheetId": sheet_id,
                            "dimension": "COLUMNS",
                            "startIndex": idx,
                            "endIndex": idx + 1
                        },
                        "properties": {
                            "pixelSize": width
                        },
                        "fields": "pixelSize"
                    }
                })
            
            # Add column width requests to the main requests
            requests.extend(column_width_requests)
            
            # Apply all formatting
            sheets_service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={"requests": requests}
            ).execute()
            
            return True
        
        except HttpError as e:
            if e.resp.status in [429, 500, 502, 503, 504]:
                self.logger.warning(f"Temporary API error: {e.resp.status}")
                raise  # Let retry handle it
            else:
                self.logger.error(f"Non-retryable API error: {e}")
                return False
        except Exception as e:
            self.logger.error(f"Error updating sheet {sheet_name}: {e}")
            return False
    
    def save(self, results: Dict[str, List[Dict[str, Any]]], 
            sheet_title: Optional[str] = None, **kwargs) -> str:
        """
        Save job data to Google Sheets.
        
        Args:
            results: Dictionary mapping scraper names to lists of jobs
            sheet_title: Title for the sheet (defaults to "Job Listings - YYYY-MM-DD")
            **kwargs: Additional parameters for Google Sheets output
            
        Returns:
            URL of the Google Sheet
        """
        try:
            # Check if we have any results
            if not results or all(not jobs for jobs in results.values()):
                self.logger.warning("No job data to save")
                return ""
            
            # Authenticate
            auth_result = self.authenticate()
            if not auth_result:
                self.logger.error("Failed to authenticate with Google Sheets API")
                return ""
            
            sheets_service, drive_service = auth_result
            
            # Generate sheet title if not provided
            if not sheet_title:
                keywords = kwargs.get('keywords', 'jobs')
                if not isinstance(keywords, str):
                    keywords = "jobs"
                
                # Sanitize keywords for use in title
                keywords = re.sub(r'[^\w\s-]', '', keywords).strip().lower().replace(' ', '_')
                today = datetime.now().strftime("%b_%d_%Y")
                sheet_title = f"jobslist_{keywords}_{today}"
            
            # Create a new spreadsheet
            try:
                spreadsheet_id = self._create_spreadsheet(sheets_service, sheet_title)
            except Exception as e:
                self.logger.error(f"Failed to create spreadsheet: {e}")
                return ""
                
            # Convert job data to DataFrames
            dfs = {}
            all_jobs = []
            
            for source, jobs in results.items():
                if not jobs:
                    continue
                
                df = pd.DataFrame(jobs)
                dfs[source] = df
                
                # Add all jobs to the combined DataFrame
                all_jobs.extend(jobs)
            
            if not all_jobs:
                self.logger.warning("No job data after processing")
                return ""
            
            # Create a combined DataFrame
            all_jobs_df = pd.DataFrame(all_jobs)
            
            # Define standard column order
            columns_order = [
                'job_id', 'title', 'company', 'location', 'experience', 
                'salary', 'job_type', 'posted_date', 'description_summary',
                'description', 'skills', 'industry', 'education', 'apply_url', 'source'
            ]
            
            # Function to reorder columns
            def reorder_columns(df):
                # Get columns that exist in the DataFrame
                available_columns = [col for col in columns_order if col in df.columns]
                
                # Add any columns not in our standard order
                extra_columns = [col for col in df.columns if col not in columns_order]
                available_columns.extend(extra_columns)
                
                # Return reordered DataFrame
                return df[available_columns]
            
            # Reorder columns in all DataFrames
            all_jobs_df = reorder_columns(all_jobs_df)
            
            for source in dfs:
                dfs[source] = reorder_columns(dfs[source])
            
            # Update the "All Jobs" sheet
            try:
                self._update_sheet(sheets_service, spreadsheet_id, "All Jobs", all_jobs_df)
            except Exception as e:
                self.logger.error(f"Failed to update All Jobs sheet: {e}")
            
            # Update individual source sheets
            for source, df in dfs.items():
                sheet_name = source
                if sheet_name.lower() == "naukri":
                    sheet_name = "Naukri.com"
                
                try:
                    self._update_sheet(sheets_service, spreadsheet_id, sheet_name, df)
                except Exception as e:
                    self.logger.error(f"Failed to update {sheet_name} sheet: {e}")
            
            # Set sharing permissions
            try:
                self._create_sharing_permission(drive_service, spreadsheet_id)
            except Exception as e:
                self.logger.error(f"Failed to set sharing permissions: {e}")
            
            # Get the sharing link
            try:
                share_url = self._get_sharing_link(drive_service, spreadsheet_id)
            except Exception as e:
                self.logger.error(f"Failed to get sharing link: {e}")
                share_url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"
            
            self.logger.info(f"Successfully saved {len(all_jobs)} jobs to Google Sheets: {share_url}")
            return share_url
            
        except Exception as e:
            self.logger.error(f"Error saving to Google Sheets: {e}")
            return ""