import os
import logging
from datetime import datetime, timedelta
import threading
import time

import logging
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup

from app import db
from models import User, Task, Reminder, CalendarEvent
from calendar_integration import get_upcoming_events
from supabase_client import get_supabase_client
from reminder_manager import schedule_reminder, send_reminder

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Global application instance
application = None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send welcome message when the command /start is issued."""
    user = update.effective_user
    await update.message.reply_text(
        f"Hello {user.first_name}! I'm your ADHD Assistant Bot.\n\n"
        "I can help you with:\n"
        "- 🔔 Setting reminders\n"
        "- 📝 Managing tasks\n"
        "- 📅 Calendar integration\n"
        "- 💧 Water reminders\n\n"
        "Use /help to see all available commands."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send help info when the command /help is issued."""
    await update.message.reply_text(
        "Here are the commands you can use:\n\n"
        "/start - Start the bot\n"
        "/help - Show this help message\n"
        "/register - Register your account\n"
        "/connect_calendar - Connect Google Calendar\n"
        "/add_task - Add a new task\n"
        "/list_tasks - List all your tasks\n"
        "/complete_task - Mark a task as complete\n"
        "/water_reminder - Set water reminders\n"
        "/today - Show today's agenda\n"
        "/tomorrow - Show tomorrow's agenda\n"
        "/reminders - Manage your reminders\n"
    )


