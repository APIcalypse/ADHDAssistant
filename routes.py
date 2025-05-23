import os
import logging
from datetime import datetime, timedelta

from flask import render_template, redirect, url_for, flash, request, session, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, EmailField
from wtforms.validators import DataRequired, Email, EqualTo, Length, ValidationError

from app import app, db
from models import User, Task, Reminder, CalendarEvent
from calendar_integration import get_auth_url, process_oauth_callback, get_upcoming_events
from supabase_client import sync_user_to_supabase, sync_task_to_supabase, sync_reminder_to_supabase
from n8n_integration import trigger_workflow
from reminder_manager import schedule_reminder, schedule_all_reminders, cleanup_expired_reminders

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Define forms
class RegistrationForm(FlaskForm):
    telegram_id = StringField('Telegram ID', validators=[DataRequired()])
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=64)])
    email = EmailField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=8)])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Register')
    
    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user and user.password_hash:  # Only check fully registered users
            raise ValidationError('That username is already taken. Please choose a different one.')
    
    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user and user.password_hash:  # Only check fully registered users
            raise ValidationError('That email is already registered. Please use a different one.')
            
class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')


@app.route('/')
def index():
    """Home page route."""
    return render_template('index.html')

@app.errorhandler(404)
def page_not_found(e):
    """Handle 404 errors by returning to index"""
    return render_template('index.html'), 200


@app.route('/register', methods=['GET', 'POST'])
def register():
    """User registration route."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    form = RegistrationForm()
    
    if form.validate_on_submit():
        telegram_id = form.telegram_id.data
        
        # Add debug logging
        logger.debug(f"Looking for user with telegram_id: '{telegram_id}'")
        logger.debug(f"User data in DB: {User.query.all()}")
        
        # Check if user with this Telegram ID exists
        existing_user = User.query.filter_by(telegram_id=telegram_id).first()
        
        # Also try with string comparison
        if not existing_user:
            logger.debug("First query failed, trying to fetch all users and compare manually")
            all_users = User.query.all()
            for user in all_users:
                logger.debug(f"Comparing: DB '{user.telegram_id}' vs Input '{telegram_id}'")
                if str(user.telegram_id) == str(telegram_id):
                    existing_user = user
                    logger.debug(f"Found match by string comparison!")
                    break
        
        if not existing_user:
            flash('No user found with this Telegram ID. Please register with the bot first using /register command.', 'danger')
            return render_template('register.html', form=form)
        
        # Check if this Telegram ID has already been fully registered with password
        if existing_user.password_hash:
            flash('This Telegram account has already been fully registered. Please login instead.', 'warning')
            return redirect(url_for('login'))
        
        # Update the existing user with proper information
        existing_user.username = form.username.data
        existing_user.email = form.email.data
        existing_user.password_hash = generate_password_hash(form.password.data)
        db.session.commit()
        
        # Sync to Supabase if needed
        try:
            sync_user_to_supabase(
                existing_user.id,
                existing_user.telegram_id,
                existing_user.email,
                existing_user.username
            )
        except Exception as e:
            logger.error(f"Error syncing user to Supabase: {e}")
        
        # Instead of logging the user in, redirect to login page with a success message
        flash('Registration completed successfully! Please log in with your new account.', 'success')
        
        # Also try to send a Telegram notification to the user
        try:
            from bot import application
            if application:
                # Use application to send message to telegram user
                import asyncio
                from telegram import Bot
                
                async def send_message():
                    bot = Bot(token=os.environ.get("TELEGRAM_TOKEN"))
                    await bot.send_message(
                        chat_id=existing_user.telegram_id,
                        text=f"✅ Your web registration is complete!\n\n"
                             f"You can now login to your dashboard using:\n"
                             f"Username: {existing_user.username}\n\n"
                             f"Remember to use the password you created during registration."
                    )
                
                # Run the async function in a new event loop
                try:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(send_message())
                    loop.close()
                except Exception as e:
                    logger.error(f"Error sending Telegram notification: {e}")
        except Exception as e:
            logger.error(f"Could not send Telegram notification: {e}")
            
        # Redirect to login page
        return redirect(url_for('login'))
    
    return render_template('register.html', form=form)

@app.route('/login', methods=['GET', 'POST'])
def login():
    """User login route."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    form = LoginForm()
    
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        
        if user and user.password_hash and check_password_hash(user.password_hash, form.password.data):
            login_user(user)
            flash('Login successful!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password.', 'danger')
    
    return render_template('login.html', form=form)


@app.route('/logout')
@login_required
def logout():
    """User logout route."""
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))


