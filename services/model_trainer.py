import datetime
import time
import sys
import os
from loguru import logger

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from offline.als.train_als import train_als_offline

def run_scheduler():
    """
    Simple scheduler to run ALS training daily at 2:00 AM.
    """
    logger.info("ALS Training Scheduler started")
    
    while True:
        now = datetime.datetime.now()
        
        # Calculate next run time (today at 2:00 AM)
        next_run = now.replace(hour=2, minute=0, second=0, microsecond=0)
        
        # If today 2:00 AM has passed, schedule for tomorrow 2:00 AM
        if now >= next_run:
            next_run += datetime.timedelta(days=1)
            
        wait_seconds = (next_run - now).total_seconds()
        
        logger.info(f"Next ALS training scheduled for {next_run} (in {wait_seconds/3600:.2f} hours)")
        
        # Sleep until scheduled time
        time.sleep(wait_seconds)
        
        # Run training
        try:
            logger.info("Starting scheduled ALS training...")
            train_als_offline()
            logger.info("Scheduled ALS training completed successfully")
        except Exception as e:
            logger.error(f"Scheduled ALS training failed: {e}")
            
        # Sleep a bit to avoid double execution if clock skews (though next loop handles it)
        time.sleep(60)

if __name__ == "__main__":
    run_scheduler()
