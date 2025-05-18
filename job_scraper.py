#!/usr/bin/env python3
"""
Job Scraper - Entry point script
Run this file to start the job scraper with command line arguments.
"""

import sys
import os

# Add src directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))

# Import the main function from main.py
from main import main

if __name__ == "__main__":
    # Execute the main function
    sys.exit(main())