@app.route('/dashboard')
@login_required
def dashboard():
    """User dashboard route."""
    # Get user's tasks
    tasks = Task.query.filter_by(user_id=current_user.id, completed=False).order_by(Task.due_date).all()
    
    # Get user's reminders
    reminders = Reminder.query.filter_by(user_id=current_user.id, active=True).all()
    
    # Get upcoming calendar events
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    events = CalendarEvent.query.filter(
        CalendarEvent.user_id == current_user.id,
        CalendarEvent.start_time >= today
    ).order_by(CalendarEvent.start_time).limit(10).all()
    
    # Check if user has Google Calendar connected
    calendar_connected = bool(current_user.google_calendar_token)
    
    return render_template(
        'dashboard.html',
        tasks=tasks,
        reminders=reminders,
        events=events,
        calendar_connected=calendar_connected
    )


@app.route('/authorize_calendar/<int:user_id>')
def authorize_calendar(user_id):
    """Start the Google Calendar authorization flow."""
    user = User.query.get(user_id)
    
    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('index'))
    
    try:
        auth_url = get_auth_url(user_id)
        return redirect(auth_url)
    except Exception as e:
        logger.error(f"Error starting calendar authorization: {e}")
        flash('Error connecting to Google Calendar.', 'danger')
        return redirect(url_for('dashboard'))


@app.route('/oauth2callback')
def oauth2callback():
    """Handle Google OAuth callback."""
    code = request.args.get('code')
    state = request.args.get('state')  # Contains user_id
    
    if not code or not state:
        flash('Authorization failed.', 'danger')
        return redirect(url_for('dashboard'))
    
    try:
        success = process_oauth_callback(code, state)
        
        if success:
            flash('Google Calendar connected successfully!', 'success')
            
            # Redirect to dashboard if logged in
            if current_user.is_authenticated:
                return redirect(url_for('dashboard'))
            else:
                # For users coming from Telegram bot
                return render_template('calendar_connected.html')
        else:
            flash('Failed to connect Google Calendar.', 'danger')
            return redirect(url_for('dashboard'))
    
    except Exception as e:
        logger.error(f"Error in OAuth callback: {e}")
        flash('Error connecting Google Calendar.', 'danger')
        return redirect(url_for('dashboard'))


@app.route('/sync_calendar')
@login_required
def sync_calendar():
    """Manually sync Google Calendar."""
    if not current_user.google_calendar_token:
        flash('Please connect your Google Calendar first.', 'warning')
        return redirect(url_for('dashboard'))
    
    try:
        success = get_upcoming_events(current_user.id)
        
        if success:
            flash('Calendar synced successfully!', 'success')
        else:
            flash('Failed to sync calendar.', 'danger')
    
    except Exception as e:
        logger.error(f"Error syncing calendar: {e}")
        flash('Error syncing calendar.', 'danger')
    
    return redirect(url_for('dashboard'))


@app.route('/add_task', methods=['POST'])
@login_required
def add_task():
    """Add a new task."""
    title = request.form.get('title')
    description = request.form.get('description', '')
    due_date_str = request.form.get('due_date', '')
    priority = int(request.form.get('priority', 0))
    
    if not title:
        flash('Task title is required.', 'danger')
        return redirect(url_for('dashboard'))
    
    # Parse due date if provided
    due_date = None
    if due_date_str:
        try:
            due_date = datetime.strptime(due_date_str, '%Y-%m-%dT%H:%M')
        except ValueError:
            flash('Invalid date format.', 'warning')
    
    # Create the task
    task = Task(
        title=title,
        description=description,
        due_date=due_date,
        priority=priority,
        user_id=current_user.id
    )
    db.session.add(task)
    db.session.commit()
    
    # Sync to Supabase
    sync_task_to_supabase(
        task.id,
        current_user.id,
        task.title,
        task.description,
        task.due_date,
        task.priority,
        task.completed
    )
    
    # Create a reminder for the task if it has a due date
    if due_date:
        reminder = Reminder(
            type="task",
            message=f"Reminder: {task.title}",
            scheduled_time=due_date - timedelta(hours=1),  # 1 hour before
            active=True,
            user_id=current_user.id,
            task_id=task.id
        )
        db.session.add(reminder)
        db.session.commit()
        
        # Schedule the reminder
        schedule_reminder(reminder.id)
        
        # Sync to Supabase
        sync_reminder_to_supabase(
            reminder.id,
            current_user.id,
            reminder.type,
            reminder.message,
            reminder.scheduled_time,
            reminder.repeat_interval,
            reminder.active
        )
    
    flash('Task added successfully!', 'success')
    return redirect(url_for('dashboard'))


@app.route('/complete_task/<int:task_id>', methods=['POST'])
@login_required
def complete_task(task_id):
    """Mark a task as complete."""
    task = Task.query.get(task_id)
    
    if not task or task.user_id != current_user.id:
        flash('Task not found.', 'danger')
        return redirect(url_for('dashboard'))
    
    task.completed = True
    db.session.commit()
    
    # Sync to Supabase
    sync_task_to_supabase(
        task.id,
        current_user.id,
        task.title,
        task.description,
        task.due_date,
        task.priority,
        task.completed
    )
    
    # Trigger n8n workflow for task completion
    trigger_workflow("task_action", {
        "user_id": current_user.id,
        "telegram_id": current_user.telegram_id,
        "task_title": task.title,
        "action": "task_completed"
    })
    
    flash('Task completed!', 'success')
    return redirect(url_for('dashboard'))


