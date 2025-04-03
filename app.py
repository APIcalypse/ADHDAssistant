import os
import logging

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from flask_login import LoginManager


# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class Base(DeclarativeBase):
    pass


db = SQLAlchemy(model_class=Base)
# create the app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET")

# configure the database
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///adhd_bot.db")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# initialize the app with the extension
db.init_app(app)

# Setup Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    from models import User
    return User.query.get(int(user_id))

# Import routes after app is created to avoid circular imports
with app.app_context():
    # Make sure to import the models here
    import models  # noqa: F401
    import routes  # noqa: F401
    
    # Create tables if they don't exist
    db.create_all()
    logger.info("Database tables created")
    
    # Initialize reminders
    from routes import init_reminders
    init_reminders()
    logger.info("Reminders initialized")

# Initialize bot if TELEGRAM_TOKEN is available
telegram_token = os.environ.get("TELEGRAM_TOKEN")
if telegram_token:
    from bot import initialize_bot
    initialize_bot(telegram_token)
    logger.info("Bot initialized")
else:
    logger.warning("TELEGRAM_TOKEN not found. Bot will not be initialized.")
