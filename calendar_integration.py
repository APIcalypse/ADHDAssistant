import os
import logging
import json
from datetime import datetime, timedelta

import requests
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app import db
from models import User, CalendarEvent

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Google Calendar API scopes
SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']
API_SERVICE_NAME = 'calendar'
API_VERSION = 'v3'

# Get client secrets from environment
CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID')
CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET')
REDIRECT_URI = os.environ.get('GOOGLE_REDIRECT_URI', 'http://localhost:5000/oauth2callback')


def create_oauth_flow():
    """Create OAuth flow for Google Calendar API."""
    if not CLIENT_ID or not CLIENT_SECRET:
        logger.error("Google client ID or secret missing in environment variables")
        raise ValueError("Google API credentials not configured")
    
    # Create flow instance
    client_config = {
        "web": {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [REDIRECT_URI]
        }
    }
    
    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )
    
    return flow


def get_auth_url(user_id):
    """Generate authorization URL for Google Calendar."""
    flow = create_oauth_flow()
    
    # Generate URL for user consent
    auth_url, _ = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent',
        state=str(user_id)  # Pass user_id as state parameter
    )
    
    return auth_url


def process_oauth_callback(code, state):
    """Process OAuth callback from Google."""
    user_id = int(state)
    flow = create_oauth_flow()
    
    # Exchange code for token
    flow.fetch_token(code=code)
    credentials = flow.credentials
    
    # Save token to user record
    user = User.query.get(user_id)
    if not user:
        logger.error(f"User {user_id} not found")
        return False
    
    # Store credentials as JSON string
    user.google_calendar_token = json.dumps({
        'token': credentials.token,
        'refresh_token': credentials.refresh_token,
        'token_uri': credentials.token_uri,
        'client_id': credentials.client_id,
        'client_secret': credentials.client_secret,
        'scopes': credentials.scopes,
        'expiry': credentials.expiry.isoformat() if credentials.expiry else None
    })
    
    db.session.commit()
    logger.info(f"Google Calendar connected for user {user_id}")
    
    # Immediately sync calendar events
    get_upcoming_events(user_id)
    
    return True


def get_calendar_service(user_id):
    """Get Google Calendar service for a user."""
    user = User.query.get(user_id)
    if not user or not user.google_calendar_token:
        logger.error(f"User {user_id} not found or calendar not connected")
        return None
    
    # Parse stored credentials
    try:
        creds_data = json.loads(user.google_calendar_token)
        
        if creds_data.get('expiry'):
            expiry = datetime.fromisoformat(creds_data['expiry'])
        else:
            expiry = None
        
        credentials = Credentials(
            token=creds_data['token'],
            refresh_token=creds_data['refresh_token'],
            token_uri=creds_data['token_uri'],
            client_id=creds_data['client_id'],
            client_secret=creds_data['client_secret'],
            scopes=creds_data['scopes'],
            expiry=expiry
        )
        
        # Check if credentials are expired and refresh if needed
        if credentials.expired and credentials.refresh_token:
            credentials.refresh(requests.Request())
            
            # Update stored credentials after refresh
            user.google_calendar_token = json.dumps({
                'token': credentials.token,
                'refresh_token': credentials.refresh_token,
                'token_uri': credentials.token_uri,
                'client_id': credentials.client_id,
                'client_secret': credentials.client_secret,
                'scopes': credentials.scopes,
                'expiry': credentials.expiry.isoformat() if credentials.expiry else None
            })
            db.session.commit()
        
        # Build and return the service
        service = build(API_SERVICE_NAME, API_VERSION, credentials=credentials)
        return service
    
    except Exception as e:
        logger.error(f"Error getting calendar service: {e}")
        return None


def get_upcoming_events(user_id, days=14):
    """Fetch upcoming events from Google Calendar and store in the database."""
    service = get_calendar_service(user_id)
    if not service:
        return False
    
    try:
        # Calculate time min and max
        now = datetime.utcnow()
        time_min = now.isoformat() + 'Z'  # 'Z' indicates UTC time
        time_max = (now + timedelta(days=days)).isoformat() + 'Z'
        
        # Call the Calendar API
        events_result = service.events().list(
            calendarId='primary',
            timeMin=time_min,
            timeMax=time_max,
            maxResults=50,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])
        
        if not events:
            logger.info(f"No upcoming events found for user {user_id}")
            return True
        
        # Store events in the database
        for event in events:
            # Extract event details
            google_event_id = event['id']
            title = event.get('summary', 'Unnamed event')
            description = event.get('description', '')
            
            # Parse start and end times
            start = event.get('start', {})
            end = event.get('end', {})
            
            if 'dateTime' in start:
                # This is a timed event
                start_time = datetime.fromisoformat(start['dateTime'].replace('Z', '+00:00'))
                end_time = datetime.fromisoformat(end['dateTime'].replace('Z', '+00:00'))
            else:
                # This is an all-day event
                start_time = datetime.fromisoformat(start['date'])
                end_time = datetime.fromisoformat(end['date'])
            
            location = event.get('location', '')
            
            # Check if event already exists
            existing_event = CalendarEvent.query.filter_by(
                google_event_id=google_event_id,
                user_id=user_id
            ).first()
            
            if existing_event:
                # Update existing event
                existing_event.title = title
                existing_event.description = description
                existing_event.start_time = start_time
                existing_event.end_time = end_time
                existing_event.location = location
                existing_event.synced_at = datetime.utcnow()
            else:
                # Create new event
                new_event = CalendarEvent(
                    google_event_id=google_event_id,
                    title=title,
                    description=description,
                    start_time=start_time,
                    end_time=end_time,
                    location=location,
                    user_id=user_id
                )
                db.session.add(new_event)
        
        db.session.commit()
        logger.info(f"Successfully synced {len(events)} events for user {user_id}")
        return True
    
    except HttpError as error:
        logger.error(f"Error syncing calendar events: {error}")
        return False
