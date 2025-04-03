import os
import logging
import json
import requests
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Get n8n webhook URL from environment
N8N_WEBHOOK_URL = os.environ.get("N8N_WEBHOOK_URL")


def trigger_workflow(event_type, payload):
    """Trigger an n8n workflow using webhook."""
    if not N8N_WEBHOOK_URL:
        logger.warning("N8N_WEBHOOK_URL not set, skipping workflow trigger")
        return False
    
    try:
        # Add event type and timestamp to payload
        full_payload = {
            "event_type": event_type,
            "timestamp": datetime.utcnow().isoformat(),
            "data": payload
        }
        
        # Send webhook request
        response = requests.post(
            N8N_WEBHOOK_URL,
            json=full_payload,
            headers={"Content-Type": "application/json"}
        )
        
        if response.status_code == 200:
            logger.info(f"Successfully triggered n8n workflow for {event_type}")
            return True
        else:
            logger.error(f"Error triggering n8n workflow: {response.status_code} - {response.text}")
            return False
    
    except Exception as e:
        logger.error(f"Error triggering n8n workflow: {e}")
        return False


def send_reminder_notification(user_id, telegram_id, message):
    """Send a reminder notification through n8n."""
    payload = {
        "user_id": user_id,
        "telegram_id": telegram_id,
        "message": message,
        "notification_type": "reminder"
    }
    
    return trigger_workflow("send_notification", payload)


def register_water_reminder(user_id, telegram_id, interval_minutes):
    """Register a water reminder in n8n."""
    payload = {
        "user_id": user_id,
        "telegram_id": telegram_id,
        "interval_minutes": interval_minutes,
        "reminder_type": "water"
    }
    
    return trigger_workflow("register_reminder", payload)


def sync_calendar_events(user_id, telegram_id):
    """Trigger calendar sync in n8n."""
    payload = {
        "user_id": user_id,
        "telegram_id": telegram_id,
        "action": "sync_calendar"
    }
    
    return trigger_workflow("calendar_action", payload)


def process_task_completion(user_id, telegram_id, task_title):
    """Process task completion in n8n."""
    payload = {
        "user_id": user_id,
        "telegram_id": telegram_id,
        "task_title": task_title,
        "action": "task_completed"
    }
    
    return trigger_workflow("task_action", payload)


def start_daily_planning(user_id, telegram_id):
    """Start daily planning workflow in n8n."""
    payload = {
        "user_id": user_id,
        "telegram_id": telegram_id,
        "action": "start_daily_planning"
    }
    
    return trigger_workflow("daily_planning", payload)
