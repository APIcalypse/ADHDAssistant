import os
import logging
from supabase import create_client, Client

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Get Supabase credentials from environment
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

# Global client
supabase: Client = None


def get_supabase_client() -> Client:
    """Get or create a Supabase client."""
    global supabase
    
    if supabase is None:
        if not SUPABASE_URL or not SUPABASE_KEY:
            logger.error("Supabase URL or key missing in environment variables")
            raise ValueError("Supabase credentials not configured")
        
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        logger.info("Supabase client initialized")
    
    return supabase


def sync_user_to_supabase(user_id, telegram_id, email, username):
    """Sync a user to Supabase."""
    try:
        client = get_supabase_client()
        
        # Check if user exists in Supabase
        resp = client.table("users").select("*").eq("telegram_id", telegram_id).execute()
        
        if len(resp.data) > 0:
            # Update existing user
            supabase_user_id = resp.data[0]["id"]
            client.table("users").update({
                "email": email,
                "username": username,
                "last_sync": "now()"
            }).eq("id", supabase_user_id).execute()
            logger.info(f"Updated user {telegram_id} in Supabase")
        else:
            # Create new user
            client.table("users").insert({
                "app_user_id": user_id,
                "telegram_id": telegram_id,
                "email": email,
                "username": username
            }).execute()
            logger.info(f"Created user {telegram_id} in Supabase")
        
        return True
    
    except Exception as e:
        logger.error(f"Error syncing user to Supabase: {e}")
        return False


def sync_task_to_supabase(task_id, user_id, title, description, due_date, priority, completed):
    """Sync a task to Supabase."""
    try:
        client = get_supabase_client()
        
        # Check if task exists in Supabase
        resp = client.table("tasks").select("*").eq("app_task_id", task_id).execute()
        
        if len(resp.data) > 0:
            # Update existing task
            supabase_task_id = resp.data[0]["id"]
            client.table("tasks").update({
                "title": title,
                "description": description,
                "due_date": due_date.isoformat() if due_date else None,
                "priority": priority,
                "completed": completed,
                "last_sync": "now()"
            }).eq("id", supabase_task_id).execute()
            logger.info(f"Updated task {task_id} in Supabase")
        else:
            # Create new task
            client.table("tasks").insert({
                "app_task_id": task_id,
                "app_user_id": user_id,
                "title": title,
                "description": description,
                "due_date": due_date.isoformat() if due_date else None,
                "priority": priority,
                "completed": completed
            }).execute()
            logger.info(f"Created task {task_id} in Supabase")
        
        return True
    
    except Exception as e:
        logger.error(f"Error syncing task to Supabase: {e}")
        return False


def sync_reminder_to_supabase(reminder_id, user_id, reminder_type, message, scheduled_time, repeat_interval, active):
    """Sync a reminder to Supabase."""
    try:
        client = get_supabase_client()
        
        # Check if reminder exists in Supabase
        resp = client.table("reminders").select("*").eq("app_reminder_id", reminder_id).execute()
        
        if len(resp.data) > 0:
            # Update existing reminder
            supabase_reminder_id = resp.data[0]["id"]
            client.table("reminders").update({
                "type": reminder_type,
                "message": message,
                "scheduled_time": scheduled_time.isoformat() if scheduled_time else None,
                "repeat_interval": repeat_interval,
                "active": active,
                "last_sync": "now()"
            }).eq("id", supabase_reminder_id).execute()
            logger.info(f"Updated reminder {reminder_id} in Supabase")
        else:
            # Create new reminder
            client.table("reminders").insert({
                "app_reminder_id": reminder_id,
                "app_user_id": user_id,
                "type": reminder_type,
                "message": message,
                "scheduled_time": scheduled_time.isoformat() if scheduled_time else None,
                "repeat_interval": repeat_interval,
                "active": active
            }).execute()
            logger.info(f"Created reminder {reminder_id} in Supabase")
        
        return True
    
    except Exception as e:
        logger.error(f"Error syncing reminder to Supabase: {e}")
        return False