async def register(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Register a new user by linking Telegram account."""
    from app import app
    
    telegram_id = str(update.effective_user.id)
    
    with app.app_context():
        # Check if user is already registered
        existing_user = User.query.filter_by(telegram_id=telegram_id).first()
        
        if existing_user:
            await update.message.reply_text(
                "You're already registered! Use /help to see available commands."
            )
            return
        
        # Create temporary user with just telegram_id
        new_user = User(
            username=f"user_{telegram_id}", 
            email=f"temp_{telegram_id}@example.com",  # Temporary email
            telegram_id=telegram_id
        )
        db.session.add(new_user)
        db.session.commit()
        
        await update.message.reply_text(
            "You've been registered successfully!\n\n"
            "To complete your setup, please:\n"
            "1. Use /connect_calendar to link your Google Calendar\n"
            "2. Visit our website to complete your profile"
        )


async def connect_calendar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Provide instructions for connecting Google Calendar."""
    from app import app
    
    telegram_id = str(update.effective_user.id)
    base_url = os.environ.get("BASE_URL", "http://localhost:5000")
    
    with app.app_context():
        user = User.query.filter_by(telegram_id=telegram_id).first()
        
        if not user:
            await update.message.reply_text(
                "You need to register first! Use /register to get started."
            )
            return
        
        # Create auth URL
        auth_url = f"{base_url}/authorize_calendar/{user.id}"
        
        await update.message.reply_text(
            "To connect your Google Calendar, please click the link below:\n\n"
            f"{auth_url}\n\n"
            "After authorization, you'll be redirected back to our website."
        )


async def add_task(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Add a new task."""
    from app import app
    
    telegram_id = str(update.effective_user.id)
    
    with app.app_context():
        user = User.query.filter_by(telegram_id=telegram_id).first()
        
        if not user:
            await update.message.reply_text("Please register first with /register")
            return
        
        # Check if there are arguments (task details)
        if not context.args:
            await update.message.reply_text(
                "Please provide a task title. For example:\n"
                "/add_task Buy groceries tomorrow 5pm"
            )
            return
        
        # Simple parsing of task and due date
        task_text = " ".join(context.args)
        
        # Create the task
        new_task = Task(
            title=task_text,
            user_id=user.id,
            due_date=datetime.utcnow() + timedelta(days=1)  # Default to tomorrow
        )
        db.session.add(new_task)
        db.session.commit()
        
        # Create automatic reminder for the task
        reminder = Reminder(
            type="task",
            message=f"Reminder: {new_task.title}",
            scheduled_time=new_task.due_date - timedelta(hours=1),  # 1 hour before
            user_id=user.id,
            task_id=new_task.id
        )
        db.session.add(reminder)
        db.session.commit()
        
        # Schedule the reminder
        schedule_reminder(reminder.id)
        
        await update.message.reply_text(
            f"Task added successfully!\n\n"
            f"📝 {new_task.title}\n"
            f"⏰ Due: {new_task.due_date.strftime('%Y-%m-%d %H:%M')}\n\n"
            f"I'll remind you 1 hour before the deadline."
        )


async def list_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List all uncompleted tasks."""
    from app import app
    
    telegram_id = str(update.effective_user.id)
    
    with app.app_context():
        user = User.query.filter_by(telegram_id=telegram_id).first()
        
        if not user:
            await update.message.reply_text("Please register first with /register")
            return
        
        tasks = Task.query.filter_by(user_id=user.id, completed=False).order_by(Task.due_date).all()
        
        if not tasks:
            await update.message.reply_text("You don't have any pending tasks! 🎉")
            return
        
        message = "📋 Your tasks:\n\n"
        for i, task in enumerate(tasks, 1):
            due_date = task.due_date.strftime("%Y-%m-%d %H:%M") if task.due_date else "No deadline"
            message += f"{i}. {task.title}\n   Due: {due_date}\n\n"
        
        # Add a note about completing tasks
        message += "To mark a task as complete, use /complete_task [number]"
        
        await update.message.reply_text(message)


async def complete_task(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mark a task as complete."""
    from app import app
    
    telegram_id = str(update.effective_user.id)
    
    with app.app_context():
        user = User.query.filter_by(telegram_id=telegram_id).first()
        
        if not user:
            await update.message.reply_text("Please register first with /register")
            return
        
        if not context.args or not context.args[0].isdigit():
            await update.message.reply_text(
                "Please specify which task to complete by number. Example:\n"
                "/complete_task 1"
            )
            return
        
        task_num = int(context.args[0])
        
        # Get user's uncompleted tasks
        tasks = Task.query.filter_by(user_id=user.id, completed=False).order_by(Task.due_date).all()
        
        if not tasks:
            await update.message.reply_text("You don't have any pending tasks!")
            return
        
        if task_num < 1 or task_num > len(tasks):
            await update.message.reply_text(f"Invalid task number. You have {len(tasks)} pending tasks.")
            return
        
        # Mark the task as complete
        task = tasks[task_num - 1]
        task.completed = True
        db.session.commit()
        
        # Celebrate the completion
        await update.message.reply_text(
            f"🎉 Task completed: {task.title}\n\n"
            "Great job! Keep up the good work!"
        )


async def water_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Set up water reminders."""
    from app import app
    
    telegram_id = str(update.effective_user.id)
    
    with app.app_context():
        user = User.query.filter_by(telegram_id=telegram_id).first()
        
        if not user:
            await update.message.reply_text("Please register first with /register")
            return
        
        # Check for existing water reminders
        existing = Reminder.query.filter_by(user_id=user.id, type="water").first()
        
        keyboard = [
            [
                InlineKeyboardButton("30 min", callback_data="water_30"),
                InlineKeyboardButton("1 hour", callback_data="water_60")
            ],
            [
                InlineKeyboardButton("2 hours", callback_data="water_120"),
                InlineKeyboardButton("Stop reminders", callback_data="water_stop")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if existing:
            interval = existing.repeat_interval
            status = "active" if existing.active else "paused"
            await update.message.reply_text(
                f"You already have water reminders set up every {interval} minutes ({status}).\n"
                "Would you like to change the frequency or stop reminders?",
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_text(
                "How often would you like to be reminded to drink water?",
                reply_markup=reply_markup
            )


async def water_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle water reminder callbacks."""
    from app import app
    
    query = update.callback_query
    await query.answer()
    
    telegram_id = str(update.effective_user.id)
    action = query.data.split("_")[1]
    
    with app.app_context():
        user = User.query.filter_by(telegram_id=telegram_id).first()
        
        if not user:
            await query.edit_message_text("Please register first with /register")
            return
        
        existing = Reminder.query.filter_by(user_id=user.id, type="water").first()
        
        if action == "stop":
            if existing:
                existing.active = False
                db.session.commit()
                await query.edit_message_text("Water reminders have been stopped.")
            else:
                await query.edit_message_text("You don't have any water reminders set up.")
            return
        
        # Convert minutes to integers
        minutes = int(action)
        
        if existing:
            existing.repeat_interval = minutes
            existing.active = True
            db.session.commit()
            await query.edit_message_text(f"Water reminder updated to every {minutes} minutes!")
        else:
            # Create new water reminder
            reminder = Reminder(
                type="water",
                message="Time to drink water! 💧 Stay hydrated!",
                scheduled_time=datetime.utcnow() + timedelta(minutes=minutes),
                repeat_interval=minutes,
                active=True,
                user_id=user.id
            )
            db.session.add(reminder)
            db.session.commit()
            
            # Schedule the reminder
            schedule_reminder(reminder.id)
            
            await query.edit_message_text(f"Water reminder set for every {minutes} minutes!")


async def today(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show today's agenda with tasks and calendar events."""
    from app import app
    
    telegram_id = str(update.effective_user.id)
    
    with app.app_context():
        user = User.query.filter_by(telegram_id=telegram_id).first()
        
        if not user:
            await update.message.reply_text("Please register first with /register")
            return
        
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)
        
        # Get tasks due today
        tasks = Task.query.filter(
            Task.user_id == user.id,
            Task.completed == False,
            Task.due_date >= today_start,
            Task.due_date < today_end
        ).order_by(Task.due_date).all()
        
        # Get calendar events for today
        events = CalendarEvent.query.filter(
            CalendarEvent.user_id == user.id,
            CalendarEvent.start_time >= today_start,
            CalendarEvent.start_time < today_end
        ).order_by(CalendarEvent.start_time).all()
        
        # If user has Google Calendar connected, fetch latest events
        if user.google_calendar_token:
            try:
                get_upcoming_events(user.id)
                # Refresh events after sync
                events = CalendarEvent.query.filter(
                    CalendarEvent.user_id == user.id,
                    CalendarEvent.start_time >= today_start,
                    CalendarEvent.start_time < today_end
                ).order_by(CalendarEvent.start_time).all()
            except Exception as e:
                logger.error(f"Failed to sync calendar: {e}")
        
        # Build the agenda message
        message = "📅 TODAY'S AGENDA\n\n"
        
        if not tasks and not events:
            message += "Your schedule is clear for today! 🎉"
            await update.message.reply_text(message)
            return
        
        if tasks:
            message += "📝 TASKS:\n"
            for i, task in enumerate(tasks, 1):
                due_time = task.due_date.strftime("%H:%M") if task.due_date else "No time"
                message += f"{i}. {task.title} - {due_time}\n"
            message += "\n"
        
        if events:
            message += "🗓️ EVENTS:\n"
            for i, event in enumerate(events, 1):
                start_time = event.start_time.strftime("%H:%M")
                message += f"{i}. {event.title} - {start_time}\n"
        
        await update.message.reply_text(message)


async def tomorrow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show tomorrow's agenda with tasks and calendar events."""
    from app import app
    
    telegram_id = str(update.effective_user.id)
    
    with app.app_context():
        user = User.query.filter_by(telegram_id=telegram_id).first()
        
        if not user:
            await update.message.reply_text("Please register first with /register")
            return
        
        tomorrow_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        tomorrow_end = tomorrow_start + timedelta(days=1)
        
        # Get tasks due tomorrow
        tasks = Task.query.filter(
            Task.user_id == user.id,
            Task.completed == False,
            Task.due_date >= tomorrow_start,
            Task.due_date < tomorrow_end
        ).order_by(Task.due_date).all()
        
        # Get calendar events for tomorrow
        events = CalendarEvent.query.filter(
            CalendarEvent.user_id == user.id,
            CalendarEvent.start_time >= tomorrow_start,
            CalendarEvent.start_time < tomorrow_end
        ).order_by(CalendarEvent.start_time).all()
        
        # If user has Google Calendar connected, fetch latest events
        if user.google_calendar_token:
            try:
                get_upcoming_events(user.id)
                # Refresh events after sync
                events = CalendarEvent.query.filter(
                    CalendarEvent.user_id == user.id,
                    CalendarEvent.start_time >= tomorrow_start,
                    CalendarEvent.start_time < tomorrow_end
                ).order_by(CalendarEvent.start_time).all()
            except Exception as e:
                logger.error(f"Failed to sync calendar: {e}")
        
        # Build the agenda message
        message = "📅 TOMORROW'S AGENDA\n\n"
        
        if not tasks and not events:
            message += "Your schedule is clear for tomorrow! 🎉"
            await update.message.reply_text(message)
            return
        
        if tasks:
            message += "📝 TASKS:\n"
            for i, task in enumerate(tasks, 1):
                due_time = task.due_date.strftime("%H:%M") if task.due_date else "No time"
                message += f"{i}. {task.title} - {due_time}\n"
            message += "\n"
        
        if events:
            message += "🗓️ EVENTS:\n"
            for i, event in enumerate(events, 1):
                start_time = event.start_time.strftime("%H:%M")
                message += f"{i}. {event.title} - {start_time}\n"
        
        await update.message.reply_text(message)


async def reminders(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show and manage reminders."""
    from app import app
    
    telegram_id = str(update.effective_user.id)
    
    with app.app_context():
        user = User.query.filter_by(telegram_id=telegram_id).first()
        
        if not user:
            await update.message.reply_text("Please register first with /register")
            return
        
        active_reminders = Reminder.query.filter_by(user_id=user.id, active=True).all()
        
        if not active_reminders:
            await update.message.reply_text(
                "You don't have any active reminders.\n\n"
                "Use /water_reminder to set up hydration reminders."
            )
            return
        
        message = "🔔 YOUR ACTIVE REMINDERS:\n\n"
        
        for i, reminder in enumerate(active_reminders, 1):
            reminder_type = reminder.type.capitalize()
            repeat = f"Every {reminder.repeat_interval} minutes" if reminder.repeat_interval else "One-time"
            next_time = reminder.scheduled_time.strftime("%Y-%m-%d %H:%M") if reminder.scheduled_time > datetime.utcnow() else "Soon"
            
            message += f"{i}. {reminder_type} reminder\n"
            message += f"   Next: {next_time}\n"
            message += f"   Repeat: {repeat}\n\n"
        
        keyboard = [
            [InlineKeyboardButton("Add Water Reminder", callback_data="add_water")],
            [InlineKeyboardButton("Pause All Reminders", callback_data="pause_all")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(message, reply_markup=reply_markup)


async def reminder_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle reminder management callbacks."""
    from app import app
    
    query = update.callback_query
    await query.answer()
    
    telegram_id = str(update.effective_user.id)
    action = query.data
    
    with app.app_context():
        user = User.query.filter_by(telegram_id=telegram_id).first()
        
        if not user:
            await query.edit_message_text("Please register first with /register")
            return
        
        if action == "add_water":
            # Show water reminder setup
            keyboard = [
                [
                    InlineKeyboardButton("30 min", callback_data="water_30"),
                    InlineKeyboardButton("1 hour", callback_data="water_60")
                ],
                [
                    InlineKeyboardButton("2 hours", callback_data="water_120"),
                    InlineKeyboardButton("Back", callback_data="reminders_back")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                "How often would you like to be reminded to drink water?",
                reply_markup=reply_markup
            )
        
        elif action == "pause_all":
            # Pause all active reminders
            reminders = Reminder.query.filter_by(user_id=user.id, active=True).all()
            
            for reminder in reminders:
                reminder.active = False
            
            db.session.commit()
            
            await query.edit_message_text("All reminders have been paused.")
        
        elif action == "reminders_back":
            # Go back to reminders list
            active_reminders = Reminder.query.filter_by(user_id=user.id, active=True).all()
            
            message = "🔔 YOUR ACTIVE REMINDERS:\n\n"
            
            if not active_reminders:
                message = "You don't have any active reminders.\n\n"
            else:
                for i, reminder in enumerate(active_reminders, 1):
                    reminder_type = reminder.type.capitalize()
                    repeat = f"Every {reminder.repeat_interval} minutes" if reminder.repeat_interval else "One-time"
                    next_time = reminder.scheduled_time.strftime("%Y-%m-%d %H:%M") if reminder.scheduled_time > datetime.utcnow() else "Soon"
                    
                    message += f"{i}. {reminder_type} reminder\n"
                    message += f"   Next: {next_time}\n"
                    message += f"   Repeat: {repeat}\n\n"
            
            keyboard = [
                [InlineKeyboardButton("Add Water Reminder", callback_data="add_water")],
                [InlineKeyboardButton("Pause All Reminders", callback_data="pause_all")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(message, reply_markup=reply_markup)


def initialize_bot(token):
    """Initialize and start the Telegram bot."""
    global application
    
    # Create the Application and pass it your bot's token
    application = Application.builder().token(token).build()
    
    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("register", register))
    application.add_handler(CommandHandler("connect_calendar", connect_calendar))
    application.add_handler(CommandHandler("add_task", add_task))
    application.add_handler(CommandHandler("list_tasks", list_tasks))
    application.add_handler(CommandHandler("complete_task", complete_task))
    application.add_handler(CommandHandler("water_reminder", water_reminder))
    application.add_handler(CommandHandler("today", today))
    application.add_handler(CommandHandler("tomorrow", tomorrow))
    application.add_handler(CommandHandler("reminders", reminders))
    
    # Add callback query handlers
    application.add_handler(CallbackQueryHandler(water_callback, pattern="^water_"))
    application.add_handler(CallbackQueryHandler(reminder_callback, pattern="^(add_water|pause_all|reminders_back)$"))
    
    # Start the Bot in a separate thread
    def start_polling():
        if application is not None:
            import asyncio
            # Create a new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            # Run the bot with the new event loop
            application.run_polling(stop_signals=None)
        else:
            logger.error("Cannot start polling: application is None")
            
    threading.Thread(target=start_polling, daemon=True).start()
    
    logger.info("Bot started!")
    
    return application


def stop_bot():
    """Stop the Telegram bot."""
    global application
    if application:
        application.stop()
        logger.info("Bot stopped!")
