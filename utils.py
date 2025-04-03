import os
import logging
from datetime import datetime, timedelta

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


def parse_natural_date(text):
    """
    Parse natural language date descriptions into datetime objects.
    Examples: "tomorrow", "next monday", "in 2 days"
    """
    text = text.lower().strip()
    now = datetime.now()
    
    # Simple cases
    if text == "today":
        return now.replace(hour=12, minute=0, second=0, microsecond=0)
    
    if text == "tomorrow":
        return (now + timedelta(days=1)).replace(hour=12, minute=0, second=0, microsecond=0)
    
    if text.startswith("in "):
        # Parse "in X days/hours/minutes"
        parts = text[3:].split()
        if len(parts) >= 2:
            try:
                amount = int(parts[0])
                unit = parts[1].lower()
                
                if unit.startswith("day"):
                    return now + timedelta(days=amount)
                elif unit.startswith("hour"):
                    return now + timedelta(hours=amount)
                elif unit.startswith("minute"):
                    return now + timedelta(minutes=amount)
            except ValueError:
                pass
    
    # Days of week
    days = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, 
            "friday": 4, "saturday": 5, "sunday": 6}
    
    for day_name, day_num in days.items():
        if day_name in text:
            # Calculate days until next occurrence of this day
            current_day = now.weekday()
            days_ahead = day_num - current_day
            if days_ahead <= 0:  # Target day already happened this week
                days_ahead += 7
                
            target_date = now + timedelta(days=days_ahead)
            if "next" in text:
                target_date += timedelta(days=7)
                
            return target_date.replace(hour=12, minute=0, second=0, microsecond=0)
    
    # Couldn't parse
    return None


def parse_time(text):
    """
    Parse time strings like "5pm", "17:30", "5:30 pm"
    Returns a tuple of (hour, minute)
    """
    text = text.lower().strip()
    hour = 0
    minute = 0
    
    # Try 24-hour format (17:30)
    if ":" in text and "am" not in text and "pm" not in text:
        try:
            hour_str, minute_str = text.split(":")
            hour = int(hour_str)
            minute = int(minute_str)
            if 0 <= hour < 24 and 0 <= minute < 60:
                return (hour, minute)
        except ValueError:
            pass
    
    # Try 12-hour format with am/pm
    if "am" in text or "pm" in text:
        # Strip am/pm and spaces
        is_pm = "pm" in text
        time_str = text.replace("am", "").replace("pm", "").strip()
        
        # Parse hour and minute
        if ":" in time_str:
            try:
                hour_str, minute_str = time_str.split(":")
                hour = int(hour_str)
                minute = int(minute_str)
            except ValueError:
                return None
        else:
            try:
                hour = int(time_str)
                minute = 0
            except ValueError:
                return None
        
        # Adjust for PM
        if is_pm and hour < 12:
            hour += 12
        elif not is_pm and hour == 12:
            hour = 0
        
        if 0 <= hour < 24 and 0 <= minute < 60:
            return (hour, minute)
    
    # Simple hour only format (5, 17)
    try:
        hour = int(text)
        if 0 <= hour < 24:
            return (hour, 0)
    except ValueError:
        pass
    
    return None


def format_datetime(dt):
    """Format a datetime in a user-friendly way."""
    if not dt:
        return "No date"
    
    now = datetime.now()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow = today + timedelta(days=1)
    
    # For today
    if dt >= today and dt < tomorrow:
        return f"Today at {dt.strftime('%I:%M %p')}"
    
    # For tomorrow
    if dt >= tomorrow and dt < tomorrow + timedelta(days=1):
        return f"Tomorrow at {dt.strftime('%I:%M %p')}"
    
    # For this week (within 7 days)
    if dt < today + timedelta(days=7):
        return f"{dt.strftime('%A')} at {dt.strftime('%I:%M %p')}"
    
    # For everything else
    return dt.strftime("%b %d, %Y at %I:%M %p")


def format_telegram_message(text, entities=None):
    """Format Telegram message with entities (bold, italic, etc.)."""
    if not entities:
        return text
    
    # Sort entities by offset in reverse order to avoid affecting positions
    entities.sort(key=lambda e: e.get('offset', 0), reverse=True)
    
    result = text
    for entity in entities:
        start = entity.get('offset', 0)
        length = entity.get('length', 0)
        end = start + length
        
        if start >= len(result) or end > len(result):
            continue
        
        entity_text = result[start:end]
        
        if entity.get('type') == 'bold':
            result = result[:start] + f"*{entity_text}*" + result[end:]
        elif entity.get('type') == 'italic':
            result = result[:start] + f"_{entity_text}_" + result[end:]
        elif entity.get('type') == 'code':
            result = result[:start] + f"`{entity_text}`" + result[end:]
        
    return result
