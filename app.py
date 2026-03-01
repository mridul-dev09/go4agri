from flask import Flask, render_template, request, redirect, url_for, flash, session, send_from_directory
import os
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash, generate_password_hash
from db_config import get_db_connection
import pandas as pd
import io
from translations import TRANSLATIONS
from markupsafe import Markup
import re

app = Flask(__name__)
app.secret_key = 'go4agri_secret_key_2026'

# Document Upload Configuration
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

@app.context_processor
def inject_translations():
    lang = session.get('lang', 'en')
    def get_translation(key):
        return TRANSLATIONS.get(lang, TRANSLATIONS['en']).get(key, key)
    return dict(_t=get_translation, current_lang=lang)

@app.route('/set-language/<lang>')
def set_language(lang):
    if lang in TRANSLATIONS:
        session['lang'] = lang
    return redirect(request.referrer or url_for('home'))

@app.route("/health")
def health():
    return "ok", 200

@app.template_filter('nl2br')
def nl2br_filter(s):
    if not s:
        return ""
    result = re.sub(r'\r\n|\r|\n', '<br>', s)
    return Markup(result)

def log_activity(user_id, action, details):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO activity_log (user_id, action, details) VALUES (%s, %s, %s)",
            (user_id, action, details)
        )
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Logging error: {e}")


# Navigation routes
@app.route('/')
def home():
    return render_template('home.html')

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/services')
def services():
    return render_template('services.html')

@app.route('/pricing')
def pricing():
    return render_template('pricing.html')

@app.route('/downloads')
def downloads():
    return render_template('downloads.html')

@app.route('/clients')
def clients():
    return render_template('clients.html')

@app.route('/updates')
def updates():
    return render_template('updates.html')

@app.route('/appeal')
def appeal():
    return render_template('appeal.html')

@app.route('/complaints')
def complaints():
    return render_template('complaints.html')

@app.route('/careers')
def careers():
    return render_template('careers.html')

@app.route('/contact')
def contact():
    return render_template('contact.html')

@app.route('/certification-schemes')
def certification_schemes():
    return render_template('certification_schemes.html')

@app.route('/certification-process')
def certification_process():
    return redirect('/#certification-process')

@app.route('/apply')
def apply():
    return render_template('apply.html')

@app.route('/employee-login')
def employee_login():
    return render_template('employee_login.html')

@app.route('/client-login')
def client_login():
    return render_template('client_login.html')

