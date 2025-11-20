 
import os
import sys
import json
from datetime import datetime
from loguru import logger

from config import LOG_LEVEL


def setup_logging():
    """Configure logging for the application"""
    # Remove default logger
    logger.remove()
    
    # Determine log level
    log_level = LOG_LEVEL.upper()
    
    # Add console handler with custom format
    logger.add(
        sys.stderr,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level=log_level,
        colorize=True
    )
    
    # Add file handler for info+ logs
    logs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
    os.makedirs(logs_dir, exist_ok=True)
    
    log_file = os.path.join(logs_dir, f"app_{datetime.now().strftime('%Y%m%d')}.log")
    logger.add(
        log_file,
        rotation="500 MB",
        retention="10 days",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level=log_level
    )
    
    # Add file handler for errors only
    error_log_file = os.path.join(logs_dir, f"error_{datetime.now().strftime('%Y%m%d')}.log")
    logger.add(
        error_log_file,
        rotation="100 MB",
        retention="30 days",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level="ERROR"
    )
    
    logger.info(f"Logging initialized with level: {log_level}")


def log_dict(data, title=None):
    """Helper function to log dictionary data in a readable format"""
    if title:
        logger.debug(f"{title}:")
    logger.debug(json.dumps(data, indent=2, default=str))


# Initialize logging when module is imported
setup_logging()