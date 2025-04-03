import os

# Flask configurations
DEBUG = os.environ.get('DEBUG', 'True').lower() == 'true'
SECRET_KEY = os.environ.get('SESSION_SECRET', 'dev_key')
DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:///adhd_bot.db')

# Telegram configurations
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')

# Google Calendar configurations
GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID')
GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET')
GOOGLE_REDIRECT_URI = os.environ.get('GOOGLE_REDIRECT_URI', 'http://localhost:5000/oauth2callback')

# Supabase configurations
SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY')

# n8n configurations
N8N_WEBHOOK_URL = os.environ.get('N8N_WEBHOOK_URL')

# API configurations
API_KEY = os.environ.get('API_KEY')

# Base URL for the application
BASE_URL = os.environ.get('BASE_URL', 'http://localhost:5000')