@app.route('/login', methods=['POST'])
def login():
    email = request.form.get('email')
    password = request.form.get('password')
    login_type = request.form.get('login_type', 'employee')
    redirect_page = 'client_login' if login_type == 'client' else 'employee_login'
    
    if not email or not password:
        flash('Please provide both email and password.', 'error')
        return redirect(url_for(redirect_page))
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['email'] = user['email']
            session['designation'] = user['designation']
            session['full_name'] = user['full_name']
            
            log_activity(user['id'], 'LOGIN', f"User logged in as {user['designation']}")
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password.', 'error')
            return redirect(url_for(redirect_page))
            
    except Exception as e:
        print(f"Login error: {e}")
        flash('An internal error occurred. Please try again later.', 'error')
        return redirect(url_for(redirect_page))

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('home'))
    
    designation = session.get('designation')
    
    # Mapping designations to template filenames
    template_map = {
        'Initial reviewer': 'db_initial_reviewer.html',
        'Admin': 'db_admin.html',
        'Scheduler': 'db_scheduler.html',
        'Evaluator': 'db_evaluator.html',
        'Technical reviewer': 'db_technical_reviewer.html',
        'Certification officer': 'db_certification_officer.html',
        'CEO': 'db_ceo.html',
        'QA': 'db_qa.html',
        'Certifier': 'db_certifier.html',
        'Auditor': 'db_auditor.html',
        'Client': 'db_client.html'
    }
    print(f"DEBUG: Dashboard requested for {designation}")
    template = template_map.get(designation, 'db_base.html')
    print(f"DEBUG: Using template {template}")
    
    enquiries = []
    apps = []
    activities = []
    tasks = []
    employees = []
    documents = []
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        if designation == 'CEO':
            cursor.execute("SELECT * FROM applications ORDER BY created_at DESC")
            apps = cursor.fetchall()
            cursor.execute("SELECT * FROM enquiries ORDER BY created_at DESC")
            enquiries = cursor.fetchall()
            cursor.execute("""
                SELECT al.*, u.full_name, u.designation 
                FROM activity_log al 
                LEFT JOIN users u ON al.user_id = u.id 
                ORDER BY al.created_at DESC LIMIT 50
            """)
            activities = cursor.fetchall()
            cursor.execute("""
                SELECT t.*, allotter.full_name as allotter_name, assignee.full_name as assignee_name 
                FROM tasks t
                JOIN users allotter ON t.allotter_id = allotter.id
                JOIN users assignee ON t.assignee_id = assignee.id
                ORDER BY t.created_at DESC
            """)
            tasks = cursor.fetchall()
            cursor.execute("SELECT id, full_name, designation FROM users WHERE designation != 'Client' AND designation != 'CEO'")
            employees = cursor.fetchall()
        elif designation == 'Client':
            cursor.execute("SELECT * FROM applications WHERE client_id = %s ORDER BY created_at DESC", (session['user_id'],))
            apps = cursor.fetchall()
        else:
            # For other employees, show tasks assigned to them
            cursor.execute("""
                SELECT t.*, allotter.full_name as allotter_name 
                FROM tasks t
                JOIN users allotter ON t.allotter_id = allotter.id
                WHERE t.assignee_id = %s
                ORDER BY t.created_at DESC
            """, (session['user_id'],))
            tasks = cursor.fetchall()
            
            # Fetch relevant applications based on role logic
            if designation == 'Admin':
                cursor.execute("SELECT * FROM applications WHERE status = 'PENDING_ADMIN_REVIEW' ORDER BY created_at DESC")
            elif designation == 'QA':
                cursor.execute("SELECT * FROM applications WHERE status = 'PENDING_QA_REVIEW' ORDER BY created_at DESC")
            elif designation == 'Initial reviewer':
                cursor.execute("SELECT * FROM applications WHERE status = 'PENDING_INITIAL_REVIEW' ORDER BY created_at DESC")
            elif designation == 'Evaluator':
                cursor.execute("SELECT * FROM applications WHERE status IN ('PENDING_EVALUATION', 'PENDING_NC_FOLLOWUP') ORDER BY created_at DESC")
            elif designation == 'Technical reviewer':
                cursor.execute("SELECT * FROM applications WHERE status = 'PENDING_TECHNICAL_REVIEW' ORDER BY created_at DESC")
            elif designation == 'Certification officer':
                cursor.execute("SELECT * FROM applications WHERE status = 'PENDING_CERTIFICATION_OFFICER' ORDER BY created_at DESC")
            elif designation == 'Certifier':
                cursor.execute("SELECT * FROM applications WHERE status = 'PENDING_CERTIFIER_APPROVAL' ORDER BY created_at DESC")
            else:
                cursor.execute("SELECT * FROM applications ORDER BY created_at DESC LIMIT 5")
            apps = cursor.fetchall()

        # Fetch Documents based on role
        if designation in ['CEO', 'Admin', 'QA']:
            cursor.execute("""
                SELECT d.*, u.full_name as client_name 
                FROM documents d 
                JOIN users u ON d.client_id = u.id 
                ORDER BY d.uploaded_at DESC
            """)
            documents = cursor.fetchall()
        elif designation == 'Client':
            cursor.execute("SELECT * FROM documents WHERE client_id = %s ORDER BY uploaded_at DESC", (session['user_id'],))
            documents = cursor.fetchall()
        elif designation in ['Initial reviewer', 'Evaluator', 'Technical reviewer', 'Certification officer', 'Certifier']:
            # Maybe they should also see documents related to their assigned tasks? 
            # For now, let's allow them to see relevant documents if needed, or just specific ones.
            # User said: "uploaded documents should be seen on CEO, Quality and ADmin dashborad"
            pass
            
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"DEBUG: Error fetching dashboard data: {e}")
        
    return render_template(template, user=session, applications=apps, enquiries=enquiries, activities=activities, tasks=tasks, employees=employees, documents=documents)

