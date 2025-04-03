/**
 * Dashboard JavaScript for ADHD Assistant Bot
 * Enhances the dashboard with dynamic interactions and functionality
 */
document.addEventListener('DOMContentLoaded', function() {
    console.log('Dashboard loaded');
    
    // Set default due date for new tasks to tomorrow
    setupTaskDefaults();
    
    // Enable alert auto-dismissal
    setupAlertDismissal();
    
    // Setup task priority visual cues
    setupTaskPriorityUI();
    
    // Initialize tooltips and popovers if available
    initializeBootstrapComponents();
    
    // Setup live time update
    setupLiveTimeUpdate();
});

/**
 * Sets default values for the task creation form
 */
function setupTaskDefaults() {
    const dueDateInput = document.getElementById('due_date');
    if (dueDateInput) {
        // Set default due date to tomorrow at noon
        const tomorrow = new Date();
        tomorrow.setDate(tomorrow.getDate() + 1);
        tomorrow.setHours(12, 0, 0, 0);
        
        // Format as YYYY-MM-DDTHH:MM
        const year = tomorrow.getFullYear();
        const month = String(tomorrow.getMonth() + 1).padStart(2, '0');
        const day = String(tomorrow.getDate()).padStart(2, '0');
        const hours = String(tomorrow.getHours()).padStart(2, '0');
        const minutes = String(tomorrow.getMinutes()).padStart(2, '0');
        
        dueDateInput.value = `${year}-${month}-${day}T${hours}:${minutes}`;
    }
}

/**
 * Sets up auto-dismissal for alert messages after 5 seconds
 */
function setupAlertDismissal() {
    const alerts = document.querySelectorAll('.alert:not(.alert-danger)');
    
    alerts.forEach(alert => {
        // Set timeout to automatically dismiss non-error alerts after 5 seconds
        setTimeout(() => {
            const bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
        }, 5000);
    });
}

/**
 * Adds visual cues for task priorities
 */
function setupTaskPriorityUI() {
    const taskItems = document.querySelectorAll('.list-group-item');
    
    taskItems.forEach(item => {
        // Look for priority indicators in the task text
        const taskTitle = item.querySelector('h5');
        if (taskTitle) {
            // Check if title contains priority indicators
            const title = taskTitle.textContent;
            
            if (title.includes('high') || title.includes('urgent') || title.includes('important')) {
                item.classList.add('border-danger');
                
                // Add priority badge if not already present
                if (!item.querySelector('.badge-priority')) {
                    const badge = document.createElement('span');
                    badge.className = 'badge bg-danger badge-priority ms-2';
                    badge.textContent = 'High Priority';
                    taskTitle.appendChild(badge);
                }
            }
        }
    });
}

/**
 * Initializes Bootstrap components like tooltips and popovers
 */
function initializeBootstrapComponents() {
    // Initialize all tooltips if any exist
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    if (tooltipTriggerList.length > 0) {
        tooltipTriggerList.map(function (tooltipTriggerEl) {
            return new bootstrap.Tooltip(tooltipTriggerEl);
        });
    }
    
    // Initialize all popovers if any exist
    const popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'));
    if (popoverTriggerList.length > 0) {
        popoverTriggerList.map(function (popoverTriggerEl) {
            return new bootstrap.Popover(popoverTriggerEl);
        });
    }
}

/**
 * Sets up live time update in the dashboard
 */
function setupLiveTimeUpdate() {
    // Check if we have a time element to update
    const timeElement = document.getElementById('current-time');
    if (timeElement) {
        // Update current time every second
        setInterval(() => {
            const now = new Date();
            timeElement.textContent = now.toLocaleTimeString();
        }, 1000);
    }
}

/**
 * Mark task as completed with animation
 * @param {string} taskId - The ID of the task to mark as completed
 */
function completeTask(taskId) {
    const taskItem = document.querySelector(`[data-task-id="${taskId}"]`);
    if (taskItem) {
        // Add completion animation
        taskItem.classList.add('bg-success', 'bg-opacity-25');
        
        // Fade out the item
        setTimeout(() => {
            taskItem.style.opacity = '0.5';
            taskItem.style.textDecoration = 'line-through';
        }, 300);
        
        // Submit the form after animation
        setTimeout(() => {
            const form = taskItem.querySelector('form');
            if (form) {
                form.submit();
            }
        }, 800);
    }
}

/**
 * Confirm deletion of a reminder
 * @param {Event} event - The click event
 * @param {string} reminderName - Name of the reminder to delete
 */
function confirmDeleteReminder(event, reminderName) {
    if (!confirm(`Are you sure you want to delete the "${reminderName}" reminder?`)) {
        event.preventDefault();
        return false;
    }
    return true;
}

/**
 * Toggle the active state of a reminder with visual feedback
 * @param {string} reminderId - ID of the reminder to toggle
 */
function toggleReminder(reminderId) {
    const reminderItem = document.querySelector(`[data-reminder-id="${reminderId}"]`);
    if (reminderItem) {
        const toggleButton = reminderItem.querySelector('button');
        const currentState = toggleButton.textContent.trim();
        
        // Show processing state
        toggleButton.disabled = true;
        toggleButton.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>';
        
        // Submit the form to toggle state
        const form = reminderItem.querySelector('form');
        if (form) {
            form.submit();
        }
    }
}

/**
 * Setup character count display for text inputs with maxlength
 */
document.addEventListener('input', function(e) {
    if (e.target.hasAttribute('maxlength')) {
        const maxLength = parseInt(e.target.getAttribute('maxlength'));
        const currentLength = e.target.value.length;
        
        // Find or create counter element
        let counter = e.target.nextElementSibling;
        if (!counter || !counter.classList.contains('char-counter')) {
            counter = document.createElement('small');
            counter.classList.add('char-counter', 'text-muted', 'd-block', 'text-end');
            e.target.parentNode.insertBefore(counter, e.target.nextSibling);
        }
        
        // Update counter
        counter.textContent = `${currentLength}/${maxLength}`;
        
        // Add warning class if approaching limit
        if (currentLength > maxLength * 0.8) {
            counter.classList.add('text-warning');
        } else {
            counter.classList.remove('text-warning');
        }
    }
});

/**
 * Handler for modal shown event to focus on first input
 */
document.addEventListener('shown.bs.modal', function(event) {
    // Focus the first input in the modal that was just shown
    const firstInput = event.target.querySelector('input, textarea, select');
    if (firstInput) {
        firstInput.focus();
    }
});
