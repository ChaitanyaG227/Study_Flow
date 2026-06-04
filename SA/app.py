
from flask import Flask, render_template, url_for, request, redirect, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import os
from datetime import datetime, date, timedelta
from sqlalchemy import or_
from sqlalchemy import Table
from functools import wraps
from werkzeug.utils import secure_filename
import google.generativeai as genai
from PyPDF2 import PdfReader
from sentence_transformers import SentenceTransformer
import faiss
import numpy as np
import pickle
from datetime import time # Add this to your imports

# --- App Configuration ---
app = Flask(__name__,
            template_folder=os.path.abspath('templates'),
            static_folder=os.path.abspath('static'))
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'static/materials')
app.config['SECRET_KEY'] = 'a-very-secret-key-that-should-be-changed'
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///local.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['AVATAR_UPLOAD_FOLDER'] = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'static/avatars')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
genai.configure(api_key=GEMINI_API_KEY)
# Load the model for creating embeddings
embedding_model = SentenceTransformer('all-MiniLM-L6-v2')

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
           
db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth'

# --- Association Table for Saved Materials (Many-to-Many) ---
saved_material_association = db.Table('saved_material',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('material_id', db.Integer, db.ForeignKey('material.id'), primary_key=True)
)

# --- Database Models ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    email = db.Column(db.String(100), unique=True)
    password = db.Column(db.String(100))
    user_class = db.Column(db.String(50))
    tasks = db.relationship('Task', backref='user', lazy=True, cascade="all, delete-orphan")
    study_sessions = db.relationship('StudySession', backref='user', lazy=True, cascade="all, delete-orphan")
    is_admin = db.Column(db.Boolean, default=False)
    avatar_filename = db.Column(db.String(100), nullable=True)
    pomodoro_work_minutes = db.Column(db.Integer, default=25)
    pomodoro_short_break = db.Column(db.Integer, default=5)
    pomodoro_long_break = db.Column(db.Integer, default=15)
    # Relationships
    uploaded_materials = db.relationship('Material', backref='uploader', lazy=True)
    saved_materials = db.relationship('Material', secondary=saved_material_association, lazy='subquery',
                                      backref=db.backref('saved_by_users', lazy=True))