@app.route('/submit-application', methods=['POST'])
def submit_application():
    if 'user_id' not in session or session.get('designation') != 'Client':
        flash('Unauthorized.', 'error')
        return redirect(url_for('home'))
        
    company_name = request.form.get('company_name')
    program_type = request.form.get('program_type')
    
    if not company_name or not program_type:
        flash('Please fill all fields.', 'error')
        return redirect(url_for('apply'))
        
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO applications (client_id, company_name, program_type, status) VALUES (%s, %s, %s, 'PENDING_CEO_REVIEW')",
            (session['user_id'], company_name, program_type)
        )
        conn.commit()
        cursor.close()
        conn.close()
        log_activity(session['user_id'], 'SUBMIT_APPLICATION', f"Submitted application for {company_name}")
        flash('Application submitted successfully!', 'success')
        return redirect(url_for('dashboard'))
    except Exception as e:
        print(f"Error submitting app: {e}")
        flash('Error submitting application.', 'error')
        return redirect(url_for('apply'))

@app.route('/submit-enquiry', methods=['POST'])
def submit_enquiry():
    name = request.form.get('name')
    email = request.form.get('email')
    phone = request.form.get('phone')
    program_type = request.form.get('program_type')
    message = request.form.get('message')
    
    if not name or not email or not phone or not program_type:
        flash('Please fill all required fields.', 'error')
        return redirect(url_for('certification_schemes'))
        
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO enquiries (name, email, phone, program_type, message) VALUES (%s, %s, %s, %s, %s)",
            (name, email, phone, program_type, message)
        )
        conn.commit()
        cursor.close()
        conn.close()
        flash('Thank you for your enquiry! Our team will contact you soon.', 'success')
        log_activity(None, 'ENQUIRY', f"New enquiry from {name} for {program_type}")
    except Exception as e:
        print(f"Error submitting enquiry: {e}")
        flash('An error occurred. Please try again later.', 'error')
        
    return redirect(url_for('certification_schemes'))

@app.route('/update-application-status/<int:app_id>', methods=['POST'])
def update_application_status(app_id):
    if 'user_id' not in session:
        return redirect(url_for('employee_login'))
        
    role = session.get('designation')
    
    # Define status flow matching 7 steps
    flow = {
        'CEO': 'PENDING_ADMIN_REVIEW',
        'Admin': 'PENDING_QA_REVIEW',
        'QA': 'PENDING_INITIAL_REVIEW',
        'Initial reviewer': 'PENDING_CONTRACT',
        # For middle steps without specific new roles, we allow Admin/CEO to move them or reuse roles
        'Contract Manager': 'PENDING_EVALUATION', 
        'Evaluator': 'PENDING_NC_FOLLOWUP',
        'NC Specialist': 'PENDING_TECHNICAL_REVIEW',
        'Technical reviewer': 'PENDING_CERTIFICATION_OFFICER',
        'Certification officer': 'PENDING_CERTIFIER_APPROVAL',
        'Certifier': 'PENDING_TRANSACTION',
    }
    
    # Adding flexibility if specific roles for new steps don't exist yet
    if role == 'Admin' and request.form.get('current_status') == 'PENDING_CONTRACT':
        new_status = 'PENDING_EVALUATION'
    elif role == 'Evaluator' and request.form.get('current_status') == 'PENDING_NC_FOLLOWUP':
        new_status = 'PENDING_TECHNICAL_REVIEW'
    else:
        new_status = flow.get(role)
    
    # Handle direct transition to CERTIFICATE_ISSUED from TRANSACTION stage
    # This might be handled by another role or a separate route, but for simplicity:
    if role == 'Certifier' and request.form.get('action') == 'issue':
        new_status = 'CERTIFICATE_ISSUED'
    else:
        new_status = flow.get(role)

    # If it's the transaction stage, we might need a separate action
    if request.form.get('status_override'):
        new_status = request.form.get('status_override')
    if not new_status:
        flash('You are not authorized to advance applications.', 'error')
        return redirect(url_for('dashboard'))
        
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE applications SET status = %s WHERE id = %s",
            (new_status, app_id)
        )
        conn.commit()
        cursor.close()
        conn.close()
        log_activity(session['user_id'], 'UPDATE_STATUS', f"Advanced application {app_id} to {new_status}")
        flash(f'Application advanced to {new_status.replace("_", " ")}.', 'success')
    except Exception as e:
        print(f"Error updating status: {e}")
        flash('Error updating application status.', 'error')
        
    return redirect(url_for('dashboard'))

