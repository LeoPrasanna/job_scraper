"""
Centralized logging configuration for the job scraper.
"""

import os
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime

# Constants
DEFAULT_LOG_LEVEL = logging.INFO
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
MAX_LOG_SIZE = 10 * 1024 * 1024  # 10 MB
BACKUP_COUNT = 5  # Number of backup logs to keep

def setup_logger(name, log_dir='logs', console=True, level=DEFAULT_LOG_LEVEL):
    """
    Set up a logger with file and console handlers.
    
    Args:
        name (str): Logger name
        log_dir (str): Directory to store log files
        console (bool): Whether to output logs to console
        level (int): Logging level
        
    Returns:
        logging.Logger: Configured logger
    """
    # Create logger
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Clear any existing handlers
    logger.handlers = []
    
    # Create formatter
    formatter = logging.Formatter(LOG_FORMAT)
    
    # Create logs directory if it doesn't exist
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    # Generate log filename with timestamp and logger name
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    sanitized_name = name.replace('.', '_')
    log_file = os.path.join(log_dir, f'{sanitized_name}_{timestamp}.log')
    
    # Add file handler
    file_handler = RotatingFileHandler(
        log_file, 
        maxBytes=MAX_LOG_SIZE, 
        backupCount=BACKUP_COUNT
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    # Add stream handler if console output is requested
    if console:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    
    return logger

def get_scraper_logger(scraper_name):
    """
    Get a logger configured for a specific scraper.
    
    Args:
        scraper_name (str): Name of the scraper
        
    Returns:
        logging.Logger: Configured logger for the scraper
    """
    return setup_logger(f'scraper.{scraper_name}')

def get_orchestrator_logger():
    """
    Get a logger configured for the orchestrator.
    
    Returns:
        logging.Logger: Configured logger for the orchestrator
    """
    return setup_logger('orchestrator')

def get_output_logger():
    """
    Get a logger configured for output handlers.
    
    Returns:
        logging.Logger: Configured logger for output handlers
    """
    return setup_logger('output')