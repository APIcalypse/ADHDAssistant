import os
import logging
import threading
import time
from datetime import datetime, timedelta

from app import db
from models import User, Reminder
from n8n_integration import send_reminder_notification

# We'll import the bot application when needed to avoid circular imports

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Dictionary to track reminder threads
reminder_threads = {}


def send_reminder(reminder_id):
    """Send a reminder to a user."""
    from app import app
    
    with app.app_context():
        # Get reminder from database
        reminder = Reminder.query.get(reminder_id)
        
        if not reminder or not reminder.active:
            logger.info(f"Reminder {reminder_id} not found or not active")
            return False
        
        # Get user
        user = User.query.get(reminder.user_id)
        
        if not user or not user.telegram_id:
            logger.error(f"User for reminder {reminder_id} not found or has no Telegram ID")
            return False
        
        try:
            # Send notification via Telegram
            # Import bot inside to avoid circular import
            try:
                from bot import application
                # Check if application is available and initialized
                if application is not None:
                    telegram_id = int(user.telegram_id)
                    application.bot.send_message(
                        chat_id=telegram_id,
                        text=reminder.message
                    )
                    logger.info(f"Reminder {reminder_id} sent to Telegram {user.telegram_id}")
                else:
                    logger.warning("Bot application is None")
            except (ImportError, AttributeError) as e:
                logger.warning(f"Bot application not available: {e}")
            
            # Also try to send via n8n for redundancy
            send_reminder_notification(
                user.id,
                user.telegram_id,
                reminder.message
            )
            
            # Update last sent time
            reminder.last_sent_at = datetime.utcnow()
            
            # If repeating, schedule next reminder
            if reminder.repeat_interval:
                reminder.scheduled_time = datetime.utcnow() + timedelta(minutes=reminder.repeat_interval)
            else:
                # Mark as inactive if non-repeating
                reminder.active = False
            
            db.session.commit()
            
            # If repeating, schedule next reminder
            if reminder.repeat_interval:
                schedule_reminder(reminder_id)
            
            return True
        
        except Exception as e:
            logger.error(f"Error sending reminder {reminder_id}: {e}")
            return False


def reminder_thread_func(reminder_id, delay_seconds):
    """Thread function to wait and send a reminder."""
    logger.info(f"Reminder {reminder_id} scheduled in {delay_seconds} seconds")
    
    # Sleep until it's time to send the reminder
    time.sleep(delay_seconds)
    
    # Send the reminder
    send_reminder(reminder_id)
    
    # Remove thread from tracking dictionary
    if reminder_id in reminder_threads:
        del reminder_threads[reminder_id]


def schedule_reminder(reminder_id):
    """Schedule a reminder to be sent."""
    from app import app
    
    with app.app_context():
        # Get reminder from database
        reminder = Reminder.query.get(reminder_id)
        
        if not reminder or not reminder.active:
            logger.info(f"Reminder {reminder_id} not found or not active")
            return False
        
        # Calculate delay in seconds
        now = datetime.utcnow()
        
        if reminder.scheduled_time <= now:
            # Send immediately
            send_reminder(reminder_id)
            return True
        
        delay_seconds = (reminder.scheduled_time - now).total_seconds()
        
        # Create and start thread
        thread = threading.Thread(
            target=reminder_thread_func,
            args=(reminder_id, delay_seconds),
            daemon=True
        )
        
        # Store thread in tracking dictionary
        reminder_threads[reminder_id] = thread
        
        # Start the thread
        thread.start()
        
        logger.info(f"Reminder {reminder_id} scheduled for {reminder.scheduled_time}")
        return True


def schedule_all_reminders():
    """Schedule all active reminders from the database."""
    from app import app
    
    with app.app_context():
        # Get all active reminders
        reminders = Reminder.query.filter_by(active=True).all()
        
        count = 0
        for reminder in reminders:
            if schedule_reminder(reminder.id):
                count += 1
        
        logger.info(f"Scheduled {count} reminders")
        return count


def cleanup_expired_reminders():
    """Clean up expired non-repeating reminders."""
    from app import app
    
    with app.app_context():
        # Find expired non-repeating reminders
        now = datetime.utcnow()
        expired_reminders = Reminder.query.filter(
            Reminder.repeat_interval.is_(None),
            Reminder.scheduled_time < now,
            Reminder.active == True
        ).all()
        
        # Mark as inactive
        for reminder in expired_reminders:
            reminder.active = False
        
        db.session.commit()
        
        logger.info(f"Cleaned up {len(expired_reminders)} expired reminders")
        return len(expired_reminders)