@app.route('/register-client', methods=['POST'])
def register_client():
    if 'user_id' not in session or session.get('designation') != 'CEO':
        flash('Unauthorized access.', 'error')
        return redirect(url_for('home'))
        
    full_name = request.form.get('full_name')
    email = request.form.get('email')
    password = request.form.get('password', 'client123') 
    enquiry_id = request.form.get('enquiry_id')
    
    if not full_name or not email:
        flash('Please provide both name and email.', 'error')
        return redirect(url_for('dashboard'))
        
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        hashed_pw = generate_password_hash(password)
        
        cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
        if cursor.fetchone() is None:
            cursor.execute(
                "INSERT INTO users (full_name, email, designation, password) VALUES (%s, %s, %s, %s)",
                (full_name, email, 'Client', hashed_pw)
            )
            
            if enquiry_id:
                cursor.execute("UPDATE enquiries SET status = 'REGISTERED' WHERE id = %s", (enquiry_id,))
                
            conn.commit()
            log_activity(session['user_id'], 'REGISTER_CLIENT', f"Registered client {full_name} ({email})")
            flash(f'Successfully registered client {full_name}.', 'success')
        else:
            flash(f'User with email {email} already exists.', 'error')
            
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Registration error: {e}")
        flash(f'Error registering client: {str(e)}', 'error')
        
    return redirect(url_for('dashboard'))

@app.route('/logout')
def logout():
    log_activity(session.get('user_id'), 'LOGOUT', "User logged out")
    session.clear()
    return redirect(url_for('home'))

@app.route('/allot-task', methods=['POST'])
def allot_task():
    if 'user_id' not in session or session.get('designation') != 'CEO':
        flash('Unauthorized.', 'error')
        return redirect(url_for('home'))
        
    assignee_id = request.form.get('assignee_id')
    application_id = request.form.get('application_id') or None
    title = request.form.get('title')
    description = request.form.get('description')
    priority = request.form.get('priority', 'MEDIUM')
    
    if not assignee_id or not title:
        flash('Please fill required fields.', 'error')
        return redirect(url_for('dashboard'))
        
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO tasks (allotter_id, assignee_id, application_id, title, description, priority) VALUES (%s, %s, %s, %s, %s, %s)",
            (session['user_id'], assignee_id, application_id, title, description, priority)
        )
        conn.commit()
        cursor.close()
        conn.close()
        log_activity(session['user_id'], 'ALLOT_TASK', f"Allotted task '{title}' to user {assignee_id}")
        flash('Task allotted successfully!', 'success')
    except Exception as e:
        print(f"Error allotting task: {e}")
        flash('Error allotting task.', 'error')
        
    return redirect(url_for('dashboard'))

