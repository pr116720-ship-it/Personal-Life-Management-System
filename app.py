from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from database import mysql
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime
import os
import random

app = Flask(__name__)

app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'super-secret-key-change-in-production')
app.config['MYSQL_HOST'] = os.environ.get('MYSQL_HOST', 'localhost')
app.config['MYSQL_USER'] = os.environ.get('MYSQL_USER', 'root')
app.config['MYSQL_PASSWORD'] = os.environ.get('MYSQL_PASSWORD', '')
app.config['MYSQL_DB'] = os.environ.get('MYSQL_DB', 'life_management')
app.config['MYSQL_PORT'] = int(os.environ.get('MYSQL_PORT', 3306))

mysql.init_app(app)

# --- Upload Directory Config ---
UPLOAD_FOLDER = 'static/profile_pics'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Ensure target directories exist
os.makedirs(os.path.join(app.root_path, UPLOAD_FOLDER), exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- Cache Control Middleware (Security) ---
@app.after_request
def add_header(response):
    # Prevent browser caching of authenticated routes (blocks BACK button security bypass)
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

# --- Authentication Helpers ---
def is_logged_in():
    return 'user_id' in session

# --- Merged Context Processor for Active User & Sidebar ---
@app.context_processor
def inject_user_context():
    if 'user_id' in session:
        cur = mysql.connection.cursor()
        # Fetch user detail columns
        cur.execute("SELECT username, email, full_name, profile_pic, theme, notifications_enabled, id FROM users WHERE id = %s", [session['user_id']])
        user = cur.fetchone()
        
        # Fetch status counts
        cur.execute("SELECT status FROM user_tasks WHERE user_id = %s", [session['user_id']])
        tasks = cur.fetchall()
        cur.close()
        
        pending = sum(1 for t in tasks if t[0] == 'Pending')
        completed = sum(1 for t in tasks if t[0] == 'Completed')
        
        if user:
            return dict(
                username=user[0],
                email=user[1],
                full_name=user[2] or '',
                profile_pic=user[3] or 'default_profile.png',
                theme=user[4] or 'dark',
                notifications_enabled=bool(user[5]),
                user_id=user[6],
                sb_pending=pending,
                sb_completed=completed
            )
    return dict(
        username='Guest',
        email='',
        full_name='',
        profile_pic='default_profile.png',
        theme='dark',
        notifications_enabled=True,
        user_id=0,
        sb_pending=0,
        sb_completed=0
    )

# --- Routes ---

@app.before_request
def restrict_access():
    # Define public/allowed routes that don't require authentication
    allowed_endpoints = ['home', 'login', 'register', 'logout', 'static']
    
    # If request is for an endpoint we don't recognize, let Flask handle it (e.g. 404 handler)
    if request.endpoint is None:
        return
        
    # If the user tries to access a protected endpoint without being logged in
    if request.endpoint not in allowed_endpoints:
        if 'user_id' not in session:
            # Handle API requests gracefully with a 401 JSON response
            if request.path.startswith('/api/'):
                return jsonify({'error': 'Unauthorized, please log in.'}), 401
            # Handle regular page requests by redirecting to login with a warning toast
            flash("Please log in to access this page.", "danger")
            return redirect(url_for('login'))

@app.route('/')
def home():
    if is_logged_in():
        return redirect(url_for('dashboard'))
    return render_template("index.html")

@app.route('/login', methods=['GET', 'POST'])
def login():
    if is_logged_in():
        return redirect(url_for('dashboard'))
        
    error = None
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        cur = mysql.connection.cursor()
        cur.execute("SELECT id, username, password_hash FROM users WHERE email = %s", [email])
        user = cur.fetchone()
        
        if user and check_password_hash(user[2], password):
            session['user_id'] = user[0]
            session['username'] = user[1]
            
            # Log login activity
            cur.execute("INSERT INTO activity_log (user_id, activity) VALUES (%s, %s)", (user[0], 'Logged in successfully'))
            mysql.connection.commit()
            cur.close()
            return redirect(url_for('dashboard'))
        else:
            if user:
                cur.close()
            error = 'Invalid Email or Password.'
            
    return render_template("login.html", error=error)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if is_logged_in():
        return redirect(url_for('dashboard'))
        
    error = None
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        
        hashed_password = generate_password_hash(password)
        
        cur = mysql.connection.cursor()
        # Check if email exists
        cur.execute("SELECT id FROM users WHERE email = %s", [email])
        if cur.fetchone():
            error = "Email is already registered."
            cur.close()
        else:
            cur.execute("INSERT INTO users (username, email, password_hash) VALUES (%s, %s, %s)", 
                        (username, email, hashed_password))
            user_id = cur.lastrowid
            
            # Log registration activity
            cur.execute("INSERT INTO activity_log (user_id, activity) VALUES (%s, %s)", (user_id, 'Registered account'))
            mysql.connection.commit()
            cur.close()
            return redirect(url_for('login'))
            
    return render_template("register.html", error=error)

@app.route('/logout')
def logout():
    if 'user_id' in session:
        # Log logout activity before clearing session
        cur = mysql.connection.cursor()
        cur.execute("INSERT INTO activity_log (user_id, activity) VALUES (%s, %s)", (session['user_id'], 'Logged out successfully'))
        mysql.connection.commit()
        cur.close()
        
    session.clear()
    flash("Logged out successfully", "success")
    return redirect(url_for('login'))

@app.route('/dashboard')
def dashboard():
    if not is_logged_in():
        return redirect(url_for('login'))
        
    user_id = session['user_id']
    
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM user_tasks WHERE user_id = %s ORDER BY due_date ASC", [user_id])
    tasks = cur.fetchall()
    
    # Analytics
    total_tasks = len(tasks)
    completed_tasks = sum(1 for t in tasks if t[4] == 'Completed')
    pending_tasks = total_tasks - completed_tasks
    productivity = int((completed_tasks / total_tasks * 100)) if total_tasks > 0 else 0
    
    # Fetch username from DB to ensure always updated
    cur.execute("SELECT username FROM users WHERE id = %s", [user_id])
    username = cur.fetchone()[0]
    cur.close()
    
    # AI Suggestion Mock
    ai_suggestions = [
        "Focus on High Priority tasks first.",
        "Take a 5-minute break after completing a task.",
        "Your productivity is peaking! Tackle a hard task now."
    ]
    suggestion = random.choice(ai_suggestions)

    return render_template(
        "dashboard.html",
        tasks=tasks,
        total_tasks=total_tasks,
        completed_tasks=completed_tasks,
        pending_tasks=pending_tasks,
        productivity=productivity,
        username=username,
        suggestion=suggestion
    )

@app.route('/addtask', methods=["POST"])
def addtask():
    if not is_logged_in():
        return redirect(url_for('login'))
        
    task_name = request.form['task_name']
    due_date = request.form['due_date']
    priority = request.form['priority']
    category = request.form['category']
    user_id = session['user_id']

    cur = mysql.connection.cursor()
    cur.execute(
        "INSERT INTO user_tasks (user_id, task_name, due_date, status, priority, category) VALUES (%s, %s, %s, %s, %s, %s)",
        (user_id, task_name, due_date, 'Pending', priority, category)
    )
    # Log activity
    cur.execute("INSERT INTO activity_log (user_id, activity) VALUES (%s, %s)", (user_id, f"Created task: '{task_name}'"))
    mysql.connection.commit()
    cur.close()
    flash("Task created successfully!", "success")
    return redirect(request.referrer or url_for('dashboard'))

@app.route('/delete/<int:id>')
def delete(id):
    if not is_logged_in():
        return redirect(url_for('login'))
        
    cur = mysql.connection.cursor()
    # Fetch task name first to log it nicely
    cur.execute("SELECT task_name FROM user_tasks WHERE id=%s AND user_id=%s", (id, session['user_id']))
    task = cur.fetchone()
    if task:
        task_name = task[0]
        cur.execute("DELETE FROM user_tasks WHERE id=%s AND user_id=%s", (id, session['user_id']))
        cur.execute("INSERT INTO activity_log (user_id, activity) VALUES (%s, %s)", (session['user_id'], f"Deleted task: '{task_name}'"))
        mysql.connection.commit()
    cur.close()
    flash("Task deleted.", "info")
    return redirect(request.referrer or url_for('dashboard'))

@app.route('/complete/<int:id>')
def complete(id):
    if not is_logged_in():
        return redirect(url_for('login'))
        
    cur = mysql.connection.cursor()
    # Fetch task name first to log it nicely
    cur.execute("SELECT task_name FROM user_tasks WHERE id=%s AND user_id=%s", (id, session['user_id']))
    task = cur.fetchone()
    if task:
        task_name = task[0]
        cur.execute("UPDATE user_tasks SET status='Completed' WHERE id=%s AND user_id=%s", (id, session['user_id']))
        cur.execute("INSERT INTO activity_log (user_id, activity) VALUES (%s, %s)", (session['user_id'], f"Completed task: '{task_name}'"))
        mysql.connection.commit()
    cur.close()
    flash("Task marked as completed!", "success")
    return redirect(request.referrer or url_for('dashboard'))
    
@app.route('/api/update_task_status', methods=['POST'])
def update_task_status():
    if not is_logged_in():
        return jsonify({'error': 'Unauthorized'}), 401
        
    data = request.get_json()
    task_id = data.get('task_id')
    new_status = data.get('status')
    
    cur = mysql.connection.cursor()
    cur.execute("SELECT task_name FROM user_tasks WHERE id=%s AND user_id=%s", (task_id, session['user_id']))
    task = cur.fetchone()
    if task:
        task_name = task[0]
        cur.execute("UPDATE user_tasks SET status=%s WHERE id=%s AND user_id=%s", (new_status, task_id, session['user_id']))
        cur.execute("INSERT INTO activity_log (user_id, activity) VALUES (%s, %s)", (session['user_id'], f"Marked task '{task_name}' as {new_status}"))
        mysql.connection.commit()
    cur.close()
    
    return jsonify({'success': True})

@app.route('/edit_task/<int:id>', methods=['POST'])
def edit_task(id):
    if not is_logged_in():
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
        
    data = request.json
    task_name = data.get('task_name')
    due_date = data.get('due_date')
    priority = data.get('priority')
    category = data.get('category')
    status = data.get('status')
    description = data.get('description', '')
    
    if not task_name or not due_date:
        return jsonify({"status": "error", "message": "Task name and due date are required"}), 400
    
    cur = mysql.connection.cursor()
    cur.execute(
        "UPDATE user_tasks SET task_name=%s, due_date=%s, priority=%s, category=%s, status=%s, description=%s WHERE id=%s AND user_id=%s",
        (task_name, due_date, priority, category, status, description, id, session['user_id'])
    )
    cur.execute("INSERT INTO activity_log (user_id, activity) VALUES (%s, %s)", (session['user_id'], f"Edited details of task: '{task_name}'"))
    mysql.connection.commit()
    cur.close()
    
    return jsonify({
        "status": "success", 
        "message": "Task updated successfully!",
        "task": {
            "id": id,
            "name": task_name,
            "date": due_date,
            "priority": priority,
            "category": category,
            "status": status,
            "description": description
        }
    })

@app.route('/analytics')
def analytics():
    if not is_logged_in():
        return redirect(url_for('login'))
        
    user_id = session['user_id']
    
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM user_tasks WHERE user_id = %s", [user_id])
    tasks = cur.fetchall()
    
    total_tasks = len(tasks)
    completed_tasks = sum(1 for t in tasks if t[4] == 'Completed')
    pending_tasks = total_tasks - completed_tasks
    productivity = int((completed_tasks / total_tasks * 100)) if total_tasks > 0 else 0
    
    # Category Analytics Calculation
    categories = ['Work', 'Personal', 'Health', 'Finance', 'General']
    cat_stats = []
    
    for c in categories:
        c_tasks = [t for t in tasks if t[6] == c]
        c_total = len(c_tasks)
        if c_total > 0:
            c_comp = sum(1 for t in c_tasks if t[4] == 'Completed')
            c_pend = c_total - c_comp
            c_perc = int((c_comp / c_total) * 100)
            
            if c_perc >= 80:
                color = 'success'
                status = 'On Track'
            elif c_perc >= 40:
                color = 'warning'
                status = 'In Progress'
            else:
                color = 'danger'
                status = 'Needs Attention'
                
            cat_stats.append({
                'name': c,
                'total': c_total,
                'completed': c_comp,
                'pending': c_pend,
                'percentage': c_perc,
                'color': color,
                'status': status
            })

    # Fetch username from DB to ensure always updated
    cur.execute("SELECT username FROM users WHERE id = %s", [user_id])
    username = cur.fetchone()[0]
    cur.close()

    return render_template(
        "analytics.html",
        total_tasks=total_tasks,
        completed_tasks=completed_tasks,
        pending_tasks=pending_tasks,
        productivity=productivity,
        username=username,
        cat_stats=cat_stats,
        total_categories=len(cat_stats)
    )

@app.route('/calendar')
def calendar_view():
    if not is_logged_in():
        return redirect(url_for('login'))
        
    user_id = session['user_id']
    
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM user_tasks WHERE user_id = %s", [user_id])
    tasks = cur.fetchall()
    
    current_month = datetime.now().month
    current_year = datetime.now().year
    
    # Calculate monthly progress
    month_tasks = [t for t in tasks if t[3].month == current_month and t[3].year == current_year]
    total_month = len(month_tasks)
    completed_month = sum(1 for t in month_tasks if t[4] == 'Completed')
    month_progress = int((completed_month / total_month * 100)) if total_month > 0 else 0
    
    # Fetch username from DB to ensure always updated
    cur.execute("SELECT username FROM users WHERE id = %s", [user_id])
    username = cur.fetchone()[0]
    cur.close()
    
    return render_template(
        "calendar.html",
        tasks=tasks,
        username=username,
        month_progress=month_progress,
        completed_month=completed_month,
        total_month=total_month
    )

@app.route('/tasks')
def tasks_view():
    if not is_logged_in():
        return redirect(url_for('login'))
        
    user_id = session['user_id']
    
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM user_tasks WHERE user_id = %s", [user_id])
    tasks = cur.fetchall()
    
    # Fetch username from DB to ensure always updated
    cur.execute("SELECT username FROM users WHERE id = %s", [user_id])
    username = cur.fetchone()[0]
    cur.close()
    
    return render_template(
        "tasks.html",
        tasks=tasks,
        username=username
    )

# --- Profile & Settings Routes ---

@app.route('/profile')
def profile():
    if not is_logged_in():
        return redirect(url_for('login'))
        
    user_id = session['user_id']
    cur = mysql.connection.cursor()
    
    # Fetch User data
    cur.execute("SELECT username, email, full_name, phone, dob, gender, profile_pic, theme, notifications_enabled, created_at, id FROM users WHERE id = %s", [user_id])
    user = cur.fetchone()
    
    if not user:
        cur.close()
        session.clear()
        return redirect(url_for('login'))
        
    # Fetch Tasks for stats
    cur.execute("SELECT status FROM user_tasks WHERE user_id = %s", [user_id])
    tasks = cur.fetchall()
    
    # Fetch Activity Log
    cur.execute("SELECT activity, created_at FROM activity_log WHERE user_id = %s ORDER BY created_at DESC LIMIT 10", [user_id])
    activities = cur.fetchall()
    cur.close()
    
    # Process stats
    total_tasks = len(tasks)
    completed_tasks = sum(1 for t in tasks if t[0] == 'Completed')
    pending_tasks = total_tasks - completed_tasks
    productivity = int((completed_tasks / total_tasks * 100)) if total_tasks > 0 else 0
    
    # Badges
    badges = []
    if completed_tasks >= 10:
        badges.append({
            'name': 'Task Master',
            'icon': 'fa-crown text-warning',
            'desc': 'Completed 10 or more tasks!'
        })
    if productivity >= 80 and completed_tasks >= 5:
        badges.append({
            'name': 'Productivity Star',
            'icon': 'fa-star text-info',
            'desc': 'Maintained >= 80% productivity with at least 5 tasks completed!'
        })
    if completed_tasks >= 1 and pending_tasks == 0:
        badges.append({
            'name': 'Goal Achiever',
            'icon': 'fa-trophy text-success',
            'desc': 'No pending tasks left, all goals achieved!'
        })
        
    return render_template(
        "profile.html",
        user=user,
        total_tasks=total_tasks,
        completed_tasks=completed_tasks,
        pending_tasks=pending_tasks,
        productivity=productivity,
        activities=activities,
        badges=badges
    )

@app.route('/profile/update', methods=['POST'])
def update_profile():
    if not is_logged_in():
        return redirect(url_for('login'))
        
    user_id = session['user_id']
    username = request.form.get('username')
    email = request.form.get('email')
    full_name = request.form.get('full_name')
    phone = request.form.get('phone')
    dob = request.form.get('dob')
    gender = request.form.get('gender')
    
    cur = mysql.connection.cursor()
    
    # Check email unique constraint if changed
    cur.execute("SELECT id FROM users WHERE email = %s AND id != %s", (email, user_id))
    if cur.fetchone():
        flash("Email is already taken by another user.", "danger")
        cur.close()
        return redirect(url_for('profile'))
        
    cur.execute(
        "UPDATE users SET username=%s, email=%s, full_name=%s, phone=%s, dob=%s, gender=%s WHERE id=%s",
        (username, email, full_name, phone, dob or None, gender, user_id)
    )
    
    session['username'] = username
    
    cur.execute("INSERT INTO activity_log (user_id, activity) VALUES (%s, %s)", (user_id, 'Updated profile details'))
    mysql.connection.commit()
    cur.close()
    
    flash("Profile updated successfully!", "success")
    return redirect(url_for('profile'))

@app.route('/profile/change_password', methods=['POST'])
def change_password():
    if not is_logged_in():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    current_password = request.form.get('current_password')
    new_password = request.form.get('new_password')
    confirm_password = request.form.get('confirm_password')
    
    if new_password != confirm_password:
        return jsonify({'success': False, 'message': 'New passwords do not match'}), 400
        
    cur = mysql.connection.cursor()
    cur.execute("SELECT password_hash FROM users WHERE id = %s", [session['user_id']])
    user = cur.fetchone()
    
    if not user or not check_password_hash(user[0], current_password):
        cur.close()
        return jsonify({'success': False, 'message': 'Incorrect current password'}), 400
        
    new_hash = generate_password_hash(new_password)
    cur.execute("UPDATE users SET password_hash = %s WHERE id = %s", (new_hash, session['user_id']))
    cur.execute("INSERT INTO activity_log (user_id, activity) VALUES (%s, %s)", (session['user_id'], 'Changed account password'))
    
    mysql.connection.commit()
    cur.close()
    
    return jsonify({'success': True, 'message': 'Password changed successfully!'})

@app.route('/profile/upload_pic', methods=['POST'])
def upload_pic():
    if not is_logged_in():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
        
    if 'profile_pic' not in request.files:
        return jsonify({'success': False, 'message': 'No file part'}), 400
        
    file = request.files['profile_pic']
    if file.filename == '':
        return jsonify({'success': False, 'message': 'No selected file'}), 400
        
    if file and allowed_file(file.filename):
        ext = file.filename.rsplit('.', 1)[1].lower()
        filename = f"profile_{session['user_id']}_{int(datetime.now().timestamp())}.{ext}"
        
        # Save to static/profile_pics/
        file_path = os.path.join(app.root_path, 'static', 'profile_pics', filename)
        file.save(file_path)
        
        cur = mysql.connection.cursor()
        
        # Fetch old profile pic to delete it
        cur.execute("SELECT profile_pic FROM users WHERE id = %s", [session['user_id']])
        old_pic = cur.fetchone()
        if old_pic and old_pic[0] and old_pic[0] != 'default_profile.png':
            try:
                old_path = os.path.join(app.root_path, 'static', 'profile_pics', old_pic[0])
                if os.path.exists(old_path):
                    os.remove(old_path)
            except Exception as e:
                print(f"Error removing old profile picture: {e}")
                
        cur.execute("UPDATE users SET profile_pic = %s WHERE id = %s", (filename, session['user_id']))
        cur.execute("INSERT INTO activity_log (user_id, activity) VALUES (%s, %s)", (session['user_id'], 'Updated profile picture'))
        
        mysql.connection.commit()
        cur.close()
        
        return jsonify({'success': True, 'message': 'Profile picture updated!', 'filepath': url_for('static', filename='profile_pics/' + filename)})
        
    return jsonify({'success': False, 'message': 'Invalid file type'}), 400

@app.route('/profile/update_settings', methods=['POST'])
def update_settings():
    if not is_logged_in():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
        
    data = request.get_json()
    theme = data.get('theme')
    notifications = data.get('notifications')
    
    cur = mysql.connection.cursor()
    if theme is not None:
        cur.execute("UPDATE users SET theme = %s WHERE id = %s", (theme, session['user_id']))
        cur.execute("INSERT INTO activity_log (user_id, activity) VALUES (%s, %s)", (session['user_id'], f'Changed theme preference to {theme}'))
    
    if notifications is not None:
        val = 1 if notifications else 0
        cur.execute("UPDATE users SET notifications_enabled = %s WHERE id = %s", (val, session['user_id']))
        status_str = 'enabled' if notifications else 'disabled'
        cur.execute("INSERT INTO activity_log (user_id, activity) VALUES (%s, %s)", (session['user_id'], f'Toggled notifications to {status_str}'))
        
    mysql.connection.commit()
    cur.close()
    
    return jsonify({'success': True, 'message': 'Settings updated!'})

if __name__ == "__main__":
    app.run(debug=os.environ.get('FLASK_DEBUG', 'False').lower() == 'true')