class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.String(200), nullable=False)
    subject = db.Column(db.String(50))
    deadline = db.Column(db.Date)
    estimated_hours = db.Column(db.Float)
    priority = db.Column(db.String(20))
    completed = db.Column(db.Boolean, default=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

class StudySession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date_completed = db.Column(db.Date, nullable=False, default=date.today)
    hours_spent = db.Column(db.Float, nullable=False)
    subject = db.Column(db.String(50), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

class Goal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    subject = db.Column(db.String(50), nullable=False)
    target_hours = db.Column(db.Float, nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
# --- New Material Model ---
class Material(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(100), nullable=False)
    filepath = db.Column(db.String(200), nullable=False)
    subject = db.Column(db.String(50), nullable=False)
    user_class = db.Column(db.String(50), nullable=False)
    description = db.Column(db.Text)
    upload_date = db.Column(db.DateTime, default=datetime.utcnow)
    is_approved = db.Column(db.Boolean, default=False)
    uploader_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
class AvailabilityBlock(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    day_of_week = db.Column(db.Integer, nullable=False) # Monday=0, Sunday=6
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

class SessionProgress(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    completed_steps = db.Column(db.Integer, default=0)
    task_id = db.Column(db.Integer, db.ForeignKey('task.id'), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# --- Intelligent Scheduling Algorithm ---
def generate_schedule(tasks):
    schedule = []
    today = date.today()
    uncompleted_tasks = [task for task in tasks if not task.completed]
    if not uncompleted_tasks:
        return []

    # --- NEW: Fetch user's availability ---
    availability_blocks = AvailabilityBlock.query.filter_by(user_id=current_user.id).all()
    
    # Create a simple lookup for blocked hours
    blocked_hours = {i: [] for i in range(7)} # {0: [time(9,0), time(10,0)], 1: [...]}
    for block in availability_blocks:
        start = block.start_time.hour
        end = block.end_time.hour
        for hour in range(start, end):
            blocked_hours[block.day_of_week].append(time(hour, 0))
    # --- END NEW ---

    task_metrics = []
    for task in uncompleted_tasks:
        days_left = (task.deadline - today).days
        priority_map = {'High': 3, 'Medium': 2, 'Low': 1}
        priority_score = priority_map.get(task.priority, 2)
        urgency_score = (priority_score * 10) / (max(0, days_left) + 1)
        task_metrics.append({'task': task, 'urgency': urgency_score})

    sorted_tasks = sorted(task_metrics, key=lambda x: x['urgency'], reverse=True)

    # --- MODIFIED: Schedule for the next 7 days ---
    scheduled_tasks_count = 0
    day_offset = 0
    while scheduled_tasks_count < min(len(sorted_tasks), 7) and day_offset < 30:
        current_day = today + timedelta(days=day_offset)
        day_of_week = current_day.weekday()
        
        # Check if there's an available slot on this day (e.g., after 9am)
        found_slot = False
        for hour in range(9, 22): # Let's assume study hours are 9am to 10pm
            slot_time = time(hour, 0)
            if slot_time not in blocked_hours[day_of_week]:
                found_slot = True
                break
        
        if found_slot:
            task_info = sorted_tasks[scheduled_tasks_count]
            day_str = "Today" if day_offset == 0 else "Tomorrow" if day_offset == 1 else current_day.strftime('%A, %b %d')
            details = f"At {slot_time.strftime('%I:%M %p')}. Priority: {task_info['task'].priority}."
            
            schedule.append({
                'day': day_str,
                'task_object': task_info['task'], # IMPORTANT: Pass the whole object
                'details': details
            })
            scheduled_tasks_count += 1
        
        day_offset += 1
        
    return schedule

# --- Admin Decorator ---
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_admin:
            flash('You do not have permission to access this page.', 'error')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

def process_and_store_embeddings(material_id, filepath):
    print(f"DEBUG: Starting to process material ID: {material_id}")
    try:
        reader = PdfReader(filepath)
        text = ""
        for page in reader.pages:
            text += page.extract_text()
        
        print(f"DEBUG: Extracted {len(text)} characters from PDF.")

        if not text.strip():
            print("DEBUG: No text could be extracted. The PDF might be an image.")
            return

        chunks = [text[i:i + 1000] for i in range(0, len(text), 1000)]
        embeddings = embedding_model.encode(chunks)
        
        dimension = embeddings.shape[1]
        index = faiss.IndexFlatL2(dimension)
        index.add(np.array(embeddings).astype('float32'))

        vector_store_path = os.path.join(app.config['UPLOAD_FOLDER'], f'vs_{material_id}')
        os.makedirs(vector_store_path, exist_ok=True)
        
        index_file = os.path.join(vector_store_path, 'index.faiss')
        chunks_file = os.path.join(vector_store_path, 'chunks.pkl')
        faiss.write_index(index, index_file)
        with open(chunks_file, 'wb') as f:
            pickle.dump(chunks, f)

        print(f"DEBUG: Successfully created memory files at {vector_store_path}")

    except Exception as e:
        print(f"!!!!!!!! ERROR processing PDF for material {material_id}: {e}")
        
# --- Web Routes ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/auth', methods=['GET', 'POST'])
def auth():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        form_name = request.form.get('form_name')
        if form_name == 'register':
            email = request.form.get('email')
            name = request.form.get('name')
            user_class = request.form.get('user_class')
            password = request.form.get('password')
            user = User.query.filter_by(email=email).first()
            if user:
                flash('Email address already exists.', 'error')
                return redirect(url_for('auth'))
            new_user = User(
                email=email, name=name, user_class=user_class,
                password=generate_password_hash(password, method='pbkdf2:sha256'))
            db.session.add(new_user)
            db.session.commit()
            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('auth'))
        elif form_name == 'login':
            email = request.form.get('email')
            password = request.form.get('password')
            user = User.query.filter_by(email=email).first()
            if not user or not check_password_hash(user.password, password):
                flash('Please check your login details and try again.', 'error')
                return redirect(url_for('auth'))
            login_user(user)
            return redirect(url_for('dashboard'))
    return render_template('auth.html')

@app.route('/dashboard')
@login_required
def dashboard():
    search_query = request.args.get('q', '')
    base_query = Task.query.filter_by(user_id=current_user.id)
    if search_query:
        tasks = base_query.filter(or_(Task.content.ilike(f'%{search_query}%'), Task.subject.ilike(f'%{search_query}%'))).order_by(Task.deadline).all()
    else:
        tasks = base_query.order_by(Task.deadline).all()
    schedule = generate_schedule(tasks)
    return render_template('dashboard.html', name=current_user.name, tasks=tasks, schedule=schedule, search_query=search_query)

@app.route('/analytics')
@login_required
def analytics():
    return render_template('analytics.html', name=current_user.name)

@app.route('/calendar')
@login_required
def calendar():
    return render_template('calendar.html', name=current_user.name)

# --- Task Management ---
@app.route('/add', methods=['POST'])
@login_required
def add_task():
    try:
        content = request.form.get('content')
        subject = request.form.get('subject')
        deadline_str = request.form.get('deadline')
        hours = request.form.get('estimated_hours')
        priority = request.form.get('priority')
        if not all([content, subject, deadline_str, hours, priority]):
            flash('All fields are required.', 'error')
        else:
            new_task = Task(
                content=content, subject=subject, 
                deadline=datetime.strptime(deadline_str, '%Y-%m-%d').date(),
                estimated_hours=float(hours), priority=priority,
                user_id=current_user.id)
            db.session.add(new_task)
            db.session.commit()
            flash('Task added and schedule re-optimized!', 'success')
    except (ValueError, TypeError):
        flash('Invalid data submitted. Please check your inputs.', 'error')
    return redirect(url_for('dashboard'))

@app.route('/edit/<int:task_id>', methods=['GET', 'POST'])
@login_required
def edit_task(task_id):
    task = Task.query.filter_by(id=task_id, user_id=current_user.id).first_or_404()
    if request.method == 'POST':
        try:
            task.content = request.form['content']
            task.subject = request.form['subject']
            task.deadline = datetime.strptime(request.form['deadline'], '%Y-%m-%d').date()
            task.estimated_hours = float(request.form['estimated_hours'])
            task.priority = request.form['priority']
            db.session.commit()
            flash('Task updated successfully!', 'success')
            return redirect(url_for('dashboard'))
        except (ValueError, TypeError):
            flash('Invalid data submitted. Please check your inputs.', 'error')
    return render_template('edit_task.html', task=task, name=current_user.name)

@app.route('/update/<int:task_id>')
@login_required
def update_task(task_id):
    task = Task.query.filter_by(id=task_id, user_id=current_user.id).first_or_404()
    task.completed = not task.completed
    if task.completed:
        session = StudySession(
            hours_spent=task.estimated_hours,
            subject=task.subject,
            user_id=current_user.id)
        db.session.add(session)
        flash('Great job! Task completion logged for analytics.', 'success')
    db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/delete/<int:task_id>')
@login_required
def delete_task(task_id):
    task = Task.query.filter_by(id=task_id, user_id=current_user.id).first_or_404()
    db.session.delete(task)
    db.session.commit()
    flash('Task deleted successfully.', 'success')
    return redirect(url_for('dashboard'))

# --- API Endpoints ---
@app.route('/api/tasks')
@login_required
def api_tasks():
    tasks = Task.query.filter_by(user_id=current_user.id).all()
    events = []
    for task in tasks:
        priority_color = {'High': '#ff4b2b', 'Medium': '#ffc107', 'Low': '#28a745'}
        events.append({
            'title': task.content,
            'start': task.deadline.isoformat(),
            'allDay': True,
            'color': priority_color.get(task.priority, '#607d8b'),
            'className': 'completed-task' if task.completed else ''
        })
    return jsonify(events)

@app.route('/api/analytics_data')
@login_required
def analytics_data():
    subject_hours = {}
    sessions = StudySession.query.filter_by(user_id=current_user.id).all()
    for session in sessions:
        subject_hours[session.subject] = subject_hours.get(session.subject, 0) + session.hours_spent
    
    productivity_data = {}
    thirty_days_ago = date.today() - timedelta(days=30)
    sessions_last_30_days = StudySession.query.filter(
        StudySession.user_id == current_user.id,
        StudySession.date_completed >= thirty_days_ago
    ).order_by(StudySession.date_completed).all()
    for session in sessions_last_30_days:
        day_str = session.date_completed.strftime('%Y-%m-%d')
        productivity_data[day_str] = productivity_data.get(day_str, 0) + session.hours_spent
        
    return jsonify({
        'subject_distribution': [{'subject': k, 'hours': v} for k, v in subject_hours.items()],
        'productivity_trend': [{'date': k, 'hours': v} for k, v in productivity_data.items()]
    })

@app.route('/api/notifications')
@login_required
def api_notifications():
    today = date.today()
    overdue = Task.query.filter(Task.user_id==current_user.id, Task.completed==False, Task.deadline < today).count()
    due_today = Task.query.filter(Task.user_id==current_user.id, Task.completed==False, Task.deadline == today).count()
    notifications = []
    if overdue > 0:
        notifications.append(f"{overdue} task(s) are overdue!")
    if due_today > 0:
        notifications.append(f"You have {due_today} task(s) due today.")
    return jsonify({'count': len(notifications), 'messages': notifications})

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        user = User.query.get(current_user.id)
        user.name = request.form.get('name')
        user.user_class = request.form.get('user_class')

        # --- Start of New Avatar Logic ---
        if 'avatar_file' in request.files:
            file = request.files['avatar_file']
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                # To make filenames unique, prepend user ID
                unique_filename = f"{current_user.id}_{filename}"
                filepath = os.path.join(app.config['AVATAR_UPLOAD_FOLDER'], unique_filename)
                os.makedirs(app.config['AVATAR_UPLOAD_FOLDER'], exist_ok=True)
                file.save(filepath)
                user.avatar_filename = unique_filename
        # --- End of New Avatar Logic ---

        # ... (rest of the profile update logic for password, etc.) ...

        db.session.commit()
        flash('Profile updated successfully!', 'success')
        return redirect(url_for('profile'))

    return render_template('profile.html', name=current_user.name, user=current_user)

# --- Goal Setting ---
@app.route('/goals', methods=['GET', 'POST'])
@login_required
def goals():
    today = date.today()
    start_of_week = today - timedelta(days=today.weekday())
    end_of_week = start_of_week + timedelta(days=6)

    if request.method == 'POST':
        subject = request.form.get('subject')
        target_hours = request.form.get('target_hours')
        
        if subject and target_hours:
            new_goal = Goal(
                subject=subject,
                target_hours=float(target_hours),
                start_date=start_of_week,
                end_date=end_of_week,
                user_id=current_user.id
            )
            db.session.add(new_goal)
            db.session.commit()
            flash('New goal added for the week!', 'success')
            return redirect(url_for('goals'))

    # Fetch goals and calculate progress
    current_goals = Goal.query.filter_by(user_id=current_user.id, start_date=start_of_week).all()
    goals_with_progress = []
    for goal in current_goals:
        sessions = StudySession.query.filter(
            StudySession.user_id == current_user.id,
            StudySession.subject == goal.subject,
            StudySession.date_completed >= start_of_week,
            StudySession.date_completed <= end_of_week
        ).all()
        hours_done = sum(s.hours_spent for s in sessions)
        progress_percent = (hours_done / goal.target_hours) * 100 if goal.target_hours > 0 else 0
        goals_with_progress.append({
            'goal': goal,
            'hours_done': round(hours_done, 1),
            'progress_percent': round(progress_percent)
        })

    return render_template('goals.html', name=current_user.name, goals_data=goals_with_progress)

@app.route('/goals/delete/<int:goal_id>')
@login_required
def delete_goal(goal_id):
    goal = Goal.query.filter_by(id=goal_id, user_id=current_user.id).first_or_404()
    db.session.delete(goal)
    db.session.commit()
    flash('Goal removed.', 'success')
    return redirect(url_for('goals'))

# --- Pomodoro Focus Session ---
@app.route('/focus_session/<int:task_id>')
@login_required
def focus_session(task_id):
    task = Task.query.filter_by(id=task_id, user_id=current_user.id).first_or_404()
    return render_template('focus_session.html', name=current_user.name, task=task, user_settings=current_user)

@app.route('/api/log_session', methods=['POST'])
@login_required
def log_session():
    data = request.get_json()
    task_id = data.get('task_id')
    hours_spent = data.get('hours_spent')
    
    task = Task.query.get(task_id)
    if task and task.user_id == current_user.id:
        new_session = StudySession(
            hours_spent=hours_spent,
            subject=task.subject,
            user_id=current_user.id
        )
        db.session.add(new_session)
        db.session.commit()
        return jsonify({'status': 'success', 'message': 'Session logged.'}), 200
    return jsonify({'status': 'error', 'message': 'Invalid task.'}), 400

# --- Material Sharing Routes ---
@app.route('/materials', methods=['GET', 'POST'])
@login_required
def materials():
    if request.method == 'POST':
        if 'material_file' not in request.files:
            flash('No file part', 'error')
            return redirect(request.url)
        file = request.files['material_file']
        if file.filename == '':
            flash('No selected file', 'error')
            return redirect(request.url)
        if file and file.filename.endswith('.pdf'):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            # Ensure the upload folder exists
            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
            file.save(filepath)
            
            new_material = Material(
                filename=filename,
                filepath=filepath,
                subject=request.form.get('subject'),
                user_class=request.form.get('user_class'),
                description=request.form.get('description'),
                uploader_id=current_user.id
            )
            db.session.add(new_material)
            db.session.commit()

            # --- ADD THIS LINE ---
            process_and_store_embeddings(new_material.id, filepath)

            flash('Material uploaded successfully! It will be visible after admin approval.', 'success')
            return redirect(url_for('materials'))
        else:
            flash('Only PDF files are allowed.', 'error')

    # Handle GET request
    query = request.args.get('q', '')
    user_class = request.args.get('class', '')
    
    base_query = Material.query.filter_by(is_approved=True)
    if query:
        base_query = base_query.filter(or_(Material.subject.ilike(f'%{query}%'), Material.description.ilike(f'%{query}%')))
    if user_class:
        base_query = base_query.filter_by(user_class=user_class)
        
    all_materials = base_query.order_by(Material.upload_date.desc()).all()
    
    return render_template('materials.html', name=current_user.name, materials=all_materials, search_query=query, selected_class=user_class)

@app.route('/materials/save/<int:material_id>')
@login_required
def save_material(material_id):
    material = Material.query.get_or_404(material_id)
    if material not in current_user.saved_materials:
        current_user.saved_materials.append(material)
        db.session.commit()
        flash(f'"{material.filename}" saved!', 'success')
    return redirect(url_for('materials'))

@app.route('/materials/unsave/<int:material_id>')
@login_required
def unsave_material(material_id):
    material = Material.query.get_or_404(material_id)
    if material in current_user.saved_materials:
        current_user.saved_materials.remove(material)
        db.session.commit()
        flash(f'"{material.filename}" unsaved.', 'success')
    return redirect(url_for('saved_materials'))

@app.route('/saved_materials')
@login_required
def saved_materials():
    return render_template('saved_materials.html', name=current_user.name, materials=current_user.saved_materials)

# --- Admin Routes ---
@app.route('/admin')
@login_required
@admin_required
def admin_dashboard():
    pending_materials = Material.query.filter_by(is_approved=False).order_by(Material.upload_date.desc()).all()
    return render_template('admin_materials.html', name=current_user.name, materials=pending_materials)

@app.route('/admin/approve/<int:material_id>')
@login_required
@admin_required
def approve_material(material_id):
    material = Material.query.get_or_404(material_id)
    material.is_approved = True
    db.session.commit()
    flash('Material approved.', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete/<int:material_id>')
@login_required
@admin_required
def delete_material(material_id):
    material = Material.query.get_or_404(material_id)
    # Delete the actual file
    try:
        os.remove(material.filepath)
    except OSError as e:
        flash(f'Error deleting file: {e}', 'error')
    
    db.session.delete(material)
    db.session.commit()
    flash('Material deleted.', 'success')
    return redirect(url_for('admin_dashboard'))

# --- AI Chatbot Route ---
@app.route('/api/chat', methods=['POST'])
@login_required
def chat():
    try:
        data = request.get_json()
        user_message = data.get("message")
        use_docs = data.get("use_docs", False)
        
        if not user_message:
            return jsonify({"error": "No message provided"}), 400

        model = genai.GenerativeModel('gemini-1.5-flash')
        context = ""

        if use_docs:
            relevant_chunks = []
            user_question_embedding = embedding_model.encode([user_message])

            for material in current_user.saved_materials:
                vector_store_path = os.path.join(app.config['UPLOAD_FOLDER'], f'vs_{material.id}')
                index_path = os.path.join(vector_store_path, 'index.faiss')
                
                if os.path.exists(index_path):
                    index = faiss.read_index(index_path)
                    with open(os.path.join(vector_store_path, 'chunks.pkl'), 'rb') as f:
                        chunks = pickle.load(f)
                    
                    distances, indices = index.search(np.array(user_question_embedding).astype('float32'), 5) # Find 5 chunks
                    for i in indices[0]:
                        if i >= 0 and i < len(chunks):
                            relevant_chunks.append(chunks[i])
            
            if relevant_chunks:
                context = "\n\n---\n\n".join(relevant_chunks)

        # --- THIS IS THE NEW, IMPROVED PROMPT ---
        if context:
            prompt = f"""
            You are "Flow", an expert AI study assistant. Your user has provided you with context from their study documents.
            Your task is to answer their question or fulfill their request based on this context.
            You can perform tasks like summarizing, explaining, or creating quizzes based on the provided text.

            CONTEXT FROM DOCUMENTS:
            "{context}"

            USER'S REQUEST:
            "{user_message}"
            """
        else:
            prompt = f"""
            You are "Flow", a friendly and encouraging AI study assistant for the StudyFlow Architect app.
            Your goal is to help students understand concepts without just giving away answers.
            Keep your responses concise, helpful, and focused on academic topics.
            
            The user's question is: "{user_message}"
            """
        
        response = model.generate_content(prompt)
        return jsonify({"reply": response.text})

    except Exception as e:
        print(f"!!!!!!!! ERROR in chat route: {e}")
        return jsonify({"error": "An error occurred while processing your request."}), 500

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    if request.method == 'POST':
        # --- Save Pomodoro Settings ---
        current_user.pomodoro_work_minutes = int(request.form.get('work_minutes'))
        current_user.pomodoro_short_break = int(request.form.get('short_break'))
        current_user.pomodoro_long_break = int(request.form.get('long_break'))
        
        # --- Save Weekly Availability ---
        # A simple strategy: delete all old blocks and create new ones
        AvailabilityBlock.query.filter_by(user_id=current_user.id).delete()
        
        days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        for i, day_name in enumerate(days):
            # Check if the checkbox for the day is ticked
            if f'is_active_{day_name}' in request.form:
                start_time_str = request.form.get(f'start_time_{day_name}')
                end_time_str = request.form.get(f'end_time_{day_name}')
                
                if start_time_str and end_time_str:
                    new_block = AvailabilityBlock(
                        day_of_week=i, # Monday=0, Tuesday=1, etc.
                        start_time=datetime.strptime(start_time_str, '%H:%M').time(),
                        end_time=datetime.strptime(end_time_str, '%H:%M').time(),
                        user_id=current_user.id
                    )
                    db.session.add(new_block)

        db.session.commit()
        flash('Settings saved successfully!', 'success')
        return redirect(url_for('settings'))

    # --- Fetch existing data for GET request ---
    # Fetch availability and format it for the template
    availability_data = {i: {"active": False, "start": "09:00", "end": "17:00"} for i in range(7)}
    user_blocks = AvailabilityBlock.query.filter_by(user_id=current_user.id).all()
    for block in user_blocks:
        availability_data[block.day_of_week] = {
            "active": True,
            "start": block.start_time.strftime('%H:%M'),
            "end": block.end_time.strftime('%H:%M')
        }
        
    return render_template('settings.html', name=current_user.name, availability=availability_data)

# ADD THIS NEW API ROUTE
@app.route('/api/session/progress/update', methods=['POST'])
@login_required
def update_session_progress():
    data = request.get_json()
    task_id = data.get('task_id')
    steps = data.get('completed_steps')

    progress = SessionProgress.query.filter_by(task_id=task_id, user_id=current_user.id).first()
    if progress:
        progress.completed_steps = steps
    else:
        progress = SessionProgress(task_id=task_id, user_id=current_user.id, completed_steps=steps)
        db.session.add(progress)
    
    db.session.commit()
    return jsonify({'status': 'success'})

# REPLACE THE OLD /guided_session ROUTE WITH THIS
@app.route('/guided_session/<int:task_id>')
@login_required
def guided_session(task_id):
    task = Task.query.filter_by(id=task_id, user_id=current_user.id).first_or_404()
    
    # Generate the Study Plan in Cycles
    study_cycles = []
    total_minutes_remaining = task.estimated_hours * 60
    work_duration = current_user.pomodoro_work_minutes
    short_break_duration = current_user.pomodoro_short_break
    long_break_duration = current_user.pomodoro_long_break
    session_count = 0
    while total_minutes_remaining > 0:
        session_count += 1
        current_work = min(total_minutes_remaining, work_duration)
        total_minutes_remaining -= current_work
        current_break = 0
        break_type = ""
        if total_minutes_remaining > 0:
            if session_count % 4 == 0:
                current_break = long_break_duration
                break_type = "Long Break"
            else:
                current_break = short_break_duration
                break_type = "Short Break"
        study_cycles.append({'work': current_work, 'break': current_break, 'break_type': break_type})

    # Fetch saved progress
    progress = SessionProgress.query.filter_by(task_id=task_id, user_id=current_user.id).first()
    completed_steps = progress.completed_steps if progress else 0

    return render_template('guided_session.html', name=current_user.name, task=task, cycles=study_cycles, completed_steps=completed_steps)

# --- App Initialization ---
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)