@app.route('/update-task-status/<int:task_id>', methods=['POST'])
def update_task_status(task_id):
    if 'user_id' not in session:
        return redirect(url_for('home'))
        
    new_status = request.form.get('status')
    if new_status not in ['PENDING', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED']:
        flash('Invalid status.', 'error')
        return redirect(url_for('dashboard'))
        
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE tasks SET status = %s WHERE id = %s", (new_status, task_id))
        conn.commit()
        cursor.close()
        conn.close()
        log_activity(session['user_id'], 'TASK_STATUS_UPDATE', f"Updated task {task_id} status to {new_status}")
        flash('Task status updated.', 'success')
    except Exception as e:
        print(f"Error updating task: {e}")
        flash('Error updating task status.', 'error')
        
    return redirect(url_for('dashboard'))

@app.route('/admin/upload-employees', methods=['POST'])
def upload_employees():
    if 'user_id' not in session or session.get('designation') != 'Admin':
        flash('Unauthorized access.', 'error')
        return redirect(url_for('employee_login'))
    
    file = request.files.get('employee_file')
    if not file or file.filename == '':
        flash('No file selected.', 'error')
        return redirect(url_for('dashboard'))
    
    if not file.filename.endswith(('.xlsx', '.xls')):
        flash('Please upload a valid Excel file.', 'error')
        return redirect(url_for('dashboard'))
    
    try:
        # Read Excel using pandas
        df = pd.read_excel(file)
        
        # Expected columns: full_name, email, designation, password
        required_cols = ['full_name', 'email', 'designation', 'password']
        if not all(col in df.columns for col in required_cols):
            flash(f'Excel must contain columns: {", ".join(required_cols)}', 'error')
            return redirect(url_for('dashboard'))
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        success_count = 0
        skip_count = 0
        
        for _, row in df.iterrows():
            full_name = str(row['full_name'])
            email = str(row['email'])
            designation = str(row['designation'])
            password = str(row['password'])
            
            # Hash password
            hashed_pw = generate_password_hash(password)
            
            # check if user exists
            cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
            if cursor.fetchone() is None:
                cursor.execute(
                    "INSERT INTO users (full_name, email, designation, password) VALUES (%s, %s, %s, %s)",
                    (full_name, email, designation, hashed_pw)
                )
                success_count += 1
            else:
                skip_count += 1
        
        conn.commit()
        cursor.close()
        conn.close()
        
        flash(f'Successfully uploaded {success_count} employees. {skip_count} skipped (already exist).', 'success')
        
    except Exception as e:
        print(f"Upload error: {e}")
        flash(f'Error processing file: {str(e)}', 'error')
        
    return redirect(url_for('dashboard'))

@app.route('/messages')
def messages():
    if 'user_id' not in session:
        return redirect(url_for('home'))
        
    user_id = session['user_id']
    msg_id = request.args.get('id')
    
    msgs = []
    selected_msg = None
    contacts = []
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Fetch inbox
        cursor.execute("""
            SELECT m.*, u.full_name as sender_name 
            FROM messages m
            JOIN users u ON m.sender_id = u.id
            WHERE m.receiver_id = %s
            ORDER BY m.created_at DESC
        """, (user_id,))
        msgs = cursor.fetchall()
        
        # Fetch selected message
        if msg_id:
            cursor.execute("""
                SELECT m.*, sender.full_name as sender_name, receiver.full_name as receiver_name
                FROM messages m
                JOIN users sender ON m.sender_id = sender.id
                JOIN users receiver ON m.receiver_id = receiver.id
                WHERE m.id = %s AND (m.receiver_id = %s OR m.sender_id = %s)
            """, (msg_id, user_id, user_id))
            selected_msg = cursor.fetchone()
            
            if selected_msg and selected_msg['receiver_id'] == user_id and not selected_msg['is_read']:
                cursor.execute("UPDATE messages SET is_read = TRUE WHERE id = %s", (msg_id,))
                conn.commit()
                
        # Fetch contacts (all employees, and clients if CEO/Admin)
        if session['designation'] in ['CEO', 'Admin']:
            cursor.execute("SELECT id, full_name, designation FROM users WHERE id != %s", (user_id,))
        else:
            cursor.execute("SELECT id, full_name, designation FROM users WHERE designation != 'Client' AND id != %s", (user_id,))
        contacts = cursor.fetchall()
        
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Error fetching messages: {e}")
        
    return render_template('db_messages.html', user=session, messages=msgs, selected_message=selected_msg, contacts=contacts)

@app.route('/send-message', methods=['POST'])
def send_message():
    if 'user_id' not in session:
        return redirect(url_for('home'))
        
    receiver_id = request.form.get('receiver_id')
    subject = request.form.get('subject')
    body = request.form.get('body')
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO messages (sender_id, receiver_id, subject, body) VALUES (%s, %s, %s, %s)",
            (session['user_id'], receiver_id, subject, body)
        )
        conn.commit()
        cursor.close()
        conn.close()
        flash('Message sent successfully!', 'success')
    except Exception as e:
        print(f"Error sending message: {e}")
        flash('Error sending message.', 'error')
        
    return redirect(url_for('messages'))

@app.route('/settings')
def settings():
    if 'user_id' not in session:
        return redirect(url_for('home'))
    return render_template('db_settings.html', user=session)

@app.route('/update-settings', methods=['POST'])
def update_settings():
    if 'user_id' not in session:
        return redirect(url_for('home'))
        
    full_name = request.form.get('full_name')
    new_password = request.form.get('new_password')
    confirm_password = request.form.get('confirm_password')
    
    if new_password and new_password != confirm_password:
        flash('Passwords do not match.', 'error')
        return redirect(url_for('settings'))
        
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if new_password:
            hashed_pw = generate_password_hash(new_password)
            cursor.execute("UPDATE users SET full_name = %s, password = %s WHERE id = %s", (full_name, hashed_pw, session['user_id']))
        else:
            cursor.execute("UPDATE users SET full_name = %s WHERE id = %s", (full_name, session['user_id']))
            
        conn.commit()
        cursor.close()
        conn.close()
        
        session['full_name'] = full_name
        log_activity(session['user_id'], 'UPDATE_SETTINGS', "Updated profile/password")
        flash('Settings updated successfully!', 'success')
    except Exception as e:
        print(f"Error updating settings: {e}")
        flash('Error updating settings.', 'error')
        
    return redirect(url_for('settings'))