@app.route('/add_water_reminder', methods=['POST'])
@login_required
def add_water_reminder():
    """Add a water reminder."""
    interval = int(request.form.get('interval', 60))  # Default to every hour
    
    # Check for existing water reminders
    existing = Reminder.query.filter_by(user_id=current_user.id, type="water").first()
    
    if existing:
        # Update existing reminder
        existing.repeat_interval = interval
        existing.active = True
        existing.scheduled_time = datetime.utcnow() + timedelta(minutes=interval)
        db.session.commit()
        
        # Reschedule the reminder
        schedule_reminder(existing.id)
        
        # Sync to Supabase
        sync_reminder_to_supabase(
            existing.id,
            current_user.id,
            existing.type,
            existing.message,
            existing.scheduled_time,
            existing.repeat_interval,
            existing.active
        )
        
        flash(f'Water reminder updated to every {interval} minutes!', 'success')
    else:
        # Create new water reminder
        reminder = Reminder(
            type="water",
            message="Time to drink water! 💧 Stay hydrated!",
            scheduled_time=datetime.utcnow() + timedelta(minutes=interval),
            repeat_interval=interval,
            active=True,
            user_id=current_user.id
        )
        db.session.add(reminder)
        db.session.commit()
        
        # Schedule the reminder
        schedule_reminder(reminder.id)
        
        # Sync to Supabase
        sync_reminder_to_supabase(
            reminder.id,
            current_user.id,
            reminder.type,
            reminder.message,
            reminder.scheduled_time,
            reminder.repeat_interval,
            reminder.active
        )
        
        flash(f'Water reminder set for every {interval} minutes!', 'success')
    
    return redirect(url_for('dashboard'))


@app.route('/toggle_reminder/<int:reminder_id>', methods=['POST'])
@login_required
def toggle_reminder(reminder_id):
    """Toggle a reminder's active status."""
    reminder = Reminder.query.get(reminder_id)
    
    if not reminder or reminder.user_id != current_user.id:
        flash('Reminder not found.', 'danger')
        return redirect(url_for('dashboard'))
    
    reminder.active = not reminder.active
    
    if reminder.active:
        # Set next scheduled time if activating
        reminder.scheduled_time = datetime.utcnow() + timedelta(minutes=reminder.repeat_interval or 60)
        
        # Schedule the reminder
        schedule_reminder(reminder.id)
    
    db.session.commit()
    
    # Sync to Supabase
    sync_reminder_to_supabase(
        reminder.id,
        current_user.id,
        reminder.type,
        reminder.message,
        reminder.scheduled_time,
        reminder.repeat_interval,
        reminder.active
    )
    
    status = "activated" if reminder.active else "paused"
    flash(f'Reminder {status}!', 'success')
    return redirect(url_for('dashboard'))


@app.route('/api/schedule_reminders', methods=['POST'])
def api_schedule_reminders():
    """API endpoint to schedule all reminders (for external triggers like n8n)."""
    api_key = request.headers.get('X-API-Key')
    expected_key = os.environ.get('API_KEY')
    
    if not expected_key or api_key != expected_key:
        return jsonify({"error": "Unauthorized"}), 401
    
    count = schedule_all_reminders()
    cleanup_expired_reminders()
    
    return jsonify({"success": True, "scheduled_count": count})


@app.route('/api/send_reminder/<int:reminder_id>', methods=['POST'])
def api_send_reminder(reminder_id):
    """API endpoint to send a specific reminder (for external triggers)."""
    api_key = request.headers.get('X-API-Key')
    expected_key = os.environ.get('API_KEY')
    
    if not expected_key or api_key != expected_key:
        return jsonify({"error": "Unauthorized"}), 401
    
    from reminder_manager import send_reminder
    success = send_reminder(reminder_id)
    
    return jsonify({"success": success})


@app.route('/api/telegram_webhook', methods=['POST'])
def telegram_webhook():
    """API endpoint for Telegram webhook."""
    api_key = request.headers.get('X-API-Key')
    expected_key = os.environ.get('API_KEY')
    
    if not expected_key or api_key != expected_key:
        return jsonify({"error": "Unauthorized"}), 401
    
    # Process webhook data
    data = request.json
    
    # Forward to bot for processing
    if data and 'message' in data:
        # This would typically be handled by python-telegram-bot library
        # But we can pass it to n8n for processing
        trigger_workflow("telegram_webhook", data)
    
    return jsonify({"success": True})


# Initialize reminder scheduling at startup
def init_reminders():
    """Initialize reminders at startup."""
    with app.app_context():
        schedule_all_reminders()
        cleanup_expired_reminders()

# Use app.before_serving in newer Flask versions
# or call it after app is created
# For now, we'll call it from app.py