@app.route('/upload-document', methods=['GET', 'POST'])
def upload_document():
    if 'user_id' not in session or session.get('designation') != 'Client':
        flash('Unauthorized.', 'error')
        return redirect(url_for('home'))
        
    if request.method == 'GET':
        # Fetch applications so the user can link the document
        apps = []
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM applications WHERE client_id = %s", (session['user_id'],))
            apps = cursor.fetchall()
            cursor.close()
            conn.close()
        except Exception as e:
            print(f"Error fetching apps: {e}")
        return render_template('upload-document.html', user=session, applications=apps)

    category = request.form.get('category')
    app_id = request.form.get('application_id') or None
    file = request.files.get('document_file')
    
    if not file or file.filename == '':
        flash('No file selected for upload.', 'error')
        return redirect(url_for('upload_document'))
        
    try:
        filename = secure_filename(file.filename)
        # Add timestamp to filename to prevent overwrites
        from datetime import datetime
        ts_filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
        
        # Ensure upload folder exists (safety check)
        if not os.path.exists(app.config['UPLOAD_FOLDER']):
            os.makedirs(app.config['UPLOAD_FOLDER'])
            
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], ts_filename)
        file.save(filepath)
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO documents (client_id, application_id, category, filename, filepath) VALUES (%s, %s, %s, %s, %s)",
            (session['user_id'], app_id, category, filename, ts_filename)
        )
        conn.commit()
        cursor.close()
        conn.close()
        
        log_activity(session['user_id'], 'UPLOAD_DOC', f"Uploaded {category}: {filename}")
        flash('Document uploaded successfully!', 'success')
        return redirect(url_for('dashboard'))
    except Exception as e:
        print(f"CRITICAL: Upload error in app.py: {e}")
        import traceback
        traceback.print_exc()
        flash(f'Error saving document: {str(e)}', 'error')
        return redirect(url_for('upload_document'))

@app.route('/client-details/<int:client_id>')
def client_details(client_id):
    if 'user_id' not in session or session.get('designation') not in ['CEO', 'Admin', 'QA']:
        flash('Unauthorized access.', 'error')
        return redirect(url_for('dashboard'))
        
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Get client details
        cursor.execute("SELECT * FROM users WHERE id = %s AND designation = 'Client'", (client_id,))
        client_user = cursor.fetchone()
        
        if not client_user:
            flash('Client not found.', 'error')
            return redirect(url_for('dashboard'))
            
        # Get client applications
        cursor.execute("SELECT * FROM applications WHERE client_id = %s ORDER BY created_at DESC", (client_id,))
        apps = cursor.fetchall()
        
        # Get client documents
        cursor.execute("SELECT * FROM documents WHERE client_id = %s ORDER BY uploaded_at DESC", (client_id,))
        docs = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return render_template('db_client_details.html', user=session, client=client_user, applications=apps, documents=docs)
    except Exception as e:
        print(f"Error fetching client details: {e}")
        flash('Error loading client details.', 'error')
        return redirect(url_for('dashboard'))

@app.route('/download-document/<int:doc_id>')
def download_document(doc_id):
    if 'user_id' not in session:
        return redirect(url_for('home'))
        
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM documents WHERE id = %s", (doc_id,))
        doc = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if not doc:
            flash('Document not found.', 'error')
            return redirect(url_for('dashboard'))
            
        # Check permissions: Client can only download their own, others (CEO/Admin/QA) can download any
        if session['designation'] == 'Client' and doc['client_id'] != session['user_id']:
            flash('Unauthorized access.', 'error')
            return redirect(url_for('dashboard'))
            
        return send_from_directory(app.config['UPLOAD_FOLDER'], doc['filepath'], as_attachment=True, download_name=doc['filename'])
    except Exception as e:
        print(f"Download error: {e}")
        flash('Error downloading document.', 'error')
        return redirect(url_for('dashboard'))

if __name__ == '__main__':
    app.run(debug=True)
