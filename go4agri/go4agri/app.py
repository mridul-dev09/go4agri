from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory, send_file, jsonify
import os
import json
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash, generate_password_hash
from db_config import get_db_connection
import pandas as pd
import io
from translations import TRANSLATIONS
from markupsafe import Markup
import re
from flask_mail import Mail, Message
from datetime import datetime, timedelta
import zipfile
from threading import Thread
from itsdangerous import URLSafeTimedSerializer

app = Flask(__name__)
app.secret_key = 'go4agri_secret_key_2026'

@app.template_filter('from_json')
def from_json_filter(s):
    if isinstance(s, dict) or isinstance(s, list):
        return s
    try:
        return json.loads(s)
    except:
        return {}


# Email Configuration
app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS', 'True') == 'True'
app.config['MAIL_USE_SSL'] = os.getenv('MAIL_USE_SSL', 'False') == 'True'
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME', 'admingo4agri@gmail.com')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD', 'demo_password')
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_USERNAME', 'admingo4agri@gmail.com')
app.config['MAIL_TIMEOUT'] = 10

mail = Mail(app)

def send_async_email(app, msg):
    with app.app_context():
        try:
            mail.send(msg)
        except Exception as e:
            print(f"Async email sending failed: {e}")

DEPARTMENT_EMAILS = {
    'Admin': 'Apply@go4agri.co.in',
    'Accounts': 'Finance@go4agri.co.in',
    'Initial reviewer': 'Review@go4agri.co.in',
    'Inspection planner': 'Review@go4agri.co.in',
    'Auditor': 'Review@go4agri.co.in',
    'Technical reviewer': 'Review@go4agri.co.in',
    'Certifier': 'Certification@go4agri.co.in',
    'CEO': 'Certification@go4agri.co.in',
    'QA': 'Quality@go4agri.co.in',
    'Quality': 'Quality@go4agri.co.in',
    'HR': 'HR@go4agri.co.in'
}

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

def generate_client_code(cursor, year):
    """Generates a sequential client code in the format G4AYYYYNNN."""
    cursor.execute("SELECT MAX(client_code) FROM users WHERE client_code LIKE %s", (f"G4A{year}%",))
    max_code_row = cursor.fetchone()
    next_num = 1
    if max_code_row and max_code_row[0]:
        try:
            last_three = max_code_row[0][-3:]
            next_num = int(last_three) + 1
        except ValueError:
            pass
    return f"G4A{year}{next_num:03d}"

def generate_project_code(cursor, client_id, client_code):
    """Generates a sequential project code in the format G4AYYYYNNN-NN."""
    cursor.execute("SELECT MAX(project_code) FROM applications WHERE client_id = %s AND project_code LIKE %s", (client_id, f"{client_code}-%"))
    max_proj_row = cursor.fetchone()
    next_proj_num = 1
    if max_proj_row and max_proj_row[0]:
        try:
            last_two = max_proj_row[0][-2:]
            next_proj_num = int(last_two) + 1
        except ValueError:
            pass
    return f"{client_code}-{next_proj_num:02d}"

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

def send_system_message(receiver_designation, subject, body):
    """Sends a system message to all users of a specific designation and department email."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        # Find all users with this designation
        cursor.execute("SELECT id FROM users WHERE designation = %s", (receiver_designation,))
        receivers = cursor.fetchall()
        
        system_user_id = 1 # Assuming user ID 1 is Admin/System
        
        for receiver in receivers:
            cursor.execute(
                "INSERT INTO messages (sender_id, receiver_id, subject, body) VALUES (%s, %s, %s, %s)",
                (system_user_id, receiver['id'], subject, body)
            )
        conn.commit()
        cursor.close()
        conn.close()
        
        # Send Email to Department
        dept_email = DEPARTMENT_EMAILS.get(receiver_designation)
        if dept_email:
            msg = Message(subject, recipients=[dept_email])
            msg.body = body
            Thread(target=send_async_email, args=(app, msg)).start()
            
    except Exception as e:
        print(f"System Message Error: {e}")


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
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT a.*, u.full_name as client_name 
        FROM applications a 
        JOIN users u ON a.client_id = u.id 
        WHERE a.status = 'CERTIFICATE_ISSUED' 
        ORDER BY a.updated_at DESC
    """)
    certified = cursor.fetchall()
    conn.close()
    from datetime import timedelta
    return render_template('clients.html', certified=certified, timedelta=timedelta)

@app.route('/updates')
def updates():
    return render_template('updates.html')

@app.route('/appeal')
def appeal():
    return render_template('appeal.html')

@app.route('/submit-appeal', methods=['POST'])
def submit_appeal():
    try:
        first_name = request.form.get('first_name')
        last_name = request.form.get('last_name')
        email = request.form.get('email')
        phone = request.form.get('phone')
        product_name = request.form.get('product_name')
        manufacturer_name = request.form.get('manufacturer_name')
        uncertified_claims = request.form.get('uncertified_claims')
        sources = request.form.getlist('source')
        details = request.form.get('details')
        contact_permission = request.form.get('contact_permission')
        
        # Handle file upload
        file = request.files.get('evidence')
        filename = None
        if file and file.filename:
            filename = secure_filename(f"appeal_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}")
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            
        # Send Email Notification
        msg = Message(
            subject=f"New Appeal/Complaint: {product_name}",
            recipients=['Quality@go4agri.co.in'],
            body=f"""
New Appeal or Complaint received:

Name: {first_name} {last_name}
Email: {email}
Phone: {phone}
Product/Subject: {product_name}
Manufacturer/Entity: {manufacturer_name}
Uncertified Claims Awareness: {uncertified_claims}
Sources of Misrepresentation: {', '.join(sources)}
Details: {details}
Contact Permission: {contact_permission}
Evidence Filename: {filename if filename else 'None'}
            """
        )
        Thread(target=send_async_email, args=(app, msg)).start()
        
        flash("Your request has been submitted successfully. Our Quality department will review it and get back to you if required.", "success")
        return redirect(url_for('appeal'))
    except Exception as e:
        print(f"Appeal submission error: {e}")
        flash("There was an error submitting your request. Please try again later.", "error")
        return redirect(url_for('appeal'))

@app.route('/complaints')
def complaints():
    return redirect(url_for('appeal'))


@app.route('/update-current-status/<int:app_id>', methods=['POST'])
def update_current_status(app_id):
    if 'user_id' not in session:
        return redirect(url_for('home'))
    designation = session.get('designation')
    if designation not in ['Admin', 'CEO', 'Quality']:
        flash('You are not authorized to perform this action.', 'error')
        return redirect(url_for('dashboard'))

    allowed_statuses = [
        'Active',
        'Suspension',
        'Cancellation (Voluntary Withdrawal)',
        'Cancellation (Change of CB)',
        'Cancellation'
    ]
    new_status = request.form.get('current_status')
    if new_status not in allowed_statuses:
        flash('Invalid status value.', 'error')
        return redirect(url_for('dashboard'))

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE applications SET current_status = %s WHERE id = %s AND status = 'CERTIFICATE_ISSUED'",
            (new_status, app_id)
        )
        conn.commit()
        cursor.close()
        conn.close()
        log_activity(session['user_id'], 'UPDATE_CURRENT_STATUS', f"Set current_status='{new_status}' for app {app_id}")
        flash(f'Certification status updated to "{new_status}" successfully.', 'success')
    except Exception as e:
        print(f"Error updating current status: {e}")
        flash('Error updating certification status.', 'error')

    return redirect(url_for('dashboard'))

@app.route('/careers')
def careers():
    return render_template('careers.html')

@app.route('/contact')
def contact():
    return render_template('contact.html')

@app.route('/certification-schemes')
def certification_schemes():
    return render_template('certification_schemes.html')

@app.route('/scheme-npop')
def scheme_npop():
    return render_template('scheme_npop.html')

@app.route('/scheme-cor')
def scheme_cor():
    return render_template('scheme_cor.html')

@app.route('/scheme-eu')
def scheme_eu():
    return render_template('scheme_eu.html')

@app.route('/scheme-nop')
def scheme_nop():
    return render_template('scheme_nop.html')

@app.route('/scheme-globalgap')
def scheme_globalgap():
    return render_template('scheme_globalgap.html')


@app.route('/certification-process')
def certification_process():
    return render_template('certification_process.html')

TRAINING_DATA = {
    'organic-standards': {
        'title': 'Organic Standards Training',
        'icon': 'fas fa-seedling',
        'gradient': 'linear-gradient(135deg, #2d5a27 0%, #4caf50 100%)',
        'sections': [
            {
                'title': 'Standards Covered',
                'points': [
                    'NPOP (India Organic Standards)',
                    'NOP (USDA Organic – 7 CFR Part 205)',
                    'EU Organic Regulation (EU) 2018/848',
                    'COR (Canada Organic Regime)'
                ]
            },
            {
                'title': 'Key Topics Covered',
                'points': [
                    'Regulatory framework and compliance requirements',
                    'Scope of certification (production, processing, trading)',
                    'Traceability and record-keeping requirements',
                    'Inspection and certification process'
                ]
            }
        ]
    },
    'globalgap': {
        'title': 'GLOBALG.A.P. Awareness Training',
        'icon': 'fas fa-globe-europe',
        'gradient': 'linear-gradient(135deg, #1f4037 0%, #99f2c8 100%)',
        'sections': [
            {
                'title': 'Main Framework',
                'points': [
                    'GLOBALG.A.P. IFA v6 (SMART / GFS)',
                    'Control Points & Compliance Criteria (CPCC)',
                    'Option 1 & Option 2 (QMS) overview'
                ]
            },
            {
                'title': 'Add-ons',
                'points': [
                    'GRASP – Social practices and worker welfare',
                    'SPRING – Sustainable water management'
                ]
            }
        ]
    },
    'food-safety': {
        'title': 'Food Safety & Quality Training',
        'icon': 'fas fa-shield-alt',
        'gradient': 'linear-gradient(135deg, #283c86 0%, #45a247 100%)',
        'sections': [
            {
                'title': 'HACCP (Codex Alimentarius)',
                'points': [
                    'Hazard identification and risk assessment',
                    'CCP determination and monitoring',
                    'Validation and verification'
                ]
            },
            {
                'title': 'BRCGS Awareness Training',
                'points': [
                    'BRCGS Food Safety Issue 9 requirements',
                    'Fundamental clauses and compliance expectations',
                    'Audit preparation and system understanding'
                ]
            },
            {
                'title': 'FSSC 22000 Awareness Training',
                'points': [
                    'ISO-based food safety management system',
                    'PRPs, OPRPs, HACCP integration',
                    'Certification structure and audit approach'
                ]
            },
            {
                'title': 'ISO 22000 Training',
                'points': [
                    'Food Safety Management System requirements',
                    'Risk-based thinking and process approach',
                    'Documentation and implementation framework'
                ]
            }
        ]
    },
    'qms': {
        'title': 'Quality & Management System Training',
        'icon': 'fas fa-award',
        'gradient': 'linear-gradient(135deg, #c4a006 0%, #e8c63f 100%)',
        'sections': [
            {
                'title': 'ISO 9001 Awareness Training',
                'points': [
                    'Quality Management Principles',
                    'Process-based approach',
                    'Risk-based thinking'
                ]
            },
            {
                'title': 'Internal Auditor Training (ISO 19011)',
                'points': [
                    'Audit principles and methodology',
                    'Planning and conducting audits',
                    'Reporting and follow-up'
                ]
            }
        ]
    },
    'gmp': {
        'title': 'GMP (Good Manufacturing Practices)',
        'icon': 'fas fa-pump-soap',
        'gradient': 'linear-gradient(135deg, #009fff 0%, #ec2F4B 100%)',
        'sections': [
            {
                'title': 'Key Topics Covered',
                'points': [
                    'Hygiene and sanitation practices',
                    'Personnel hygiene requirements',
                    'Facility and operational controls'
                ]
            }
        ]
    }
}

@app.route('/training')
def training():
    return render_template('training.html', training_data=TRAINING_DATA)

@app.route('/training/<area_id>')
def training_detail(area_id):
    if area_id not in TRAINING_DATA:
        flash('Training area not found.', 'error')
        return redirect(url_for('training'))
    
    training_info = TRAINING_DATA[area_id]
    return render_template('training_detail.html', area_id=area_id, training=training_info)

@app.route('/enquire-training')
def enquire_training():
    selected_type = request.args.get('type', '')
    return render_template('enquire_training.html', selected_type=selected_type)

@app.route('/submit-training-enquiry', methods=['POST'])
def submit_training_enquiry():
    name = request.form.get('name')
    email = request.form.get('email')
    phone = request.form.get('phone')
    training_type = request.form.get('training_type')
    message = request.form.get('message')
    
    if not all([name, email, phone, training_type]):
        flash('Please fill in all required fields.', 'error')
        return redirect(url_for('enquire_training'))

    try:
        connection = get_db_connection()
        with connection.cursor() as cursor:
            sql = """
                INSERT INTO training_enquiries 
                (name, email, phone, training_type, message) 
                VALUES (%s, %s, %s, %s, %s)
            """
            cursor.execute(sql, (name, email, phone, training_type, message))
            connection.commit()
            
        flash(f'Thank you, {name}! Your enquiry for {training_type} has been submitted successfully.', 'success')
        return redirect(url_for('training'))
        
    except Exception as e:
        print(f"Error submitting training enquiry: {e}")
        flash('An error occurred. Please try again later.', 'error')
        return redirect(url_for('enquire_training'))
    finally:
        if 'connection' in locals() and connection.is_connected():
            connection.close()

@app.route('/apply')
def apply():
    return render_template('apply.html')

@app.route('/employee-login')
def employee_login():
    return render_template('employee_login.html')

@app.route('/client-login')
def client_login():
    return render_template('client_login.html')

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email')
        login_type = request.form.get('type', 'employee')
        redirect_page = 'client_login' if login_type == 'client' else 'employee_login'
        
        if not email:
            flash('Please provide your email address.', 'error')
            return redirect(url_for('forgot_password', type=login_type))
            
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
            user = cursor.fetchone()
            cursor.close()
            conn.close()
            
            if user:
                serializer = URLSafeTimedSerializer(app.secret_key)
                token = serializer.dumps(user['email'], salt='password-reset-salt')
                
                reset_link = url_for('reset_password', token=token, _external=True)
                
                msg = Message(
                    subject="Password Reset Request - Go4Agri",
                    recipients=[user['email']],
                    body=f"""Hello {user['full_name']},

You requested to reset your password for your Go4Agri account.

Please click on the link below to reset your password (this link will expire in 30 minutes):
{reset_link}

If you did not make this request, please ignore this email.

Best regards,
Go4Agri Team
"""
                )
                Thread(target=send_async_email, args=(app, msg)).start()
                
            flash('If the email is registered, a password reset link has been sent.', 'success')
            return redirect(url_for(redirect_page))
            
        except Exception as e:
            print(f"Forgot password error: {e}")
            flash('An error occurred. Please try again later.', 'error')
            return redirect(url_for('forgot_password', type=login_type))
            
    login_type = request.args.get('type', 'employee')
    return render_template('forgot_password.html', login_type=login_type)

@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    from itsdangerous import SignatureExpired, BadSignature
    serializer = URLSafeTimedSerializer(app.secret_key)
    
    try:
        email = serializer.loads(token, salt='password-reset-salt', max_age=1800)
    except SignatureExpired:
        flash('The reset link has expired. Please request a new one.', 'error')
        return redirect(url_for('forgot_password'))
    except BadSignature:
        flash('Invalid reset link.', 'error')
        return redirect(url_for('forgot_password'))
        
    if request.method == 'POST':
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        if not password or not confirm_password:
            flash('Please fill in all fields.', 'error')
            return render_template('reset_password.html', token=token)
            
        if password != confirm_password:
            flash('Passwords do not match.', 'error')
            return render_template('reset_password.html', token=token)
            
        try:
            hashed_password = generate_password_hash(password)
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT designation FROM users WHERE email = %s", (email,))
            user = cursor.fetchone()
            
            if user:
                cursor.execute("UPDATE users SET password = %s WHERE email = %s", (hashed_password, email))
                conn.commit()
                
                redirect_page = 'client_login' if user['designation'] == 'Client' else 'employee_login'
                flash('Your password has been reset successfully. Please log in.', 'success')
                cursor.close()
                conn.close()
                return redirect(url_for(redirect_page))
            else:
                cursor.close()
                conn.close()
                flash('User not found.', 'error')
                return redirect(url_for('forgot_password'))
                
        except Exception as e:
            print(f"Reset password error: {e}")
            flash('An error occurred. Please try again later.', 'error')
            return render_template('reset_password.html', token=token)
            
    return render_template('reset_password.html', token=token)

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
            # Role validation based on login_type
            if login_type == 'client' and user['designation'] != 'Client':
                flash('Please use the employee login portal.', 'error')
                return redirect(url_for('client_login'))
            
            if login_type == 'employee' and user['designation'] == 'Client':
                flash('Please use the client login portal.', 'error')
                return redirect(url_for('employee_login'))

            session['user_id'] = user['id']
            session['email'] = user['email']
            session['designation'] = user['designation']
            session['full_name'] = user['full_name']
            
            # Add profile_picture to session if the column exists
            session['profile_picture'] = user.get('profile_picture')
            
            # Store client_code in session (None for non-clients)
            session['client_code'] = user.get('client_code')
            
            log_activity(user['id'], 'LOGIN', f"User logged in as {user['designation']}")
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password.', 'error')
            return redirect(url_for(redirect_page))
            
    except Exception as e:
        print(f"Login error: {e}")
        flash('An internal error occurred. Please try again later.', 'error')
        return redirect(url_for(redirect_page))

def get_employee_processed_applications(cursor, user_id):
    # 1. Applications linked to tasks assigned to this user
    cursor.execute("""
        SELECT DISTINCT application_id FROM tasks 
        WHERE assignee_id = %s AND application_id IS NOT NULL
    """, (user_id,))
    app_ids = {row['application_id'] for row in cursor.fetchall()}
    
    # 2. Applications where the user is lead auditor
    cursor.execute("SELECT id FROM applications WHERE lead_auditor_id = %s", (user_id,))
    for row in cursor.fetchall():
        app_ids.add(row['id'])
        
    # 3. Parse from activity logs
    cursor.execute("SELECT details FROM activity_log WHERE user_id = %s", (user_id,))
    logs = cursor.fetchall()
    for log in logs:
        details = log['details'] or ""
        matches = re.findall(r'(?:application\s*#?|app\s*#?)\s*(\d+)', details, re.IGNORECASE)
        for m in matches:
            app_ids.add(int(m))
            
    if not app_ids:
        return []
        
    format_strings = ','.join(['%s'] * len(app_ids))
    query = f"""
        SELECT a.*, u.full_name as lead_auditor_name, cu.client_code
        FROM applications a
        LEFT JOIN users u ON a.lead_auditor_id = u.id
        LEFT JOIN users cu ON a.client_id = cu.id
        WHERE a.id IN ({format_strings})
          AND (a.current_status IS NULL OR a.current_status NOT IN ('Deleted', 'Archived'))
        ORDER BY a.created_at DESC
    """
    cursor.execute(query, tuple(app_ids))
    return cursor.fetchall()


def get_employee_archived_applications(cursor, user_id):
    """Returns applications that were archived by/for this employee."""
    cursor.execute("""
        SELECT DISTINCT application_id FROM tasks 
        WHERE assignee_id = %s AND application_id IS NOT NULL
    """, (user_id,))
    app_ids = {row['application_id'] for row in cursor.fetchall()}

    cursor.execute("SELECT id FROM applications WHERE lead_auditor_id = %s", (user_id,))
    for row in cursor.fetchall():
        app_ids.add(row['id'])

    cursor.execute("SELECT details FROM activity_log WHERE user_id = %s", (user_id,))
    logs = cursor.fetchall()
    for log in logs:
        details = log['details'] or ""
        matches = re.findall(r'(?:application\s*#?|app\s*#?)\s*(\d+)', details, re.IGNORECASE)
        for m in matches:
            app_ids.add(int(m))

    if not app_ids:
        return []

    format_strings = ','.join(['%s'] * len(app_ids))
    query = f"""
        SELECT a.*, u.full_name as lead_auditor_name, cu.client_code
        FROM applications a
        LEFT JOIN users u ON a.lead_auditor_id = u.id
        LEFT JOIN users cu ON a.client_id = cu.id
        WHERE a.id IN ({format_strings})
          AND a.current_status = 'Archived'
        ORDER BY a.created_at DESC
    """
    cursor.execute(query, tuple(app_ids))
    return cursor.fetchall()


@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('home'))
    
    designation = session.get('designation')
    
    # Mapping designations to template filenames
    template_map = {
        'Admin': 'db_admin.html',
        'CEO': 'db_ceo.html',
        'Client': 'db_client.html',
        'Accounts': 'db_accounts.html',
        'Recruiter': 'db_recruiter.html',
        'HR': 'db_hr.html',
        
        # Operational roles mapped to generic employee dashboard
        'Initial reviewer': 'db_employee.html',
        'Inspection planner': 'db_employee.html',
        'Auditor': 'db_employee.html',
        'Technical reviewer': 'db_employee.html',
        'Certifier': 'db_employee.html',
        'Evaluator': 'db_employee.html',
        'Certification officer': 'db_employee.html',
        
        # New roles from user's list
        'Director': 'db_employee.html',
        'Quality Manager': 'db_employee.html',
        'Qulaity Manager': 'db_employee.html', # Accommodating typo in user image
        'Dy. Quality Manager': 'db_employee.html',
        'Reviewer': 'db_employee.html',
        'Trainee Auditor': 'db_employee.html',
        'Tracnet In-charge': 'db_employee.html',
        'Witness Auditor': 'db_employee.html',
        'Trainee': 'db_employee.html',
        'Technical Expert': 'db_employee.html',
        'CEO/Certifier': 'db_ceo.html'
    }
    print(f"DEBUG: Dashboard requested for {designation}")
    template = template_map.get(designation, 'db_base.html')
    print(f"DEBUG: Using template {template}")
    
    enquiries = []
    deleted_enquiries = []
    apps = []
    all_applications = []
    deleted_applications = []
    processed_applications = []
    activities = []
    tasks = []
    employees = []
    documents = []
    registered_clients = []
    job_applications = []
    auditors = []
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        if designation == 'CEO':
            cursor.execute("""
                SELECT a.*, u.full_name as lead_auditor_name, cu.client_code
                FROM applications a
                LEFT JOIN users u ON a.lead_auditor_id = u.id
                LEFT JOIN users cu ON a.client_id = cu.id
                WHERE a.status = 'FINAL_PAYMENT_VERIFIED' AND (a.current_status IS NULL OR a.current_status NOT IN ('Deleted', 'Archived'))
                ORDER BY a.created_at DESC
            """)
            apps = cursor.fetchall()
            cursor.execute("SELECT id, full_name, designation FROM users WHERE designation != 'Client' AND designation != 'CEO'")
            employees = cursor.fetchall()
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
        elif designation == 'Client':
            cursor.execute("SELECT * FROM applications WHERE client_id = %s AND (current_status IS NULL OR current_status != 'Deleted') ORDER BY created_at DESC", (session['user_id'],))
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
            # Role-based workflow filtering
            if designation == 'Admin':
                cursor.execute("""
                    SELECT a.*, u.full_name as lead_auditor_name, cu.client_code
                    FROM applications a
                    LEFT JOIN users u ON a.lead_auditor_id = u.id
                    LEFT JOIN users cu ON a.client_id = cu.id
                    WHERE a.status IN ('APPLICATION_RECEIVED', 'APPLICATION_SUBMITTED', 'PARTIAL_PAYMENT_VERIFIED', 'REJECTED') AND (a.current_status IS NULL OR a.current_status NOT IN ('Deleted', 'Archived'))
                    ORDER BY CASE a.status WHEN 'REJECTED' THEN 0 ELSE 1 END, a.created_at DESC
                """)
                apps = cursor.fetchall()
            elif designation == 'Accounts':
                cursor.execute("""
                    SELECT a.*, u.full_name as client_name, u.client_code
                    FROM applications a
                    JOIN users u ON a.client_id = u.id
                    WHERE a.status IN ('CONTRACT_UPLOADED', 'FINAL_PAYMENT_SUBMITTED') AND (a.current_status IS NULL OR a.current_status NOT IN ('Deleted', 'Archived'))
                    ORDER BY a.created_at DESC
                """)
                apps = cursor.fetchall()
            elif designation == 'Initial reviewer':
                cursor.execute("""
                    SELECT a.*, u.full_name as lead_auditor_name, cu.client_code
                    FROM applications a
                    LEFT JOIN users u ON a.lead_auditor_id = u.id
                    LEFT JOIN users cu ON a.client_id = cu.id
                    WHERE a.status IN ('DOCUMENT_REVIEW', 'CLIENT_DOCUMENT_SUBMISSION_PENDING', 'CLIENT_DOCUMENT_SUBMITTED') AND (a.current_status IS NULL OR a.current_status NOT IN ('Deleted', 'Archived'))
                    ORDER BY a.created_at DESC
                """)
                apps = cursor.fetchall()
                # Fetch auditors list for FMO18 allocation
                cursor.execute("SELECT id, full_name, email FROM users WHERE designation = 'Auditor'")
                auditors = cursor.fetchall()
            elif designation == 'Inspection planner':
                cursor.execute("""
                    SELECT a.*, u.full_name as lead_auditor_name, cu.client_code
                    FROM applications a
                    LEFT JOIN users u ON a.lead_auditor_id = u.id
                    LEFT JOIN users cu ON a.client_id = cu.id
                    WHERE a.status = 'INSPECTION_PLANNING' AND (a.current_status IS NULL OR a.current_status NOT IN ('Deleted', 'Archived'))
                    ORDER BY a.created_at DESC
                """)
                apps = cursor.fetchall()
                cursor.execute("SELECT id, full_name, email FROM users WHERE designation = 'Auditor'")
                auditors = cursor.fetchall()
            elif designation in ['Auditor', 'Trainee Auditor', 'Witness Auditor']:
                cursor.execute("""
                    SELECT a.*, u.full_name as lead_auditor_name, cu.client_code
                    FROM applications a
                    LEFT JOIN users u ON a.lead_auditor_id = u.id
                    LEFT JOIN users cu ON a.client_id = cu.id
                    WHERE a.status = 'AUDIT_IN_PROGRESS' AND (a.current_status IS NULL OR a.current_status NOT IN ('Deleted', 'Archived'))
                    ORDER BY a.created_at DESC
                """)
                apps = cursor.fetchall()
            elif designation == 'Technical reviewer':
                cursor.execute("""
                    SELECT a.*, u.full_name as lead_auditor_name, cu.client_code
                    FROM applications a
                    LEFT JOIN users u ON a.lead_auditor_id = u.id
                    LEFT JOIN users cu ON a.client_id = cu.id
                    WHERE a.status = 'TECHNICAL_REVIEW' AND (a.current_status IS NULL OR a.current_status NOT IN ('Deleted', 'Archived'))
                    ORDER BY a.created_at DESC
                """)
                apps = cursor.fetchall()
            elif designation in ['Certifier', 'CEO']:
                cursor.execute("""
                    SELECT a.*, u.full_name as lead_auditor_name, cu.client_code
                    FROM applications a
                    LEFT JOIN users u ON a.lead_auditor_id = u.id
                    LEFT JOIN users cu ON a.client_id = cu.id
                    WHERE a.status = 'FINAL_PAYMENT_VERIFIED' AND (a.current_status IS NULL OR a.current_status NOT IN ('Deleted', 'Archived'))
                    ORDER BY a.created_at DESC
                """)
                apps = cursor.fetchall()
            else:
                cursor.execute("""
                    SELECT a.*, u.full_name as lead_auditor_name, cu.client_code
                    FROM applications a
                    LEFT JOIN users u ON a.lead_auditor_id = u.id
                    LEFT JOIN users cu ON a.client_id = cu.id
                    WHERE a.current_status IS NULL OR a.current_status NOT IN ('Deleted', 'Archived')
                    ORDER BY a.created_at DESC LIMIT 10
                """)
                apps = cursor.fetchall()

            # For regular workflow employees, fetch their processed applications history
            if designation not in ['CEO', 'Admin', 'Client', 'HR', 'Recruiter']:
                processed_applications = get_employee_processed_applications(cursor, session['user_id'])
                deleted_applications = get_employee_archived_applications(cursor, session['user_id'])

        # Shared Data for Management (CEO, Admin & Quality Managers)
        if designation in ['CEO', 'Admin', 'Quality Manager', 'Qulaity Manager', 'Dy. Quality Manager']:
            cursor.execute("SELECT * FROM enquiries WHERE status != 'DELETED' ORDER BY created_at DESC")
            enquiries = cursor.fetchall()
            cursor.execute("SELECT * FROM enquiries WHERE status = 'DELETED' ORDER BY created_at DESC")
            deleted_enquiries = cursor.fetchall()
            
            cursor.execute("SELECT id, full_name, email, created_at, client_code FROM users WHERE designation = 'Client' ORDER BY created_at DESC")
            registered_clients = cursor.fetchall()
            
            cursor.execute("""
                SELECT a.*, u.full_name as lead_auditor_name, cu.client_code
                FROM applications a
                LEFT JOIN users u ON a.lead_auditor_id = u.id
                LEFT JOIN users cu ON a.client_id = cu.id
                ORDER BY a.created_at DESC
            """)
            all_applications = cursor.fetchall()
            
            # Fetch deleted/archived applications
            cursor.execute("""
                SELECT a.*, u.full_name as lead_auditor_name, cu.client_code
                FROM applications a
                LEFT JOIN users u ON a.lead_auditor_id = u.id
                LEFT JOIN users cu ON a.client_id = cu.id
                WHERE a.current_status IN ('Deleted', 'Archived')
                ORDER BY a.created_at DESC
            """)
            deleted_applications = cursor.fetchall()

        if designation == 'HR':
            cursor.execute("SELECT * FROM job_applications ORDER BY created_at DESC")
            job_applications = cursor.fetchall()

        if designation == 'Recruiter':
            cursor.execute("SELECT id, full_name, email, created_at, client_code FROM users WHERE designation = 'Client' ORDER BY created_at DESC")
            registered_clients = cursor.fetchall()
            # Fetch ALL applications (all statuses) for the Registered Clients dropdown
            cursor.execute("""
                SELECT a.*, u.full_name as lead_auditor_name, cu.client_code
                FROM applications a
                LEFT JOIN users u ON a.lead_auditor_id = u.id
                LEFT JOIN users cu ON a.client_id = cu.id
                WHERE a.current_status IS NULL OR a.current_status NOT IN ('Deleted', 'Archived')
                ORDER BY a.created_at DESC
            """)
            all_applications = cursor.fetchall()
            # Fetch recruiter processed history (Step 1b reviews they did)
            # Find apps that recruiter reviewed from the activity log or by status transition
            cursor.execute("""
                SELECT a.*, u.full_name as lead_auditor_name, cu.client_code
                FROM applications a
                LEFT JOIN users u ON a.lead_auditor_id = u.id
                LEFT JOIN users cu ON a.client_id = cu.id
                WHERE a.status IN ('PENDING_CONTRACT_QUOTATION', 'APPLICATION_REJECTED_1B')
                  AND (a.current_status IS NULL OR a.current_status NOT IN ('Deleted', 'Archived'))
                ORDER BY a.updated_at DESC
            """)
            processed_applications = cursor.fetchall()
            
            # Also fetch deleted/archived applications for Recruiter
            cursor.execute("""
                SELECT a.*, u.full_name as lead_auditor_name, cu.client_code
                FROM applications a
                LEFT JOIN users u ON a.lead_auditor_id = u.id
                LEFT JOIN users cu ON a.client_id = cu.id
                WHERE a.current_status IN ('Deleted', 'Archived')
                ORDER BY a.created_at DESC
            """)
            deleted_applications = cursor.fetchall()

        # Fetch Documents based on role
        if designation in ['CEO', 'Admin', 'QA', 'Director', 'Quality Manager', 'Qulaity Manager', 'Dy. Quality Manager', 'CEO/Certifier']:
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
        elif designation in ['Initial reviewer', 'Inspection planner', 'Auditor', 'Technical reviewer', 'Certifier', 'Evaluator', 'Certification officer']:
            cursor.execute("""
                SELECT d.*, u.full_name as client_name 
                FROM documents d 
                JOIN users u ON d.client_id = u.id 
                ORDER BY d.uploaded_at DESC
            """)
            documents = cursor.fetchall()
            
        # Fetch unread message count for badge
        unread_count = 0
        if 'user_id' in session:
            cursor.execute("SELECT COUNT(*) as count FROM messages WHERE receiver_id = %s AND is_read = FALSE", (session['user_id'],))
            unread_count = cursor.fetchone()['count']

        # --- Training Assessment Data ---
        assessments = []
        archived_assessments = []
        pending_assessments = []
        if designation == 'CEO':
            cursor.execute("SELECT * FROM training_assessments WHERE is_archived = FALSE ORDER BY created_at DESC")
            assessments = cursor.fetchall()
            cursor.execute("SELECT * FROM training_assessments WHERE is_archived = TRUE ORDER BY created_at DESC")
            archived_assessments = cursor.fetchall()
        elif designation != 'Client':
            cursor.execute("""
                SELECT aa.*, ta.title, ta.training_type 
                FROM assessment_assignments aa
                JOIN training_assessments ta ON aa.assessment_id = ta.id
                WHERE aa.employee_id = %s AND aa.status = 'PENDING'
                ORDER BY aa.assigned_at DESC
            """, (session['user_id'],))
            pending_assessments = cursor.fetchall()

        print(f"DEBUG: Designation={designation}, Apps Found={len(apps)}")
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"DEBUG: Error fetching dashboard data: {e}")
        
    return render_template(template, user=session, applications=apps, all_applications=all_applications, enquiries=enquiries, deleted_enquiries=deleted_enquiries, deleted_applications=deleted_applications, processed_applications=processed_applications, activities=activities, tasks=tasks, employees=employees, documents=documents, registered_clients=registered_clients, unread_count=unread_count, job_applications=job_applications, auditors=auditors, assessments=assessments, archived_assessments=archived_assessments, pending_assessments=pending_assessments)

# --- Auditor Audit List Route ---
@app.route('/auditor/audit-list')
def auditor_audit_list():
    if 'user_id' not in session or session.get('designation') not in ['Auditor', 'Trainee Auditor', 'Witness Auditor']:
        flash('Unauthorized access.', 'error')
        return redirect(url_for('employee_login'))
    applications = []
    unread_count = 0
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        designation = session.get('designation')
        if designation == 'Auditor':
            # Auditors see all audits assigned to them or in audit-related stages
            cursor.execute("""
                SELECT a.*, u.full_name as lead_auditor_name,
                       cu.client_code, cu.full_name as company_name
                FROM applications a
                LEFT JOIN users u ON a.lead_auditor_id = u.id
                LEFT JOIN users cu ON a.client_id = cu.id
                WHERE a.lead_auditor_id = %s OR a.status IN ('AUDIT_IN_PROGRESS', 'TECHNICAL_REVIEW', 'CERTIFICATE_ISSUED', 'FINAL_PAYMENT_PENDING', 'FINAL_PAYMENT_VERIFIED')
                ORDER BY a.created_at DESC
            """, (session['user_id'],))
        else:
            # Trainee / Witness auditors see all audit-in-progress items
            cursor.execute("""
                SELECT a.*, u.full_name as lead_auditor_name,
                       cu.client_code, cu.full_name as company_name
                FROM applications a
                LEFT JOIN users u ON a.lead_auditor_id = u.id
                LEFT JOIN users cu ON a.client_id = cu.id
                WHERE a.status IN ('AUDIT_IN_PROGRESS', 'TECHNICAL_REVIEW', 'CERTIFICATE_ISSUED', 'FINAL_PAYMENT_PENDING', 'FINAL_PAYMENT_VERIFIED')
                ORDER BY a.created_at DESC
            """)
        applications = cursor.fetchall()
        cursor.execute(
            "SELECT COUNT(*) as count FROM messages WHERE receiver_id = %s AND is_read = FALSE",
            (session['user_id'],)
        )
        unread_count = cursor.fetchone()['count']
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Error fetching audit list: {e}")
    return render_template(
        'db_auditor_audit_list.html',
        user=session,
        applications=applications,
        unread_count=unread_count,
        tasks=[],
        auditors=[]
    )

@app.route('/auditor/audit-details/<int:app_id>')
def auditor_audit_details(app_id):
    if 'user_id' not in session or session.get('designation') not in ['Auditor', 'Trainee Auditor', 'Witness Auditor']:
        flash('Unauthorized access.', 'error')
        return redirect(url_for('employee_login'))
        
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT a.*, u.full_name as lead_auditor_name,
                   cu.client_code, cu.full_name as company_name
            FROM applications a
            LEFT JOIN users u ON a.lead_auditor_id = u.id
            LEFT JOIN users cu ON a.client_id = cu.id
            WHERE a.id = %s
        """, (app_id,))
        app_data = cursor.fetchone()
        
        if not app_data:
            cursor.close()
            conn.close()
            flash('Audit record not found.', 'error')
            return redirect(url_for('auditor_audit_list'))
            
        cursor.execute(
            "SELECT COUNT(*) as count FROM messages WHERE receiver_id = %s AND is_read = FALSE",
            (session['user_id'],)
        )
        unread_count = cursor.fetchone()['count']
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Error fetching audit details: {e}")
        flash('Error loading audit details.', 'error')
        return redirect(url_for('auditor_audit_list'))
        
    return render_template(
        'db_auditor_audit_details.html',
        user=session,
        app=app_data,
        unread_count=unread_count
    )


@app.route('/submit-application', methods=['POST'])
def submit_application():
    company_name = request.form.get('company_name')
    program_type = request.form.get('program_type')
    scope = request.form.get('scope')
    
    # TEMP: Only allow COR program for now
    if program_type and program_type != 'COR':
        flash('Currently, only COR certification applications are being accepted. Other programs will be available soon.', 'error')
        return redirect(url_for('apply'))
    
    # Check if user is logged in
    is_client = 'user_id' in session and session.get('designation') == 'Client'
    
    if is_client:
        if not company_name or not program_type or not scope:
            flash('Please fill all fields, including the scope.', 'error')
            return redirect(url_for('apply'))
            
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Check for existing application with same client_id and program_type
            cursor.execute("SELECT id FROM applications WHERE client_id = %s AND program_type = %s", (session['user_id'], program_type))
            if cursor.fetchone():
                flash(f'You have already applied for the {program_type} program.', 'error')
                cursor.close()
                conn.close()
                return redirect(url_for('apply'))
                
            # Fetch client_code to generate project_code
            cursor.execute("SELECT client_code FROM users WHERE id = %s", (session['user_id'],))
            cc_row = cursor.fetchone()
            client_code = cc_row[0] if cc_row and cc_row[0] else None
            project_code = generate_project_code(cursor, session['user_id'], client_code) if client_code else None
            cursor.execute(
                "INSERT INTO applications (client_id, company_name, program_type, scope, status, project_code) VALUES (%s, %s, %s, %s, 'APPLICATION_RECEIVED', %s)",
                (session['user_id'], company_name, program_type, scope, project_code)
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
    else:
        # User is a guest, process as enquiry
        name = request.form.get('full_name')
        email = request.form.get('email')
        phone = request.form.get('phone')
        
        if not name or not email or not phone or not company_name or not program_type or not scope:
            flash('Please fill all required fields, including the scope.', 'error')
            return redirect(url_for('apply'))
            
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO enquiries (name, company_name, email, phone, program_type, scope, message, status) VALUES (%s, %s, %s, %s, %s, %s, 'Submitted via application form', 'NEW')",
                (name, company_name, email, phone, program_type, scope)
            )
            conn.commit()
            cursor.close()
            conn.close()
            log_activity(None, 'APPLICATION_ENQUIRY', f"New enquiry/app from guest {name} for {company_name}")
            
            # Notify Apply@go4agri.co.in
            msg = Message('New Guest Application Received', recipients=['Apply@go4agri.co.in'])
            msg.body = f"New application from guest:\nName: {name}\nEmail: {email}\nCompany: {company_name}\nProgram: {program_type}\nScope: {scope}"
            Thread(target=send_async_email, args=(app, msg)).start()
            
            flash('Your application/enquiry has been submitted! Our team will review it and contact you to set up your account.', 'success')
            return redirect(url_for('home'))
        except Exception as e:
            print(f"Error submitting guest application: {e}")
            flash('An error occurred. Please try again later.', 'error')
            return redirect(url_for('apply'))

@app.route('/upload-application-form/<int:app_id>', methods=['POST'])
def upload_application_form(app_id):
    """Client uploads their filled Application.xlsx to submit for admin review."""
    if 'user_id' not in session or session.get('designation') != 'Client':
        flash('Unauthorized access.', 'error')
        return redirect(url_for('client_login'))

    form_file = request.files.get('application_form')
    if not form_file or form_file.filename == '':
        flash('Please select the filled application file to upload.', 'error')
        return redirect(url_for('dashboard'))

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT status FROM applications WHERE id = %s AND client_id = %s", (app_id, session['user_id']))
        app_data = cursor.fetchone()

        if not app_data:
            flash('Application not found.', 'error')
            cursor.close()
            conn.close()
            return redirect(url_for('dashboard'))

        is_resubmission = (app_data[0] == 'APPLICATION_REJECTED_1B')
        if app_data[0] not in ['APPLICATION_RECEIVED', 'NEW', 'APPLICATION_REJECTED_1B', None]:
            flash('Application form has already been submitted.', 'info')
            cursor.close()
            conn.close()
            return redirect(url_for('dashboard'))

        # Save the uploaded application form
        f_filename = secure_filename(f"app_form_{app_id}_{form_file.filename}")
        f_filepath = os.path.join(app.config['UPLOAD_FOLDER'], f_filename)
        form_file.save(f_filepath)

        # Save document record
        cursor.execute(
            "INSERT INTO documents (client_id, application_id, filename, filepath, category) VALUES (%s, %s, %s, %s, 'APPLICATION_FORM')",
            (session['user_id'], app_id, f_filename, f_filename)
        )

        # Advance status to APPLICATION_SUBMITTED (waiting for admin/CEO review)
        cursor.execute(
            "UPDATE applications SET status = 'APPLICATION_SUBMITTED' WHERE id = %s",
            (app_id,)
        )
        conn.commit()

        # Notify Apply desk by email
        try:
            notify_msg = Message(
                'New Application Form Submitted for Review' if not is_resubmission else 'Application Re-Submitted for Re-Review',
                recipients=['Apply@go4agri.co.in']
            )
            notify_msg.body = (
                f"{'RE-SUBMISSION' if is_resubmission else 'NEW SUBMISSION'}: A client has submitted their filled application form.\n\n"
                f"Application ID: {app_id}\n"
                f"Client: {session.get('full_name')}\n\n"
                f"Please review it on the admin dashboard and Accept (FMO11) or Reject (FMO15)."
            )
            Thread(target=send_async_email, args=(app, notify_msg)).start()
        except Exception as email_err:
            print(f"Email to Apply desk failed: {email_err}")

        log_activity(session['user_id'], 'UPLOAD_APPLICATION_FORM', f"{'Re-submitted' if is_resubmission else 'Uploaded'} filled application form for app {app_id}")
        flash(
            'Application re-submitted to Apply Desk for re-review! You will be notified via messages.' if is_resubmission
            else 'Application form uploaded and sent to Apply Desk (Apply@go4agri.co.in) for review!',
            'success'
        )

        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Error uploading application form: {e}")
        flash('Error uploading application form. Please try again.', 'error')

    return redirect(url_for('dashboard'))


@app.route('/apply-desk/review/<int:app_id>', methods=['POST'])
def apply_desk_review(app_id):
    """Unified Apply Desk review: employee uploads FMO11 (accept) or FMO15 (reject) and clicks Accept or Reject."""
    allowed_roles = ['Admin', 'CEO', 'CEO/Certifier', 'Recruiter']
    if 'user_id' not in session or session.get('designation') not in allowed_roles:
        flash('Unauthorized access.', 'error')
        return redirect(url_for('dashboard'))

    action = request.form.get('action', '').strip().lower()  # 'accept' or 'reject'
    if action not in ('accept', 'reject'):
        flash('Invalid action.', 'error')
        return redirect(url_for('dashboard'))

    # Validate file upload
    response_file = request.files.get('response_form')
    if not response_file or response_file.filename == '':
        flash('Please upload the response form (FMO11 or FMO15) before proceeding.', 'error')
        return redirect(url_for('dashboard'))

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT a.*, u.full_name as client_name, u.id as client_user_id
            FROM applications a JOIN users u ON a.client_id = u.id
            WHERE a.id = %s
        """, (app_id,))
        application = cursor.fetchone()
        if not application:
            flash('Application not found.', 'error')
            cursor.close(); conn.close()
            return redirect(url_for('dashboard'))
        if application['status'] != 'APPLICATION_SUBMITTED':
            flash('Application is not awaiting Apply Desk review.', 'error')
            cursor.close(); conn.close()
            return redirect(url_for('dashboard'))

        # Save the uploaded response form (FMO11 or FMO15)
        safe_orig = secure_filename(response_file.filename)
        label = 'FMO11' if action == 'accept' else 'FMO15'
        saved_filename = secure_filename(f"{label}_app{app_id}_{safe_orig}")
        saved_path = os.path.join(app.config['UPLOAD_FOLDER'], saved_filename)
        response_file.save(saved_path)

        if action == 'accept':
            # Advance status to Contract & Quotation
            cursor.execute("UPDATE applications SET status = 'PENDING_CONTRACT_QUOTATION' WHERE id = %s", (app_id,))
            subject = f'Application #{app_id} Accepted — Letter of Registration (FMO11)'
            body = (
                f"Dear {application['client_name']},\n\n"
                f"We are pleased to inform you that your application for {application['program_type']} "
                f"certification ({application['company_name']}) has been reviewed and ACCEPTED by our Apply Desk.\n\n"
                f"Please find your Letter of Registration attached to this message.\n\n"
                f"You may now proceed to Step 2: Contract & Quotation on your dashboard.\n\n"
                f"Best regards,\nGo4Agri Apply Desk\nApply@go4agri.co.in"
            )
            flash_msg = f'Application #{app_id} accepted. FMO11 sent to client. Moved to Contract & Quotation.'
            log_action = f'Accepted application {app_id} at Step 1b — FMO11 uploaded and sent to client.'
            activity_type = 'APPLY_DESK_ACCEPT'
        else:
            # Set status to APPLICATION_REJECTED_1B — client must re-submit
            cursor.execute("UPDATE applications SET status = 'APPLICATION_REJECTED_1B' WHERE id = %s", (app_id,))
            subject = f'Application #{app_id} — Letter of Rejection (FMO15) — Action Required'
            body = (
                f"Dear {application['client_name']},\n\n"
                f"After reviewing your application for {application['program_type']} certification "
                f"({application['company_name']}), we regret to inform you that your application has "
                f"NOT been accepted at this stage.\n\n"
                f"Please find your Letter of Rejection attached to this message for detailed reasons.\n\n"
                f"You may re-submit your corrected application from your dashboard (Step 1b — Re-Submit Application).\n\n"
                f"Best regards,\nGo4Agri Apply Desk\nApply@go4agri.co.in"
            )
            flash_msg = f'Application #{app_id} rejected. FMO15 sent to client. Client must re-submit.'
            log_action = f'Rejected application {app_id} at Step 1b — FMO15 uploaded and sent to client.'
            activity_type = 'APPLY_DESK_REJECT'

        # Send internal message to client with the uploaded form as attachment
        cursor.execute(
            "INSERT INTO messages (sender_id, receiver_id, subject, body, attachment_filename, attachment_path) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (session['user_id'], application['client_user_id'],
             subject, body, saved_filename, saved_filename)
        )
        conn.commit()
        cursor.close(); conn.close()
        log_activity(session['user_id'], activity_type, log_action)
        flash(flash_msg, 'success')
    except Exception as e:
        print(f'Error in apply_desk_review: {e}')
        flash('Error processing the review. Please try again.', 'error')
    return redirect(url_for('dashboard'))


@app.route('/confirm-application/<int:app_id>', methods=['POST'])
def confirm_application(app_id):
    """CEO or Admin confirms the client's submitted application form, advancing to contract phase."""
    if 'user_id' not in session or session.get('designation') not in ['CEO', 'Admin', 'CEO/Certifier']:
        flash('Unauthorized access.', 'error')
        return redirect(url_for('dashboard'))

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT status FROM applications WHERE id = %s", (app_id,))
        app_data = cursor.fetchone()

        if app_data:
            current_status = app_data[0]
            if current_status in ['APPLICATION_SUBMITTED', 'APPLICATION_RECEIVED', 'NEW', None]:
                cursor.execute(
                    "UPDATE applications SET status = 'PENDING_CONTRACT_QUOTATION' WHERE id = %s",
                    (app_id,)
                )
                conn.commit()
                log_activity(session['user_id'], 'CONFIRM_APPLICATION', f"Confirmed application {app_id}")
                flash('Application confirmed! Client can now proceed to contract & quotation.', 'success')
            else:
                flash('Application is already in an advanced stage.', 'info')
        else:
            flash('Application not found.', 'error')

        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Error confirming application: {e}")
        flash('Error confirming application.', 'error')

    return redirect(url_for('dashboard'))

@app.route('/submit-contract/<int:app_id>', methods=['POST'])
def submit_contract(app_id):
    if 'user_id' not in session or session.get('designation') != 'Client':
        flash('Unauthorized access.', 'error')
        return redirect(url_for('client_login'))
        
    contract_file = request.files.get('contract')
    receipt_file = request.files.get('payment_receipt')
    licence_file = request.files.get('licence_agreement')
    txn_no = request.form.get('partial_payment_txn')
    
    if not contract_file or not receipt_file or not txn_no:
        flash('Please provide the signed contract, payment receipt, and transaction ID.', 'error')
        return redirect(url_for('dashboard'))
        
    try:
        # Save Contract
        c_filename = secure_filename(f"contract_{app_id}_{contract_file.filename}")
        c_filepath = os.path.join(app.config['UPLOAD_FOLDER'], c_filename)
        contract_file.save(c_filepath)
        
        # Save Receipt
        r_filename = secure_filename(f"receipt_{app_id}_{receipt_file.filename}")
        r_filepath = os.path.join(app.config['UPLOAD_FOLDER'], r_filename)
        receipt_file.save(r_filepath)
        
        # Save Licence Agreement (optional)
        l_filename = None
        if licence_file and licence_file.filename:
            l_filename = secure_filename(f"licence_{app_id}_{licence_file.filename}")
            l_filepath = os.path.join(app.config['UPLOAD_FOLDER'], l_filename)
            licence_file.save(l_filepath)
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Save document entries
        cursor.execute(
            "INSERT INTO documents (client_id, application_id, filename, filepath, category) VALUES (%s, %s, %s, %s, 'SIGNED_CONTRACT')",
            (session['user_id'], app_id, c_filename, c_filename)
        )
        cursor.execute(
            "INSERT INTO documents (client_id, application_id, filename, filepath, category) VALUES (%s, %s, %s, %s, 'PAYMENT_RECEIPT')",
            (session['user_id'], app_id, r_filename, r_filename)
        )
        if l_filename:
            cursor.execute(
                "INSERT INTO documents (client_id, application_id, filename, filepath, category) VALUES (%s, %s, %s, %s, 'LICENCE_AGREEMENT')",
                (session['user_id'], app_id, l_filename, l_filename)
            )
        
        # Update application status
        cursor.execute(
            "UPDATE applications SET status = 'CONTRACT_UPLOADED', partial_payment_txn = %s WHERE id = %s",
            (txn_no, app_id)
        )
        
        conn.commit()
        cursor.close()
        conn.close()
        
        log_activity(session['user_id'], 'UPLOAD_CONTRACT_PAYMENT', f"Uploaded contract, receipt{'+ licence' if l_filename else ''} and txn {txn_no} for app {app_id}")
        flash('Contract and payment receipt submitted successfully! Admin will review them.', 'success')
    except Exception as e:
        print(f"Error uploading contract/receipt: {e}")
        flash('Error submitting documents.', 'error')
        
    return redirect(url_for('dashboard'))

@app.route('/submit-final-payment/<int:app_id>', methods=['POST'])
def submit_final_payment(app_id):
    if 'user_id' not in session or session.get('designation') != 'Client':
        flash('Unauthorized access.', 'error')
        return redirect(url_for('client_login'))
        
    txn_no = request.form.get('final_payment_txn')
    receipt_file = request.files.get('final_payment_receipt')
    
    if not txn_no or not receipt_file or receipt_file.filename == '':
        flash('Please provide both transaction number and payment receipt.', 'error')
        return redirect(url_for('dashboard'))
        
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Securely save the receipt
        filename = secure_filename(f"final_payment_{app_id}_{receipt_file.filename}")
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        receipt_file.save(filepath)
        
        # Save to documents table
        cursor.execute(
            "INSERT INTO documents (client_id, application_id, filename, filepath, category) VALUES (%s, %s, %s, %s, 'FINAL_PAYMENT_RECEIPT')",
            (session['user_id'], app_id, filename, filename)
        )
        
        # Update application status
        cursor.execute(
            "UPDATE applications SET status = 'FINAL_PAYMENT_SUBMITTED', final_payment_txn = %s WHERE id = %s",
            (txn_no, app_id)
        )
        conn.commit()
        cursor.close()
        conn.close()
        
        log_activity(session['user_id'], 'SUBMIT_FINAL_PAYMENT', f"Submitted final payment txn {txn_no} and receipt for app {app_id}")
        flash('Final payment details submitted! Admin will verify and issue your certificate.', 'success')
    except Exception as e:
        print(f"Error submitting final payment: {e}")
        flash('Error submitting final payment.', 'error')
        
    return redirect(url_for('dashboard'))

@app.route('/download-template/<path:filename>')
def download_template(filename):
    allowed_files = [
        "Processing_&_Handling_FEED_Application Packet.zip",
        "Processing_&_Handling_FOOD_Application Packet.zip",
        "Production_Application_Packet.zip",
        "Application.xlsx",
        "FMO32_Quotation.docx",
        "FMO07_Certification License Agreement.docx"
    ]
    if filename in allowed_files:
        try:
            return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=True)
        except Exception as e:
            print(f"Error downloading template: {e}")
            flash('Error downloading template.', 'error')
    else:
        flash('Invalid file requested.', 'error')
    return redirect(request.referrer or url_for('dashboard'))

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
        
        # Notify Apply@go4agri.co.in
        msg = Message('New Enquiry Received', recipients=['Apply@go4agri.co.in'])
        msg.body = f"New enquiry from {name}:\nEmail: {email}\nPhone: {phone}\nProgram: {program_type}\nMessage: {message}"
        Thread(target=send_async_email, args=(app, msg)).start()
    except Exception as e:
        print(f"Error submitting enquiry: {e}")
        flash('An error occurred. Please try again later.', 'error')
        
    return redirect(url_for('certification_schemes'))

@app.route('/upload-review-templates/<int:app_id>', methods=['POST'])
def upload_review_templates(app_id):
    if 'user_id' not in session or session.get('designation') not in ['Initial reviewer', 'Admin', 'CEO']:
        flash('Unauthorized access.', 'error')
        return redirect(url_for('dashboard'))
    
    files = request.files.getlist('review_templates')
    if not files or all(f.filename == '' for f in files):
        flash('Please select at least one template document to upload.', 'error')
        return redirect(request.referrer or url_for('dashboard'))
    
    submit_action = request.form.get('submit_action', 'upload')
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Get client_id
        cursor.execute("SELECT client_id FROM applications WHERE id = %s", (app_id,))
        result = cursor.fetchone()
        if not result:
            flash('Application not found.', 'error')
            cursor.close(); conn.close()
            return redirect(request.referrer or url_for('dashboard'))
        client_id = result['client_id']
        
        uploaded_count = 0
        for file in files:
            if file and file.filename != '':
                filename = secure_filename(f"template_{app_id}_{file.filename}")
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                
                cursor.execute(
                    "INSERT INTO documents (client_id, application_id, filename, filepath, category) VALUES (%s, %s, %s, %s, 'REVIEW_TEMPLATE')",
                    (client_id, app_id, filename, filename)
                )
                uploaded_count += 1
        
        conn.commit()
        
        if submit_action == 'upload_and_send':
            cursor.execute("SELECT a.*, u.full_name as client_name, u.id as client_user_id FROM applications a JOIN users u ON a.client_id = u.id WHERE a.id = %s", (app_id,))
            app_details = cursor.fetchone()
            
            if app_details:
                cursor.execute("UPDATE applications SET status = 'CLIENT_DOCUMENT_SUBMISSION_PENDING' WHERE id = %s", (app_id,))
                
                sender_name = session.get('full_name', 'Initial Reviewer')
                cursor.execute(
                    "INSERT INTO messages (sender_id, receiver_id, subject, body, is_read) VALUES (%s, %s, %s, %s, 0)",
                    (session['user_id'], app_details['client_user_id'],
                     f"Action Required: Document Review Templates Ready for App #{app_id}",
                     f"Dear {app_details['client_name']},\n\n"
                     f"The Initial Reviewer ({sender_name}) has uploaded the required document templates for your certification "
                     f"under Step 3: Document Review.\n\n"
                     f"Please log in to your dashboard, download the templates, fill them out, and upload the completed versions.\n\n"
                     f"Best regards,\nGo4Agri Review Team")
                )
                conn.commit()
                flash(f'Successfully uploaded {uploaded_count} template(s) and sent to client. Application status updated to CLIENT_DOCUMENT_SUBMISSION_PENDING.', 'success')
            else:
                flash(f'Successfully uploaded {uploaded_count} template(s), but application was not found for sending.', 'error')
        else:
            flash(f'Successfully uploaded {uploaded_count} review template(s).', 'success')
            
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Error uploading review templates: {e}")
        flash('Error uploading review templates.', 'error')
        
    return redirect(request.referrer or url_for('dashboard'))

@app.route('/send-review-templates/<int:app_id>', methods=['POST'])
def send_review_templates(app_id):
    if 'user_id' not in session or session.get('designation') not in ['Initial reviewer', 'Admin', 'CEO']:
        flash('Unauthorized access.', 'error')
        return redirect(url_for('dashboard'))
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Verify template exists
        cursor.execute("SELECT id FROM documents WHERE application_id = %s AND category = 'REVIEW_TEMPLATE'", (app_id,))
        if not cursor.fetchone():
            flash('Please upload at least one review template before sending to the client.', 'error')
            cursor.close(); conn.close()
            return redirect(request.referrer or url_for('dashboard'))
        
        # Fetch application details
        cursor.execute("SELECT a.*, u.full_name as client_name, u.id as client_user_id FROM applications a JOIN users u ON a.client_id = u.id WHERE a.id = %s", (app_id,))
        app_details = cursor.fetchone()
        
        if app_details:
            # Update application status
            cursor.execute("UPDATE applications SET status = 'CLIENT_DOCUMENT_SUBMISSION_PENDING' WHERE id = %s", (app_id,))
            
            # Send system message to client
            sender_name = session.get('full_name', 'Initial Reviewer')
            cursor.execute(
                "INSERT INTO messages (sender_id, receiver_id, subject, body, is_read) VALUES (%s, %s, %s, %s, 0)",
                (session['user_id'], app_details['client_user_id'],
                 f"Action Required: Document Review Templates Ready for App #{app_id}",
                 f"Dear {app_details['client_name']},\n\n"
                 f"The Initial Reviewer ({sender_name}) has uploaded the required document templates for your certification "
                 f"under Step 3: Document Review.\n\n"
                 f"Please log in to your dashboard, download the templates, fill them out, and upload the completed versions.\n\n"
                 f"Best regards,\nGo4Agri Review Team")
            )
            conn.commit()
            flash('Templates sent to client. Application status updated to CLIENT_DOCUMENT_SUBMISSION_PENDING.', 'success')
        else:
            flash('Application not found.', 'error')
            
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Error sending review templates: {e}")
        flash('Error sending templates to client.', 'error')
        
    return redirect(request.referrer or url_for('dashboard'))

@app.route('/submit-client-review-documents/<int:app_id>', methods=['POST'])
def submit_client_review_documents(app_id):
    if 'user_id' not in session or session.get('designation') != 'Client':
        flash('Unauthorized access.', 'error')
        return redirect(url_for('dashboard'))
    
    action = request.form.get('action') # 'upload', 'submit', or 'upload_and_submit'
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Verify ownership
        cursor.execute("SELECT * FROM applications WHERE id = %s AND client_id = %s", (app_id, session['user_id']))
        application = cursor.fetchone()
        if not application:
            flash('Application not found or unauthorized access.', 'error')
            cursor.close(); conn.close()
            return redirect(url_for('dashboard'))
        
        if action in ['upload', 'upload_and_submit']:
            files = request.files.getlist('client_review_docs')
            if not files or all(f.filename == '' for f in files):
                flash('Please select at least one document to upload.', 'error')
                cursor.close(); conn.close()
                return redirect(request.referrer or url_for('dashboard'))
            
            uploaded_count = 0
            for file in files:
                if file and file.filename != '':
                    filename = secure_filename(f"client_filled_{app_id}_{file.filename}")
                    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    file.save(filepath)
                    
                    cursor.execute(
                        "INSERT INTO documents (client_id, application_id, filename, filepath, category) VALUES (%s, %s, %s, %s, 'CLIENT_FILLED_DOCUMENT')",
                        (session['user_id'], app_id, filename, filename)
                    )
                    uploaded_count += 1
            
            conn.commit()
            if action == 'upload':
                flash(f'Successfully uploaded {uploaded_count} filled document(s). You can upload more, or click Finalize & Submit to send them to the reviewer.', 'success')
            else:
                # Update application status
                cursor.execute("UPDATE applications SET status = 'CLIENT_DOCUMENT_SUBMITTED' WHERE id = %s", (app_id,))
                
                # Notify Initial Reviewer
                send_system_message('Initial reviewer', 'Client Review Documents Submitted', f'Client has submitted their review documents for application {app_id}.')
                conn.commit()
                flash(f'Successfully uploaded {uploaded_count} filled document(s) and submitted to the Initial Reviewer successfully.', 'success')
        
        elif action == 'submit':
            # Verify client has uploaded at least one filled document
            cursor.execute("SELECT id FROM documents WHERE application_id = %s AND category = 'CLIENT_FILLED_DOCUMENT'", (app_id,))
            if not cursor.fetchall():
                flash('Please upload at least one completed document before submitting.', 'error')
            else:
                # Update application status
                cursor.execute("UPDATE applications SET status = 'CLIENT_DOCUMENT_SUBMITTED' WHERE id = %s", (app_id,))
                
                # Notify Initial Reviewer
                send_system_message('Initial reviewer', 'Client Review Documents Submitted', f'Client has submitted their review documents for application {app_id}.')
                conn.commit()
                flash('Your documents have been submitted to the Initial Reviewer successfully.', 'success')
                
        cursor.close()
        conn.close()
    except Exception as e:
        import traceback
        print(f"Error submitting client review documents: {e}")
        print(traceback.format_exc())
        flash(f'Error processing your request: {e}', 'error')
        
    return redirect(request.referrer or url_for('dashboard'))

@app.route('/update-application-status/<int:app_id>', methods=['POST'])
def update_application_status(app_id):
    if 'user_id' not in session:
        return redirect(url_for('employee_login'))
        
    role = session.get('designation')
    
    # Define 14-step workflow transitions map (current_status -> role -> next_status)
    transitions = {
        'APPLICATION_RECEIVED': { 'Admin': 'CLIENT_REGISTERED' },
        'CLIENT_REGISTERED': { 'Admin': 'PENDING_CONTRACT_QUOTATION' },
        'CONTRACT_UPLOADED': { 'Accounts': 'PARTIAL_PAYMENT_VERIFIED', 'Admin': 'PARTIAL_PAYMENT_VERIFIED' },
        'PARTIAL_PAYMENT_VERIFIED': { 'Admin': 'DOCUMENT_REVIEW' },
        # DOCUMENT_REVIEW: Initial Reviewer uploads/sends templates via dedicated routes.
        # If update-application-status is called for this status, it is a no-op for Initial reviewer
        # (handled below in role-specific block). Safety entry prevents 'No valid transition' error.
        'DOCUMENT_REVIEW': { 'Initial reviewer': 'CLIENT_DOCUMENT_SUBMISSION_PENDING' },
        'CLIENT_DOCUMENT_SUBMITTED': { 'Initial reviewer': 'INSPECTION_PLANNING' },
        'INSPECTION_PLANNING': { 'Inspection planner': 'AUDIT_IN_PROGRESS' },
        'AUDIT_IN_PROGRESS': { 'Auditor': 'TECHNICAL_REVIEW' },
        'TECHNICAL_REVIEW': { 'Technical reviewer': 'FINAL_PAYMENT_PENDING' },
        'FINAL_PAYMENT_SUBMITTED': { 'Accounts': 'FINAL_PAYMENT_VERIFIED', 'Admin': 'FINAL_PAYMENT_VERIFIED' },
        'FINAL_PAYMENT_PENDING': { 'Accounts': 'FINAL_PAYMENT_VERIFIED', 'Admin': 'FINAL_PAYMENT_VERIFIED' },
        'FINAL_PAYMENT_VERIFIED': { 'Certifier': 'CERTIFICATE_ISSUED', 'CEO': 'CERTIFICATE_ISSUED' }
    }
    
    current_status = request.form.get('current_status')
    new_status = request.form.get('status_override')
    action = request.form.get('action')
    comment = request.form.get('comment', '').strip()
    
    if action == 'reject':
        if not comment:
            flash('A comment is mandatory when rejecting an application.', 'error')
            return redirect(url_for('dashboard'))
        if role == 'Initial reviewer' and current_status == 'CLIENT_DOCUMENT_SUBMITTED':
            new_status = 'CLIENT_DOCUMENT_SUBMISSION_PENDING'
        else:
            new_status = 'REJECTED'
    elif not new_status:
        if current_status:
            new_status = transitions.get(current_status, {}).get(role)
        else:
            flash('Current status not provided.', 'error')
            return redirect(url_for('dashboard'))

    if not new_status:
        flash(f'No valid transition found for your role ({role}) and current status ({current_status}).', 'error')
        return redirect(url_for('dashboard'))
        
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Auditor specific logic: Must upload report if not rejecting
        if role == 'Auditor' and current_status == 'AUDIT_IN_PROGRESS' and action != 'reject':
            report_file = request.files.get('audit_report')
            if not report_file or report_file.filename == '':
                flash('Audit report is mandatory for submission.', 'error')
                return redirect(url_for('dashboard'))
            
            filename = secure_filename(f"audit_report_{app_id}_{report_file.filename}")
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            report_file.save(filepath)
            
            # Fetch client_id for document entry
            cursor.execute("SELECT client_id FROM applications WHERE id = %s", (app_id,))
            result = cursor.fetchone()
            client_id = result['client_id'] if result else None
            
            if client_id:
                cursor.execute(
                    "INSERT INTO documents (client_id, application_id, filename, filepath, category) VALUES (%s, %s, %s, %s, 'AUDIT_REPORT')",
                    (client_id, app_id, filename, filename)
                )

        # Initial Reviewer specific logic: Allocate project to auditor(s) and send FMO18
        # Triggered when client has submitted docs (CLIENT_DOCUMENT_SUBMITTED) and reviewer assigns auditors.
        elif role == 'Initial reviewer' and current_status == 'CLIENT_DOCUMENT_SUBMITTED' and action != 'reject':
            lead_auditor_id = request.form.get('lead_auditor_id')
            if not lead_auditor_id:
                flash('Assigning a Lead Auditor is mandatory.', 'error')
                return redirect(url_for('dashboard'))
            
            co_auditor_ids = request.form.getlist('co_auditor_ids')
            
            # Update lead_auditor_id in applications table
            cursor.execute("UPDATE applications SET lead_auditor_id = %s WHERE id = %s", (lead_auditor_id, app_id))
            
            # Clear existing co-auditors (if any) and insert new co-auditors
            cursor.execute("DELETE FROM application_auditors WHERE application_id = %s", (app_id,))
            cursor.execute("INSERT INTO application_auditors (application_id, auditor_id, role) VALUES (%s, %s, 'Lead')", (app_id, lead_auditor_id))
            
            for co_id in co_auditor_ids:
                if co_id and co_id != lead_auditor_id:
                    cursor.execute("INSERT INTO application_auditors (application_id, auditor_id, role) VALUES (%s, %s, 'Co-Auditor')", (app_id, co_id))
            
            # Fetch auditor details for sending the FMO18 letter
            cursor.execute("SELECT id, full_name, email FROM users WHERE id = %s", (lead_auditor_id,))
            lead_auditor = cursor.fetchone()
            
            co_auditors = []
            if co_auditor_ids:
                format_strings = ','.join(['%s'] * len(co_auditor_ids))
                cursor.execute(f"SELECT id, full_name, email FROM users WHERE id IN ({format_strings})", tuple(co_auditor_ids))
                co_auditors = cursor.fetchall()
            
            # Fetch application details
            cursor.execute("SELECT a.*, u.full_name as client_name FROM applications a JOIN users u ON a.client_id = u.id WHERE a.id = %s", (app_id,))
            app_details = cursor.fetchone()
            
            # Prepare and send FMO18 email
            recipients = []
            if lead_auditor and lead_auditor['email']:
                recipients.append(lead_auditor['email'])
            for co in co_auditors:
                if co['email'] and co['email'] not in recipients:
                    recipients.append(co['email'])
            
            if recipients:
                sender_name = session.get('full_name', 'Initial Reviewer')
                sender_email = session.get('email', 'Review@go4agri.co.in')
                
                co_names_str = ", ".join([co['full_name'] for co in co_auditors if co['id'] != lead_auditor['id']]) if co_auditors else "None"
                proj_code = app_details['project_code'] if app_details['project_code'] else f"PRG-{app_details['id']:04d}"
                
                # Format FMO18 Email Letter
                subject = f"FMO18: Audit Allocation Letter - Project {proj_code}"
                email_body = f"""FMO18 - AUDIT ALLOCATION LETTER

Date: {datetime.now().strftime('%d-%b-%Y')}
From: Go4Agri Initial Reviewer ({sender_name})
To: {", ".join([r for r in recipients])}

Subject: Audit Allocation for {app_details['company_name']}

Dear Auditor(s),

This is to inform you that you have been allocated for the certification audit of the following project:

Client Name: {app_details['company_name']}
Program/Scheme: {app_details['program_type']}
Project Code: {proj_code}
Application ID: {app_details['id']}

Role Allocation:
- Lead Auditor: {lead_auditor['full_name']}
- Co-Auditor(s): {co_names_str}

Please proceed with the audit planning and coordinate with the client. You are requested to submit the Audit Plan and ASR (Audit Summary Report) within the stipulated timelines.

If you have any conflicts of interest or questions regarding this allocation, please contact the Quality Department immediately.

Best regards,
{sender_name}
Initial Reviewer, Go4Agri
{sender_email}
"""
                msg = Message(
                    subject=subject,
                    recipients=recipients,
                    body=email_body,
                    reply_to=sender_email
                )
                Thread(target=send_async_email, args=(app, msg)).start()
                
                # Save copy of FMO18 Letter
                letter_filename = f"FMO18_Allocation_Letter_app{app_id}.txt"
                letter_filepath = os.path.join(app.config['UPLOAD_FOLDER'], letter_filename)
                with open(letter_filepath, 'w', encoding='utf-8') as f:
                    f.write(email_body)
                
                cursor.execute(
                    "INSERT INTO documents (client_id, application_id, filename, filepath, category) VALUES (%s, %s, %s, %s, 'AUDIT_ALLOCATION_LETTER')",
                    (app_details['client_id'], app_id, letter_filename, letter_filename)
                )
                
                flash('FMO18 Audit Allocation Letter sent successfully by email to assigned auditor(s) and logged.', 'success')

        # Inspection Planner specific logic: Must upload planning doc if not rejecting
        elif role == 'Inspection planner' and current_status == 'INSPECTION_PLANNING' and action != 'reject':
            plan_file = request.files.get('planning_doc')
            if not plan_file or plan_file.filename == '':
                flash('Planning document is mandatory for submission.', 'error')
                return redirect(url_for('dashboard'))
                
            audit_start_date = request.form.get('audit_start_date')
            audit_end_date = request.form.get('audit_end_date')
            if not audit_start_date or not audit_end_date:
                flash('Audit Start Date and Audit End Date are mandatory.', 'error')
                return redirect(url_for('dashboard'))
            
            filename = secure_filename(f"planning_doc_{app_id}_{plan_file.filename}")
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            plan_file.save(filepath)
            
            # Fetch client_id for document entry
            cursor.execute("SELECT client_id FROM applications WHERE id = %s", (app_id,))
            result = cursor.fetchone()
            client_id = result['client_id'] if result else None
            
            if client_id:
                cursor.execute(
                    "INSERT INTO documents (client_id, application_id, filename, filepath, category) VALUES (%s, %s, %s, %s, 'PLANNING_DOCUMENT')",
                    (client_id, app_id, filename, filename)
                )
                
            # Update application with audit dates
            cursor.execute("UPDATE applications SET audit_start_date = %s, audit_end_date = %s WHERE id = %s", (audit_start_date, audit_end_date, app_id))

        # Technical Reviewer specific logic: Upload FMO23a
        elif role == 'Technical reviewer' and current_status == 'TECHNICAL_REVIEW' and action != 'reject':
            cdr_file = request.files.get('fmo23a_doc')
            if not cdr_file or cdr_file.filename == '':
                flash('FMO23a (Certification Decision Record) is mandatory.', 'error')
                return redirect(url_for('dashboard'))
            
            filename = secure_filename(f"FMO23a_CDR_{app_id}_{cdr_file.filename}")
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            cdr_file.save(filepath)
            
            # Fetch client_id for document entry
            cursor.execute("SELECT client_id FROM applications WHERE id = %s", (app_id,))
            result = cursor.fetchone()
            client_id = result['client_id'] if result else None
            
            if client_id:
                cursor.execute(
                    "INSERT INTO documents (client_id, application_id, filename, filepath, category) VALUES (%s, %s, %s, %s, 'FMO23a_CDR_TECH_REVIEW')",
                    (client_id, app_id, filename, filename)
                )

        # Certifier specific logic: Upload FMO23a, select decision letter, upload and send
        elif role in ['Certifier', 'CEO'] and current_status == 'FINAL_PAYMENT_VERIFIED' and action != 'reject':
            cdr_file = request.files.get('fmo23a_doc')
            decision_type = request.form.get('decision_type')
            decision_letter = request.files.get('decision_letter')

            if not cdr_file or cdr_file.filename == '':
                flash('FMO23a (Certification Decision Record) is mandatory.', 'error')
                return redirect(url_for('dashboard'))
                
            if not decision_type or not decision_letter or decision_letter.filename == '':
                flash('A decision letter must be selected and uploaded.', 'error')
                return redirect(url_for('dashboard'))

            # Save FMO23a
            cdr_filename = secure_filename(f"FMO23a_CDR_{app_id}_{cdr_file.filename}")
            cdr_filepath = os.path.join(app.config['UPLOAD_FOLDER'], cdr_filename)
            cdr_file.save(cdr_filepath)

            # Save Decision Letter
            letter_filename = secure_filename(f"{decision_type}_{app_id}_{decision_letter.filename}")
            letter_filepath = os.path.join(app.config['UPLOAD_FOLDER'], letter_filename)
            decision_letter.save(letter_filepath)

            # Fetch client and app details
            cursor.execute("SELECT a.*, u.email as client_email, u.full_name as client_name, u.id as client_user_id FROM applications a JOIN users u ON a.client_id = u.id WHERE a.id = %s", (app_id,))
            app_details = cursor.fetchone()

            if app_details:
                client_id = app_details['client_user_id']
                cursor.execute(
                    "INSERT INTO documents (client_id, application_id, filename, filepath, category) VALUES (%s, %s, %s, %s, 'FMO23a_CDR_CERTIFIER')",
                    (client_id, app_id, cdr_filename, cdr_filename)
                )
                cursor.execute(
                    "INSERT INTO documents (client_id, application_id, filename, filepath, category) VALUES (%s, %s, %s, %s, %s)",
                    (client_id, app_id, letter_filename, letter_filename, f'DECISION_LETTER_{decision_type}')
                )

                # Send Email
                if app_details['client_email']:
                    sender_name = session.get('full_name', 'Certifier')
                    sender_email = session.get('email', 'Review@go4agri.co.in')
                    proj_code = app_details['project_code'] if app_details['project_code'] else f"PRG-{app_id:04d}"
                    
                    subject = f"Certification Decision: {decision_type} - Project {proj_code}"
                    email_body = f"""Dear {app_details['client_name']},

Please find attached the official certification decision letter ({decision_type}) regarding your application for Project {proj_code}.

If you have any questions, please contact our support team.

Best regards,
{sender_name}
Certifier, Go4Agri
"""
                    msg = Message(
                        subject=subject,
                        recipients=[app_details['client_email']],
                        body=email_body,
                        reply_to=sender_email
                    )
                    
                    # Attach the decision letter
                    with open(letter_filepath, 'rb') as fp:
                        msg.attach(letter_filename, 'application/octet-stream', fp.read())

                    Thread(target=send_async_email, args=(app, msg)).start()
                    flash(f'Decision letter ({decision_type}) sent to client successfully.', 'success')

        
        cursor.execute(
            "UPDATE applications SET status = %s WHERE id = %s",
            (new_status, app_id)
        )
        conn.commit()

        # Automated Notifications based on new_status
        notification_map = {
            'CLIENT_REGISTERED': ('Admin', 'New Client Registered', f'Application {app_id} is ready for contract generation.'),
            'CONTRACT_UPLOADED': ('Accounts', 'Contract Uploaded', f'New contract and payment receipt uploaded for application {app_id}.'),
            'PARTIAL_PAYMENT_VERIFIED': ('Admin', 'Payment Verified', f'Partial payment verified for application {app_id}. Ready for document review.'),
            'DOCUMENT_REVIEW': ('Initial reviewer', 'New Activity: Document Review', f'Application {app_id} assigned for document review.'),
            'CLIENT_DOCUMENT_SUBMISSION_PENDING': ('Client', 'Action Required: Review Templates Ready', f'Templates are ready for application {app_id}.'),
            'CLIENT_DOCUMENT_SUBMITTED': ('Initial reviewer', 'Review Documents Submitted', f'Client submitted review documents for application {app_id}.'),
            'INSPECTION_PLANNING': ('Inspection planner', 'New Activity: Inspection Planning', f'Application {app_id} assigned for inspection planning.'),
            'AUDIT_IN_PROGRESS': ('Auditor', 'New Activity: Audit Assigned', f'Application {app_id} is now assigned to you for inspection.'),
            'TECHNICAL_REVIEW': ('Technical reviewer', 'New Activity: Technical Review', f'Audit report submitted for application {app_id}. Technical review required.'),
            'FINAL_PAYMENT_PENDING': ('Accounts', 'Final Payment Pending', f'Technical review completed for app {app_id}. Awaiting final payment.'),
            'FINAL_PAYMENT_VERIFIED': ('Certifier', 'Payment Verified: Issue Certificate', f'Final payment verified for app {app_id}. Certificate can now be issued.'),
            'CERTIFICATE_ISSUED': ('CEO', 'Certificate Issued', f'Certificate has been issued for application {app_id}.')
        }

        if new_status in notification_map:
            dest_role, subject, body = notification_map[new_status]
            send_system_message(dest_role, subject, body)
            
        if action == 'reject':
            if role == 'Initial reviewer' and current_status == 'CLIENT_DOCUMENT_SUBMITTED':
                cursor.execute("SELECT client_id, company_name FROM applications WHERE id = %s", (app_id,))
                res = cursor.fetchone()
                if res:
                    c_id, comp_name = res['client_id'], res['company_name']
                    cursor.execute(
                        "INSERT INTO messages (sender_id, receiver_id, subject, body, is_read) "
                        "VALUES (%s, %s, %s, %s, 0)",
                        (session['user_id'], c_id,
                         f"Action Required: Document Review Corrections for App #{app_id}",
                         f"Dear client,\n\nYour submitted documents for application '{comp_name}' require corrections.\n\nReviewer Comments:\n{comment}\n\nPlease visit your dashboard, download the templates, and re-upload the corrected documents.")
                    )
            else:
                send_system_message('Admin', 'Application Rejected', f'Application {app_id} was rejected by {session.get("full_name")} ({role}). Reason: {comment}')

        cursor.close()
        conn.close()
        
        if action == 'reject':
            log_activity(session['user_id'], 'REJECT_APPLICATION', f"Rejected application {app_id}. Reason: {comment}")
            flash(f'Application rejected successfully.', 'success')
        else:
            log_activity(session['user_id'], 'UPDATE_STATUS', f"Advanced application {app_id} to {new_status}")
            flash(f'Application advanced to {new_status.replace("_", " ")}.', 'success')
            
    except Exception as e:
        print(f"Error updating status: {e}")
        flash('Error updating application status.', 'error')
        
    return redirect(request.referrer or url_for('dashboard'))

@app.route('/update-audit-details/<int:app_id>', methods=['POST'])
def update_audit_details(app_id):
    if 'user_id' not in session or session.get('designation') not in ['Admin', 'Auditor']:
        flash('Unauthorized access.', 'error')
        return redirect(url_for('dashboard'))
        
    plan_days = request.form.get('plan_days')
    asr_days = request.form.get('asr_days')
    start_date = request.form.get('start_date')
    end_date = request.form.get('end_date')
    
    # Handle empty strings for integer fields
    plan_days = plan_days if plan_days else 0
    asr_days = asr_days if asr_days else 0
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if start_date or end_date:
            cursor.execute("""
                UPDATE applications 
                SET plan_submission_days = %s, 
                    draft_asr_days = %s, 
                    audit_start_date = %s, 
                    audit_end_date = %s 
                WHERE id = %s
            """, (plan_days, asr_days, start_date or None, end_date or None, app_id))
        else:
            cursor.execute("""
                UPDATE applications 
                SET plan_submission_days = %s, 
                    draft_asr_days = %s
                WHERE id = %s
            """, (plan_days, asr_days, app_id))
            
        conn.commit()
        cursor.close()
        conn.close()
        log_activity(session['user_id'], 'UPDATE_AUDIT_DETAILS', f"Updated audit details for application {app_id}")
        flash('Audit details updated successfully.', 'success')
    except Exception as e:
        print(f"Error updating audit details: {e}")
        flash('Error updating audit details.', 'error')
        
    return redirect(request.referrer or url_for('dashboard'))

@app.route('/update-post-cert-status/<int:app_id>', methods=['POST'])
def update_post_cert_status(app_id):
    if 'user_id' not in session or session.get('designation') not in ['Admin', 'Certifier', 'CEO']:
        flash('Unauthorized access.', 'error')
        return redirect(url_for('dashboard'))

    post_cert_status = request.form.get('post_cert_status')
    if post_cert_status not in ['Active', 'Surrender', 'Withdraw', 'Suspended']:
        flash('Invalid post-certification status.', 'error')
        return redirect(url_for('dashboard'))

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE applications SET post_cert_status = %s WHERE id = %s", (post_cert_status, app_id))
        conn.commit()
        log_activity(session['user_id'], 'UPDATE_POST_CERT_STATUS', f"Updated post-certification status to {post_cert_status} for application {app_id}")
        flash(f'Post-certification status successfully updated to {post_cert_status}.', 'success')
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Error updating post cert status: {e}")
        flash('Error updating status.', 'error')

    return redirect(request.referrer or url_for('dashboard'))

@app.route('/submit-withdrawal/<int:app_id>', methods=['POST'])
def submit_withdrawal(app_id):
    if 'user_id' not in session or session.get('designation') != 'Client':
        flash('Unauthorized access.', 'error')
        return redirect(url_for('dashboard'))

    fmo17_doc = request.files.get('fmo17_doc')
    if not fmo17_doc or fmo17_doc.filename == '':
        flash('FMO17 Withdrawal Notification document is required.', 'error')
        return redirect(url_for('dashboard'))

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Verify ownership
        cursor.execute("SELECT id FROM applications WHERE id = %s AND client_id = %s", (app_id, session['user_id']))
        if not cursor.fetchone():
            flash('Unauthorized access.', 'error')
            return redirect(url_for('dashboard'))

        # Save file
        filename = secure_filename(f"FMO17_Withdrawal_{app_id}_{fmo17_doc.filename}")
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        fmo17_doc.save(filepath)

        # Save document to DB
        cursor.execute(
            "INSERT INTO documents (client_id, application_id, filename, filepath, category) VALUES (%s, %s, %s, %s, 'FMO17_WITHDRAWAL')",
            (session['user_id'], app_id, filename, filename)
        )
        
        conn.commit()
        log_activity(session['user_id'], 'SUBMIT_WITHDRAWAL', f"Uploaded FMO17 Withdrawal Notification for application {app_id}")
        flash('Withdrawal Notification (FMO17) submitted successfully.', 'success')
        
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Error submitting withdrawal: {e}")
        flash('Error processing Withdrawal Notification.', 'error')

    return redirect(url_for('dashboard'))

@app.route('/send-audit-plan/<int:app_id>', methods=['POST'])
def send_audit_plan(app_id):
    if 'user_id' not in session or session.get('designation') != 'Auditor':
        flash('Unauthorized access.', 'error')
        return redirect(url_for('dashboard'))

    fmo19_doc = request.files.get('fmo19_doc')
    if not fmo19_doc or fmo19_doc.filename == '':
        flash('Audit Plan (FMO19) document is required.', 'error')
        return redirect(url_for('dashboard'))

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Save file
        filename = secure_filename(f"FMO19_Audit_Plan_{app_id}_{fmo19_doc.filename}")
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        fmo19_doc.save(filepath)

        # Get client and app info
        cursor.execute("SELECT a.*, u.email as client_email, u.full_name as client_name, u.id as client_user_id FROM applications a JOIN users u ON a.client_id = u.id WHERE a.id = %s", (app_id,))
        app_details = cursor.fetchone()

        if app_details:
            client_id = app_details['client_user_id']
            # Save document to DB
            cursor.execute(
                "INSERT INTO documents (client_id, application_id, filename, filepath, category) VALUES (%s, %s, %s, %s, 'AUDIT_PLAN_FMO19')",
                (client_id, app_id, filename, filename)
            )
            
            # Send Email
            if app_details['client_email']:
                sender_name = session.get('full_name', 'Auditor')
                sender_email = session.get('email', 'Review@go4agri.co.in')
                proj_code = app_details['project_code'] if app_details['project_code'] else f"PRG-{app_id:04d}"
                subject = f"FMO19: Audit Plan - Project {proj_code}"
                email_body = f"""Dear {app_details['client_name']},

Please find attached the Audit Plan (FMO19) for your certification audit for Project {proj_code}.

Please review the plan and make the necessary arrangements. If you have any questions, feel free to contact us.

Best regards,
{sender_name}
Lead Auditor, Go4Agri
"""
                msg = Message(
                    subject=subject,
                    recipients=[app_details['client_email']],
                    body=email_body,
                    reply_to=sender_email
                )
                
                # Attach file
                with open(filepath, 'rb') as fp:
                    msg.attach(filename, 'application/octet-stream', fp.read())

                Thread(target=send_async_email, args=(app, msg)).start()
            
            conn.commit()
            log_activity(session['user_id'], 'UPLOAD_AUDIT_PLAN', f"Uploaded and sent Audit Plan (FMO19) for application {app_id}")
            flash('Audit Plan (FMO19) uploaded and sent to client successfully.', 'success')
            
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Error sending audit plan: {e}")
        flash('Error processing Audit Plan.', 'error')

    return redirect(url_for('dashboard'))

@app.route('/register-client', methods=['POST'])
def register_client():
    if 'user_id' not in session or session.get('designation') not in ['CEO', 'Admin']:
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
        existing_user = cursor.fetchone()
        
        if existing_user is None:
            year = datetime.now().year
            client_code = generate_client_code(cursor, year)
            cursor.execute(
                "INSERT INTO users (full_name, email, designation, password, client_code) VALUES (%s, %s, %s, %s, %s)",
                (full_name, email, 'Client', hashed_pw, client_code)
            )
            client_id = cursor.lastrowid
            flash_msg = f'Successfully registered client {full_name} ({client_code}).'
            
            # Send email to the new client
            try:
                msg = Message('Welcome to Go4Agri - Your Credentials', recipients=[email])
                msg.body = f"""Hello {full_name},
 
Welcome to Go4Agri! Your client account has been successfully created by our administrator.
 
Here are your login credentials:
Login URL: {url_for('client_login', _external=True)}
Email: {email}
Password: {password}
 
NEXT STEPS TO GET STARTED:
1. Log in to your dashboard: {url_for('client_login', _external=True)}
2. Review the 'Company Bank Details' and 'Registration Steps' on your dashboard.
3. Download the 'Standard Contract Template'.
4. Print, sign, and scan the contract.
5. Complete the partial payment as mentioned in the registration steps.
6. Upload the signed contract, payment receipt and related documents in the Application Tracker.
 
Once these steps are completed, our team will review your application and proceed with the next stages of certification.
 
If you encounter any issues logging in or have any questions, please feel free to reply to this email or contact our support team.
 
Best regards,
The Go4Agri Team"""
                try:
                    Thread(target=send_async_email, args=(app, msg)).start()
                except Exception as e:
                    print(f"Failed to start async email thread: {e}")
 
                flash_msg += ' An email with login credentials and next steps has been sent.'
            except Exception as e:
                print(f"Failed to send email: {e}")
                flash_msg += ' (Warning: Failed to send email with credentials).'
        else:
            client_id = existing_user[0]
            cursor.execute("SELECT client_code FROM users WHERE id = %s", (client_id,))
            cc_row = cursor.fetchone()
            if cc_row and cc_row[0]:
                client_code = cc_row[0]
            else:
                year = datetime.now().year
                client_code = generate_client_code(cursor, year)
                cursor.execute("UPDATE users SET client_code = %s WHERE id = %s", (client_code, client_id))
                conn.commit()
            flash_msg = f'User with email {email} already exists. Enquiry linked to existing account.'
            
        if enquiry_id:
            cursor.execute("SELECT company_name, program_type FROM enquiries WHERE id = %s", (enquiry_id,))
            enq = cursor.fetchone()
            if enq:
                company_name, program_type = enq
                cursor.execute("SELECT id FROM applications WHERE client_id = %s AND program_type = %s", (client_id, program_type))
                if cursor.fetchone() is None:
                    project_code = generate_project_code(cursor, client_id, client_code)
                    cursor.execute(
                        "INSERT INTO applications (client_id, company_name, program_type, status, project_code) VALUES (%s, %s, %s, 'APPLICATION_RECEIVED', %s)",
                        (client_id, company_name, program_type, project_code)
                    )
                else:
                    flash_msg += ' (Warning: Application for this program already exists).'
                    
            cursor.execute("UPDATE enquiries SET status = 'REGISTERED' WHERE id = %s", (enquiry_id,))
            
        conn.commit()
        log_activity(session['user_id'], 'REGISTER_CLIENT', f"Registered/Linked client {full_name} ({email})")
        flash(flash_msg, 'success')
            
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Registration error: {e}")
        flash(f'Error registering client: {str(e)}', 'error')
        
    return redirect(url_for('dashboard'))

@app.route('/delete-enquiry/<int:enquiry_id>', methods=['POST'])
def delete_enquiry(enquiry_id):
    if 'user_id' not in session or session.get('designation') not in ['CEO', 'Admin']:
        flash('Unauthorized access.', 'error')
        return redirect(url_for('home'))
        
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE enquiries SET status = 'DELETED' WHERE id = %s", (enquiry_id,))
        conn.commit()
        cursor.close()
        conn.close()
        log_activity(session['user_id'], 'DELETE_ENQUIRY', f"Deleted enquiry {enquiry_id}")
        flash('Enquiry marked as deleted.', 'success')
    except Exception as e:
        print(f"Error deleting enquiry: {e}")
        flash('Error deleting enquiry.', 'error')
        
    return redirect(url_for('dashboard'))

@app.route('/restore-enquiry/<int:enquiry_id>', methods=['POST'])
def restore_enquiry(enquiry_id):
    if 'user_id' not in session or session.get('designation') not in ['CEO', 'Admin']:
        flash('Unauthorized access.', 'error')
        return redirect(url_for('home'))
        
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE enquiries SET status = 'NEW' WHERE id = %s", (enquiry_id,))
        conn.commit()
        cursor.close()
        conn.close()
        log_activity(session['user_id'], 'RESTORE_ENQUIRY', f"Restored enquiry {enquiry_id}")
        flash('Enquiry restored successfully.', 'success')
    except Exception as e:
        print(f"Error restoring enquiry: {e}")
        flash('Error restoring enquiry.', 'error')
        
    return redirect(url_for('dashboard'))

@app.route('/delete-application/<int:app_id>', methods=['POST'])
def delete_application(app_id):
    if 'user_id' not in session:
        flash('Unauthorized access.', 'error')
        return redirect(url_for('home'))
    if session.get('designation') == 'Client':
        flash('Unauthorized access.', 'error')
        return redirect(url_for('home'))
        
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE applications SET current_status = 'Deleted' WHERE id = %s", (app_id,))
        conn.commit()
        cursor.close()
        conn.close()
        log_activity(session['user_id'], 'DELETE_APPLICATION', f"Deleted application {app_id}")
        flash('Application marked as deleted.', 'success')
    except Exception as e:
        print(f"Error deleting application: {e}")
        flash('Error deleting application.', 'error')
        
    return redirect(url_for('dashboard'))

@app.route('/archive-application/<int:app_id>', methods=['POST'])
def archive_application(app_id):
    if 'user_id' not in session:
        flash('Unauthorized access.', 'error')
        return redirect(url_for('home'))
    if session.get('designation') == 'Client':
        flash('Unauthorized access.', 'error')
        return redirect(url_for('home'))

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE applications SET current_status = 'Archived' WHERE id = %s", (app_id,))
        conn.commit()
        cursor.close()
        conn.close()
        log_activity(session['user_id'], 'ARCHIVE_APPLICATION', f"Archived application {app_id}")
        flash('Application archived successfully.', 'success')
    except Exception as e:
        print(f"Error archiving application: {e}")
        flash('Error archiving application.', 'error')

    return redirect(url_for('dashboard'))


@app.route('/restore-application/<int:app_id>', methods=['POST'])
def restore_application(app_id):
    if 'user_id' not in session:
        flash('Unauthorized access.', 'error')
        return redirect(url_for('home'))
    if session.get('designation') == 'Client':
        flash('Unauthorized access.', 'error')
        return redirect(url_for('home'))

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE applications SET current_status = NULL WHERE id = %s", (app_id,))
        conn.commit()
        cursor.close()
        conn.close()
        log_activity(session['user_id'], 'RESTORE_APPLICATION', f"Restored application #{app_id} from archive")
        flash('Application restored to history successfully.', 'success')
    except Exception as e:
        print(f"Error restoring application: {e}")
        flash('Error restoring application.', 'error')

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
    due_date = request.form.get('due_date')
    
    if not assignee_id or not title:
        flash('Please fill required fields.', 'error')
        return redirect(url_for('dashboard'))
        
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO tasks (allotter_id, assignee_id, application_id, due_date, title, description, priority) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (session['user_id'], assignee_id, application_id, due_date if due_date else None, title, description, priority)
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

@app.route('/api/calendar-events')
def calendar_events():
    if 'user_id' not in session:
        return jsonify([])
        
    user_id = session['user_id']
    designation = session.get('designation')
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        if designation == 'CEO':
            cursor.execute("SELECT t.*, u.full_name as assignee_name FROM tasks t JOIN users u ON t.assignee_id = u.id")
        elif designation == 'Admin':
            cursor.execute("SELECT t.*, u.full_name as assignee_name FROM tasks t JOIN users u ON t.assignee_id = u.id")
        else:
            cursor.execute("SELECT t.*, u.full_name as assignee_name FROM tasks t JOIN users u ON t.assignee_id = u.id WHERE t.assignee_id = %s", (user_id,))
            
        tasks = cursor.fetchall()
        cursor.close()
        conn.close()
        
        events = []
        for task in tasks:
            start_date = task['due_date']
            if not start_date and task['created_at']:
                if isinstance(task['created_at'], datetime):
                    start_date = task['created_at'].date()
                else:
                    start_date = task['created_at']
            if start_date:
                color = '#0072bc' # default info
                if task['status'] == 'COMPLETED':
                    color = '#27ae60' # success
                elif task['priority'] == 'HIGH':
                    color = '#e74c3c' # danger
                elif task['priority'] == 'MEDIUM':
                    color = '#f39c12' # warning
                    
                start_date_str = start_date.strftime('%Y-%m-%d') if hasattr(start_date, 'strftime') else str(start_date)
                events.append({
                    'id': str(task['id']),
                    'title': task['title'] if designation in ['CEO', 'Admin'] else task['title'],
                    'start': start_date_str,
                    'description': task['description'],
                    'color': color,
                    'extendedProps': {
                        'status': task['status'],
                        'priority': task['priority'],
                        'assignee': task.get('assignee_name', '')
                    }
                })
        return jsonify(events)
    except Exception as e:
        print(f"Error fetching calendar events: {e}")
        return jsonify([])


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
    active_tab = request.args.get('tab', 'inbox')
    
    msgs = []
    selected_msg = None
    contacts = []
    repo_file = None
    repo_file_id = request.args.get('repo_file_id')
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Fetch messages based on active tab
        if active_tab == 'sent':
            cursor.execute("""
                SELECT m.*, receiver.full_name as receiver_name
                FROM messages m
                JOIN users receiver ON m.receiver_id = receiver.id
                WHERE m.sender_id = %s AND m.deleted_by_sender = FALSE
                ORDER BY m.created_at DESC
            """, (user_id,))
        else: # Default to inbox
            cursor.execute("""
                SELECT m.*, sender.full_name as sender_name
                FROM messages m
                JOIN users sender ON m.sender_id = sender.id
                WHERE m.receiver_id = %s AND m.deleted_by_receiver = FALSE
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
                
        # Fetch contacts (all employees, and clients if CEO/Admin/Recruiter)
        if session['designation'] in ['CEO', 'Admin', 'Recruiter']:
            cursor.execute("SELECT id, full_name, designation FROM users WHERE id != %s", (user_id,))
        else:
            cursor.execute("SELECT id, full_name, designation FROM users WHERE designation != 'Client' AND id != %s", (user_id,))
        contacts = cursor.fetchall()
        
        # Fetch repo file if requested
        if repo_file_id and session['designation'] == 'CEO':
            cursor.execute("SELECT * FROM ceo_repository WHERE id = %s", (repo_file_id,))
            repo_file = cursor.fetchone()
        
        employee_repo_file_id = request.args.get('employee_repo_file_id')
        if employee_repo_file_id:
            cursor.execute("SELECT * FROM employee_repository WHERE id = %s AND user_id = %s", (employee_repo_file_id, user_id))
            repo_file = cursor.fetchone()
            
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Error fetching messages: {e}")
        
    return render_template('db_messages.html', user=session, messages=msgs, selected_message=selected_msg, contacts=contacts, active_tab=active_tab, repo_file=repo_file)

@app.route('/delete-message/<int:message_id>', methods=['POST'])
def delete_message(message_id):
    if 'user_id' not in session:
        return redirect(url_for('home'))
        
    user_id = session['user_id']
    active_tab = request.form.get('tab', 'inbox')
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if active_tab == 'inbox':
            cursor.execute("UPDATE messages SET deleted_by_receiver = TRUE WHERE id = %s AND receiver_id = %s", (message_id, user_id))
        else:
            cursor.execute("UPDATE messages SET deleted_by_sender = TRUE WHERE id = %s AND sender_id = %s", (message_id, user_id))
            
        conn.commit()
        cursor.close()
        conn.close()
        flash('Message deleted.', 'success')
    except Exception as e:
        print(f"Error deleting message: {e}")
        flash('Failed to delete message.', 'error')
        
    return redirect(url_for('messages', tab=active_tab))

@app.route('/delete-messages-bulk', methods=['POST'])
def delete_messages_bulk():
    if 'user_id' not in session:
        return redirect(url_for('home'))
        
    user_id = session['user_id']
    active_tab = request.form.get('tab', 'inbox')
    message_ids = request.form.getlist('message_ids')
    
    if not message_ids:
        flash('No messages selected.', 'warning')
        return redirect(url_for('messages', tab=active_tab))
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        for mid in message_ids:
            try:
                mid = int(mid)
                if active_tab == 'inbox':
                    cursor.execute("UPDATE messages SET deleted_by_receiver = TRUE WHERE id = %s AND receiver_id = %s", (mid, user_id))
                else:
                    cursor.execute("UPDATE messages SET deleted_by_sender = TRUE WHERE id = %s AND sender_id = %s", (mid, user_id))
            except ValueError:
                continue
                
        conn.commit()
        cursor.close()
        conn.close()
        flash(f'{len(message_ids)} message(s) deleted.', 'success')
    except Exception as e:
        print(f"Error bulk deleting messages: {e}")
        flash('Failed to delete messages.', 'error')
        
    return redirect(url_for('messages', tab=active_tab))

@app.route('/send-message', methods=['POST'])
def send_message():
    if 'user_id' not in session:
        return redirect(url_for('home'))
        
    # Handle multiple receiver IDs
    receiver_ids = request.form.getlist('receiver_ids')
    if not receiver_ids:
        # Fallback for single select
        single_id = request.form.get('receiver_id')
        if single_id:
            receiver_ids = [single_id]
            
    subject = request.form.get('subject')
    body = request.form.get('body')
    
    # Handle attachment
    attachment = request.files.get('attachment')
    attachment_filename = None
    attachment_path = None
    
    if attachment and attachment.filename != '':
        from werkzeug.utils import secure_filename
        from datetime import datetime
        import os
        filename = secure_filename(attachment.filename)
        timestamp_filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_msg_{filename}"
        
        if not os.path.exists(app.config['UPLOAD_FOLDER']):
            os.makedirs(app.config['UPLOAD_FOLDER'])
            
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], timestamp_filename)
        attachment.save(filepath)
        
        attachment_filename = filename
        attachment_path = timestamp_filename

    # Handle repo file attachment shortcut
    repo_file_id = request.form.get('repo_file_id')
    if repo_file_id and session.get('designation') == 'CEO':
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT filename, filepath FROM ceo_repository WHERE id = %s", (repo_file_id,))
            repo_file = cursor.fetchone()
            if repo_file:
                attachment_filename = repo_file['filename']
                attachment_path = repo_file['filepath']
            cursor.close()
            conn.close()
        except Exception as e:
            print(f"Error attaching CEO repo file: {e}")
            
    # Handle employee repo file attachment shortcut
    employee_repo_file_id = request.form.get('employee_repo_file_id')
    if employee_repo_file_id:
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT filename, filepath FROM employee_repository WHERE id = %s AND user_id = %s", 
                           (employee_repo_file_id, session['user_id']))
            repo_file = cursor.fetchone()
            if repo_file:
                attachment_filename = repo_file['filename']
                attachment_path = repo_file['filepath']
            cursor.close()
            conn.close()
        except Exception as e:
            print(f"Error attaching employee repo file: {e}")
        except Exception as e:
            print(f"Error attaching repo file: {e}")
    
    if not receiver_ids:
        flash('Please select at least one recipient.', 'error')
        return redirect(url_for('messages'))
        
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        msg_ids = []
        for r_id in receiver_ids:
            if r_id.strip():
                cursor.execute(
                    "INSERT INTO messages (sender_id, receiver_id, subject, body, attachment_filename, attachment_path) VALUES (%s, %s, %s, %s, %s, %s)",
                    (session['user_id'], r_id, subject, body, attachment_filename, attachment_path)
                )
                msg_ids.append(cursor.lastrowid)
        
        # Save to repository if requested
        if request.form.get('save_to_repo') == 'on' and attachment_path:
            cursor.execute(
                "INSERT INTO employee_repository (user_id, filename, filepath, original_message_id) VALUES (%s, %s, %s, %s)",
                (session['user_id'], attachment_filename, attachment_path, msg_ids[0] if msg_ids else None)
            )
            
        conn.commit()
        cursor.close()
        conn.close()
        flash('Message(s) sent successfully!', 'success')
    except Exception as e:
        print(f"Error sending message: {e}")
        flash('Error sending message.', 'error')
        
    return redirect(url_for('messages'))

@app.route('/download-message-attachment/<int:msg_id>')
def download_message_attachment(msg_id):
    if 'user_id' not in session:
        return redirect(url_for('home'))
        
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        # Check permissions
        cursor.execute("SELECT * FROM messages WHERE id = %s AND (sender_id = %s OR receiver_id = %s)", 
                       (msg_id, session['user_id'], session['user_id']))
        msg = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if msg and msg.get('attachment_path'):
            import os
            from flask import send_from_directory
            return send_from_directory(app.config['UPLOAD_FOLDER'], msg['attachment_path'], as_attachment=True, download_name=msg['attachment_filename'])
        else:
            flash('Attachment not found.', 'error')
            return redirect(url_for('messages'))
    except Exception as e:
        print(f"Error downloading attachment: {e}")
        flash('Error downloading attachment.', 'error')
        return redirect(url_for('messages'))

@app.route('/ceo-repository', methods=['GET', 'POST'])
def ceo_repository():
    if 'user_id' not in session or session.get('designation') != 'CEO':
        flash('Unauthorized access.', 'error')
        return redirect(url_for('home'))
        
    if request.method == 'POST':
        file = request.files.get('file')
        if not file or file.filename == '':
            flash('No file selected.', 'error')
            return redirect(url_for('ceo_repository'))
            
        try:
            from werkzeug.utils import secure_filename
            from datetime import datetime
            import os
            
            filename = secure_filename(file.filename)
            timestamp_filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_repo_{filename}"
            
            if not os.path.exists(app.config['UPLOAD_FOLDER']):
                os.makedirs(app.config['UPLOAD_FOLDER'])
                
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], timestamp_filename)
            file.save(filepath)
            
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO ceo_repository (filename, filepath) VALUES (%s, %s)",
                (filename, timestamp_filename)
            )
            conn.commit()
            cursor.close()
            conn.close()
            flash('File uploaded successfully!', 'success')
        except Exception as e:
            print(f"Error uploading repo file: {e}")
            flash('Error uploading file.', 'error')
            
        return redirect(url_for('ceo_repository'))
        
    # GET request
    files = []
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM ceo_repository ORDER BY uploaded_at DESC")
        files = cursor.fetchall()
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Error fetching repo files: {e}")
        
    return render_template('db_ceo_repository.html', user=session, files=files)

@app.route('/delete-ceo-repo/<int:file_id>', methods=['POST'])
def delete_ceo_repo(file_id):
    if 'user_id' not in session or session.get('designation') != 'CEO':
        flash('Unauthorized access.', 'error')
        return redirect(url_for('home'))
        
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM ceo_repository WHERE id = %s", (file_id,))
        file = cursor.fetchone()
        
        if file:
            import os
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], file['filepath'])
            if os.path.exists(filepath):
                os.remove(filepath)
                
            cursor.execute("DELETE FROM ceo_repository WHERE id = %s", (file_id,))
            conn.commit()
            flash('File deleted successfully.', 'success')
        else:
            flash('File not found.', 'error')
            
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Error deleting repo file: {e}")
        flash('Error deleting file.', 'error')
        
    return redirect(url_for('ceo_repository'))

@app.route('/download-ceo-repo/<int:file_id>')
def download_ceo_repo(file_id):
    if 'user_id' not in session or session.get('designation') != 'CEO':
        flash('Unauthorized access.', 'error')
        return redirect(url_for('home'))
        
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM ceo_repository WHERE id = %s", (file_id,))
        file = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if file:
            import os
            from flask import send_from_directory
            return send_from_directory(app.config['UPLOAD_FOLDER'], file['filepath'], as_attachment=True, download_name=file['filename'])
        else:
            flash('File not found.', 'error')
            return redirect(url_for('ceo_repository'))
    except Exception as e:
        print(f"Error downloading repo file: {e}")
        flash('Error downloading file.', 'error')
        return redirect(url_for('ceo_repository'))

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
    profile_picture = request.files.get('profile_picture')
    
    if new_password and new_password != confirm_password:
        flash('Passwords do not match.', 'error')
        return redirect(url_for('settings'))
        
    new_pic_filename = None
    if profile_picture and profile_picture.filename != '':
        from werkzeug.utils import secure_filename
        from datetime import datetime
        import os
        filename = secure_filename(f"profile_{session['user_id']}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{profile_picture.filename}")
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        profile_picture.save(filepath)
        new_pic_filename = filename
        
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if profile_picture column exists, if not, add it
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN profile_picture VARCHAR(255) DEFAULT NULL")
            conn.commit()
        except:
            pass # Column likely already exists
            
        if new_password:
            hashed_pw = generate_password_hash(new_password)
            if new_pic_filename:
                cursor.execute("UPDATE users SET full_name = %s, password = %s, profile_picture = %s WHERE id = %s", (full_name, hashed_pw, new_pic_filename, session['user_id']))
            else:
                cursor.execute("UPDATE users SET full_name = %s, password = %s WHERE id = %s", (full_name, hashed_pw, session['user_id']))
        else:
            if new_pic_filename:
                cursor.execute("UPDATE users SET full_name = %s, profile_picture = %s WHERE id = %s", (full_name, new_pic_filename, session['user_id']))
            else:
                cursor.execute("UPDATE users SET full_name = %s WHERE id = %s", (full_name, session['user_id']))
            
        conn.commit()
        cursor.close()
        conn.close()
        
        session['full_name'] = full_name
        if new_pic_filename:
            session['profile_picture'] = new_pic_filename
            
        log_activity(session['user_id'], 'UPDATE_SETTINGS', "Updated profile/password")
        flash('Settings updated successfully!', 'success')
    except Exception as e:
        print(f"Error updating settings: {e}")
        flash('Error updating settings.', 'error')
        
    return redirect(url_for('settings'))

@app.route('/submit-job-application', methods=['POST'])
def submit_job_application():
    name = request.form.get('full_name')
    email = request.form.get('email')
    phone = request.form.get('phone')
    position = request.form.get('position')
    resume_file = request.files.get('resume')
    
    if not name or not email or not phone or not position or not resume_file:
        flash('Please fill all fields and upload your resume.', 'error')
        return redirect(url_for('careers'))
        
    try:
        # Save resume with a unique name
        filename = secure_filename(f"resume_{datetime.now().strftime('%Y%m%d%H%M%S')}_{resume_file.filename}")
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        resume_file.save(filepath)
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Find HR users to notify (instead of apply send new job application to HR)
        cursor.execute("SELECT id FROM users WHERE designation = 'HR'")
        hr_users = cursor.fetchall()
        targets = [user['id'] for user in hr_users] if hr_users else [32]
        
        system_user_id = 1
        subject = f"New Job Application: {position} - {name}"
        body = f"""New job application received via careers page.

Name: {name}
Email: {email}
Phone: {phone}
Position: {position}
Submitted: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

You can download the resume here:
{url_for('download_resume', filename=filename, _external=True)}
"""
        
        # Insert into job_applications table
        cursor.execute(
            "INSERT INTO job_applications (full_name, email, phone, position, resume_path) VALUES (%s, %s, %s, %s, %s)",
            (name, email, phone, position, filename)
        )
        
        # Send message to HR
        for target_id in targets:
            cursor.execute(
                "INSERT INTO messages (sender_id, receiver_id, subject, body) VALUES (%s, %s, %s, %s)",
                (system_user_id, target_id, subject, body)
            )
        
        conn.commit()
        cursor.close()
        conn.close()
        
        log_activity(None, 'JOB_APPLICATION', f"New job application from {name} for {position}")
        flash('Your application has been submitted successfully! Our team will review it and get back to you.', 'success')
        return redirect(url_for('careers'))
        
    except Exception as e:
        print(f"Error submitting job application: {e}")
        flash('An error occurred while submitting your application. Please try again later.', 'error')
        return redirect(url_for('careers'))

@app.route('/download-resume/<filename>')
def download_resume(filename):
    if 'user_id' not in session or session.get('designation') == 'Client':
        flash('Unauthorized access.', 'error')
        return redirect(url_for('home'))
        
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=True)
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

    categories = request.form.getlist('category')
    app_ids = request.form.getlist('application_id')
    files = request.files.getlist('document_file')
    
    if not files or all(f.filename == '' for f in files):
        flash('No files selected for upload.', 'error')
        return redirect(url_for('upload_document'))
        
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        success_count = 0
        from datetime import datetime
        
        for i, file in enumerate(files):
            if file and file.filename != '':
                filename = secure_filename(file.filename)
                # Ensure the category matches the specific file if staged, else fallback to the single submitted category
                current_category = categories[i] if i < len(categories) else (categories[0] if categories else 'Other')
                
                current_app_id = app_ids[i] if i < len(app_ids) else (app_ids[0] if app_ids else None)
                if current_app_id == '':
                    current_app_id = None
                    
                # Add timestamp to filename to prevent overwrites, add unique index to prevent fast upload collisions
                ts_filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{success_count}_{filename}"
                
                # Ensure upload folder exists
                if not os.path.exists(app.config['UPLOAD_FOLDER']):
                    os.makedirs(app.config['UPLOAD_FOLDER'])
                    
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], ts_filename)
                file.save(filepath)
                
                cursor.execute(
                    "INSERT INTO documents (client_id, application_id, category, filename, filepath) VALUES (%s, %s, %s, %s, %s)",
                    (session['user_id'], current_app_id, current_category, filename, ts_filename)
                )
                success_count += 1
                log_activity(session['user_id'], 'UPLOAD_DOC', f"Uploaded {current_category}: {filename}")

        conn.commit()
        cursor.close()
        conn.close()
        
        if success_count > 1:
            flash(f'{success_count} documents uploaded successfully!', 'success')
        elif success_count == 1:
            flash('1 document uploaded successfully!', 'success')
        else:
            flash('No valid documents found to upload.', 'error')
            
        return redirect(url_for('dashboard'))
    except Exception as e:
        print(f"CRITICAL: Upload error in app.py: {e}")
        import traceback
        traceback.print_exc()
        flash(f'Error saving documents: {str(e)}', 'error')
        return redirect(url_for('upload_document'))

@app.route('/client-details/<int:client_id>')
def client_details(client_id):
    if 'user_id' not in session:
        flash('Unauthorized access.', 'error')
        return redirect(url_for('home'))
    if session.get('designation') == 'Client':
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
        cursor.execute("""
            SELECT a.*, u.full_name as lead_auditor_name, ep.job_description as auditor_job_description,
                   ep.assigned_role as auditor_assigned_role, ep.assigned_scheme as auditor_assigned_scheme,
                   client_user.full_name AS auditor_assigned_client_name
            FROM applications a
            LEFT JOIN users u ON a.lead_auditor_id = u.id
            LEFT JOIN employee_profiles ep ON u.id = ep.user_id
            LEFT JOIN users client_user ON ep.assigned_client_id = client_user.id
            WHERE a.client_id = %s 
            ORDER BY a.created_at DESC
        """, (client_id,))
        apps = cursor.fetchall()
        for app_row in apps:
            cursor.execute("""
                SELECT u.full_name, aa.role 
                FROM application_auditors aa
                JOIN users u ON aa.auditor_id = u.id
                WHERE aa.application_id = %s
            """, (app_row['id'],))
            app_row['auditor_team'] = cursor.fetchall()
        
        # Get client documents
        cursor.execute("SELECT * FROM documents WHERE client_id = %s ORDER BY uploaded_at DESC", (client_id,))
        docs = cursor.fetchall()
        
        # Get employees assigned to this client via QM Verification
        cursor.execute("""
            SELECT u.id as employee_id, u.full_name as employee_name, ep.assigned_role, ep.assigned_scheme
            FROM employee_profiles ep
            JOIN users u ON ep.user_id = u.id
            WHERE ep.assigned_client_id = %s
        """, (client_id,))
        assigned_staff = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return render_template('db_client_details.html', user=session, client=client_user, applications=apps, documents=docs, assigned_staff=assigned_staff)
    except Exception as e:
        print(f"Error fetching client details: {e}")
        flash('Error loading client details.', 'error')
        return redirect(url_for('dashboard'))

@app.route('/application-documents/<int:app_id>')
def application_documents(app_id):
    if 'user_id' not in session:
        return redirect(url_for('home'))
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        # Fetch the application - clients can only see their own
        cursor.execute("SELECT * FROM applications WHERE id = %s", (app_id,))
        application = cursor.fetchone()
        if not application:
            flash('Application not found.', 'error')
            return redirect(url_for('dashboard'))
        # Clients can only view their own application documents
        if session.get('designation') == 'Client' and application['client_id'] != session['user_id']:
            flash('Unauthorized access.', 'error')
            return redirect(url_for('dashboard'))
        # Fetch all documents for this application
        cursor.execute(
            "SELECT * FROM documents WHERE application_id = %s ORDER BY uploaded_at DESC",
            (app_id,)
        )
        docs = cursor.fetchall()
        cursor.close()
        conn.close()
        return render_template('application_documents.html', user=session, application=application, documents=docs)
    except Exception as e:
        print(f"Error fetching application documents: {e}")
        flash('Error loading documents.', 'error')
        return redirect(url_for('dashboard'))

@app.route('/delete-document/<int:doc_id>', methods=['POST'])
def delete_document(doc_id):
    if 'user_id' not in session or session.get('designation') != 'Client':
        flash('Unauthorized access.', 'error')
        return redirect(url_for('dashboard'))
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        # Fetch the document and verify ownership
        cursor.execute("SELECT * FROM documents WHERE id = %s AND client_id = %s", (doc_id, session['user_id']))
        doc = cursor.fetchone()
        if not doc:
            flash('Document not found or you do not have permission to delete it.', 'error')
            cursor.close()
            conn.close()
            return redirect(url_for('dashboard'))
        # Do not allow deletion if the application is completed
        if doc.get('application_id'):
            cursor.execute("SELECT status FROM applications WHERE id = %s", (doc['application_id'],))
            app_row = cursor.fetchone()
            if app_row and app_row['status'] == 'CERTIFICATE_ISSUED':
                flash('Documents for completed applications cannot be deleted.', 'error')
                cursor.close()
                conn.close()
                return redirect(f"/application-documents/{doc['application_id']}")
        # Delete from database
        app_id = doc.get('application_id')
        cursor.execute("DELETE FROM documents WHERE id = %s", (doc_id,))
        conn.commit()
        # Try to delete file from disk
        try:
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], doc['filepath'])
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception as file_err:
            print(f"Warning: Could not delete file from disk: {file_err}")
        cursor.close()
        conn.close()
        log_activity(session['user_id'], 'DELETE_DOCUMENT', f"Deleted document {doc['filename']} (ID: {doc_id})")
        flash(f'Document "{doc["filename"]}" has been deleted.', 'success')
        if app_id:
            return redirect(f'/application-documents/{app_id}')
        return redirect(url_for('dashboard'))
    except Exception as e:
        print(f"Error deleting document: {e}")
        flash('Error deleting document.', 'error')
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
            
        # Check permissions
        allowed_roles = ['CEO', 'Admin', 'QA', 'Initial reviewer', 'Inspection planner', 'Auditor', 'Technical reviewer', 'Certifier']
        is_employee = session.get('designation') in allowed_roles
        
        if session['designation'] == 'Client' and doc['client_id'] != session['user_id']:
            flash('Unauthorized access.', 'error')
            return redirect(url_for('dashboard'))
        elif session['designation'] != 'Client' and not is_employee:
            flash('Unauthorized access.', 'error')
            return redirect(url_for('dashboard'))
            
        return send_from_directory(app.config['UPLOAD_FOLDER'], doc['filepath'], as_attachment=True, download_name=doc['filename'])
    except Exception as e:
        print(f"Download error: {e}")
        flash('Error downloading document.', 'error')
        return redirect(url_for('dashboard'))

@app.route('/download-all-documents/<int:client_id>')
def download_all_documents(client_id):
    allowed_roles = ['CEO', 'Admin', 'QA', 'Initial reviewer', 'Inspection planner', 'Auditor', 'Technical reviewer', 'Certifier']
    if 'user_id' not in session or session.get('designation') not in allowed_roles:
        flash('Unauthorized access.', 'error')
        return redirect(url_for('dashboard'))
        
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM documents WHERE client_id = %s", (client_id,))
        docs = cursor.fetchall()
        cursor.close()
        conn.close()
        
        if not docs:
            flash('No documents found for this client.', 'error')
            return redirect(url_for('client_details', client_id=client_id))
            
        memory_file = io.BytesIO()
        with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for doc in docs:
                # Use the full path to the file on the server
                full_filepath = os.path.join(app.config['UPLOAD_FOLDER'], doc['filepath'])
                if os.path.exists(full_filepath):
                    safe_filename = secure_filename(doc['filename'])
                    # Group by category in the zip file
                    archive_name = f"{doc['category']}/{safe_filename}"
                    zipf.write(full_filepath, archive_name)
                    
        memory_file.seek(0)
        return send_file(
            memory_file,
            download_name=f'client_{client_id}_documents.zip',
            as_attachment=True,
            mimetype='application/zip'
        )
            
    except Exception as e:
        print(f"Error downloading all documents: {e}")
        flash('Error compressing and downloading documents.', 'error')
        return redirect(url_for('client_details', client_id=client_id))


@app.route('/verify-payment/<int:app_id>', methods=['POST'])
def verify_payment(app_id):
    if 'user_id' not in session or session.get('designation') != 'Accounts':
        return redirect(url_for('employee_login'))
        
    payment_type = request.form.get('payment_type') # 'partial' or 'final'
    action = request.form.get('action') # 'approve' or 'reject'
    
    new_status = 'PARTIAL_PAYMENT_VERIFIED' if payment_type == 'partial' else 'FINAL_PAYMENT_VERIFIED'
    
    if action == 'reject':
        new_status = 'PENDING_CONTRACT_QUOTATION' if payment_type == 'partial' else 'TECHNICAL_REVIEW' # send back
        
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE applications SET status = %s WHERE id = %s", (new_status, app_id))
        conn.commit()
        cursor.close()
        conn.close()
        log_activity(session['user_id'], 'PAYMENT_VERIFY', f"{action.capitalize()}ed {payment_type} payment for app {app_id}")
        flash(f'Payment {action}d successfully.', 'success')
    except Exception as e:
        print(f"Error verifying payment: {e}")
        flash('Error processing payment.', 'error')
        
    return redirect(url_for('dashboard'))

@app.route('/download-certificate/<int:app_id>')
@app.route('/view-certificate/<int:app_id>')
def view_certificate(app_id):
    if 'user_id' not in session:
        return redirect(url_for('home'))
        
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM documents WHERE application_id = %s AND category = 'CERTIFICATE' ORDER BY uploaded_at DESC LIMIT 1", (app_id,))
        doc = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if not doc:
            flash('Certificate not found.', 'error')
            return redirect(url_for('dashboard'))
            
        # Permission check
        allowed_roles = ['CEO', 'Admin', 'Certifier']
        if session.get('designation') == 'Client':
            if doc['client_id'] != session['user_id']:
                flash('Unauthorized.', 'error')
                return redirect(url_for('dashboard'))
        elif session.get('designation') not in allowed_roles:
            flash('Unauthorized.', 'error')
            return redirect(url_for('dashboard'))
            
        return send_from_directory(app.config['UPLOAD_FOLDER'], doc['filepath'], as_attachment=True, download_name=doc['filename'])
    except Exception as e:
        print(f"Error viewing certificate: {e}")
        flash('Error loading certificate.', 'error')
        return redirect(url_for('dashboard'))

@app.route('/generate-certificate/<int:app_id>', methods=['POST'])
def generate_certificate(app_id):
    if 'user_id' not in session or session.get('designation') != 'CEO':
        flash('Unauthorized access.', 'error')
        return redirect(url_for('dashboard'))
        
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Fetch application and client details
        cursor.execute("""
            SELECT a.*, u.full_name as client_name 
            FROM applications a
            JOIN users u ON a.client_id = u.id
            WHERE a.id = %s
        """, (app_id,))
        app_data = cursor.fetchone()
        
        if not app_data:
            flash('Application not found.', 'error')
            return redirect(url_for('dashboard'))
            
        # Use the uploaded certificate template
        template_name = "Certificate Of Achievement.pdf"
        template_path = os.path.join(app.config['UPLOAD_FOLDER'], template_name)
        
        if not os.path.exists(template_path):
            flash('Certificate template not found in uploads folder.', 'error')
            return redirect(url_for('dashboard'))
            
        import shutil
        filename = f"Certificate_{app_id}_{datetime.now().strftime('%Y%m%d')}.pdf"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        shutil.copy(template_path, filepath)
        
        # Save to documents table
        cursor.execute(
            "INSERT INTO documents (client_id, application_id, filename, filepath, category) VALUES (%s, %s, %s, %s, 'CERTIFICATE')",
            (app_data['client_id'], app_id, filename, filename)
        )
        
        # Update application status
        cursor.execute("UPDATE applications SET status = 'CERTIFICATE_ISSUED' WHERE id = %s", (app_id,))
        conn.commit()
        
        cursor.close()
        conn.close()
        
        log_activity(session['user_id'], 'GENERATE_CERTIFICATE', f"Issued certificate {filename} for application {app_id} using template")
        flash('Certificate issued successfully using the provided template!', 'success')
    except Exception as e:
        print(f"Error issuing certificate: {e}")
        flash('Error issuing certificate.', 'error')
        
    return redirect(url_for('dashboard'))



@app.route('/restart-application/<int:app_id>', methods=['POST'])
def restart_application(app_id):
    if 'user_id' not in session or session.get('designation') != 'Admin':
        flash('Unauthorized access.', 'error')
        return redirect(url_for('employee_login'))
    rejection_reason = request.form.get('rejection_reason', '').strip()
    if not rejection_reason:
        flash('A rejection reason is mandatory to restart the application.', 'error')
        return redirect(url_for('dashboard'))
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute('SELECT * FROM applications WHERE id = %s', (app_id,))
        application = cursor.fetchone()
        if not application or application['status'] != 'REJECTED':
            flash('Only REJECTED applications can be restarted.', 'error')
            cursor.close()
            conn.close()
            return redirect(url_for('dashboard'))
        new_restart_count = (application.get('restart_count') or 0) + 1
        cursor.execute(
            'UPDATE applications SET status = %s, restart_count = %s WHERE id = %s',
            ('DOCUMENT_REVIEW', new_restart_count, app_id)
        )
        cursor.execute(
            'INSERT INTO application_restarts (application_id, restarted_by, restart_count, rejection_reason) VALUES (%s, %s, %s, %s)',
            (app_id, session['user_id'], new_restart_count, rejection_reason)
        )
        conn.commit()
        cursor.execute(
            'INSERT INTO messages (sender_id, receiver_id, subject, body, is_read) VALUES (%s, %s, %s, %s, 0)',
            (session['user_id'], application['client_id'],
             f'Application #{app_id} Restarted (Attempt #{new_restart_count})',
             f'Your application requires corrections.\n\nReason: {rejection_reason}\n\nPlease re-upload the corrected documents from your dashboard.')
        )
        conn.commit()
        cursor.close()
        conn.close()
        log_activity(session['user_id'], 'RESTART_APPLICATION', f'Restarted application {app_id} (Attempt #{new_restart_count}). Reason: {rejection_reason}')
        flash(f'Application #{app_id} has been restarted (Attempt #{new_restart_count}). Client has been notified.', 'success')
    except Exception as e:
        print(f'Error restarting application: {e}')
        flash('Error restarting application.', 'error')
    return redirect(url_for('dashboard'))


@app.route('/restart-history/<int:app_id>')
def restart_history(app_id):
    allowed_roles = ['CEO', 'Admin', 'QA', 'Initial reviewer', 'Inspection planner', 'Auditor', 'Technical reviewer', 'Certifier']
    if 'user_id' not in session or session.get('designation') not in allowed_roles:
        flash('Unauthorized access.', 'error')
        return redirect(url_for('dashboard'))
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute('SELECT * FROM applications WHERE id = %s', (app_id,))
        application = cursor.fetchone()
        cursor.execute(
            'SELECT r.*, u.full_name as restarted_by_name FROM application_restarts r JOIN users u ON r.restarted_by = u.id WHERE r.application_id = %s ORDER BY r.restarted_at ASC',
            (app_id,)
        )
        history = cursor.fetchall()
        cursor.close()
        conn.close()
        return render_template('restart_history.html', user=session, application=application, history=history)
    except Exception as e:
        print(f'Error fetching restart history: {e}')
        flash('Error loading restart history.', 'error')
        return redirect(url_for('dashboard'))

@app.route('/api/auditor-tasks')
def get_auditor_tasks():
    if 'user_id' not in session or session.get('designation') != 'Auditor':
        return jsonify({'error': 'Unauthorized'}), 403
        
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Fetch tasks for this auditor, joining with applications for company info
        cursor.execute("""
            SELECT t.id, t.title, t.due_date, t.status, a.company_name, t.assignee_id, t.created_at
            FROM tasks t
            LEFT JOIN applications a ON t.application_id = a.id
            WHERE t.assignee_id = %s
        """, (session['user_id'],))
        tasks = cursor.fetchall()
        
        # Fetch applications (audit projects) for this auditor (including completed ones)
        cursor.execute("""
            SELECT a.id, a.client_id, a.company_name, a.program_type, a.status, a.audit_start_date, a.audit_end_date, a.created_at
            FROM applications a
            WHERE a.lead_auditor_id = %s OR a.status IN ('AUDIT_IN_PROGRESS', 'TECHNICAL_REVIEW', 'CERTIFICATE_ISSUED', 'FINAL_PAYMENT_PENDING', 'FINAL_PAYMENT_VERIFIED')
        """, (session['user_id'],))
        apps = cursor.fetchall()
        
        # Format for FullCalendar
        events = []
        for task in tasks:
            start_date = task['due_date']
            if not start_date and task['created_at']:
                if isinstance(task['created_at'], datetime):
                    start_date = task['created_at'].date()
                else:
                    start_date = task['created_at']
                    
            if not start_date:
                continue
                
            # Determine color based on status and date
            color = '#2d5a27' # Default Green (Pending)
            if task['status'] == 'COMPLETED':
                color = '#28a745' # Green
            elif task['status'] == 'CANCELLED':
                color = '#dc3545' # Red
            else:
                try:
                    compare_date = start_date.date() if hasattr(start_date, 'date') else start_date
                    if compare_date < datetime.now().date() and task['status'] not in ['COMPLETED', 'CANCELLED']:
                        color = '#dc3545' # Red (Overdue)
                except Exception as ex:
                    print(f"Error checking overdue date: {ex}")
            
            start_date_str = start_date.strftime('%Y-%m-%d') if hasattr(start_date, 'strftime') else str(start_date)
            events.append({
                'id': f"task-{task['id']}",
                'title': f"Task:\n{task['title']}\n({task['company_name'] if task['company_name'] else 'Internal'})",
                'start': start_date_str,
                'color': color,
                'extendedProps': {
                    'type': 'task',
                    'status': task['status'],
                    'company': task['company_name'] or 'N/A',
                    'raw_title': task['title']
                }
            })
            
        for app in apps:
            start_date = app['audit_start_date']
            if not start_date:
                # Find the assignment date from activity_log
                cursor.execute("""
                    SELECT MIN(created_at) as assign_date 
                    FROM activity_log 
                    WHERE action = 'UPDATE_STATUS' 
                      AND (details LIKE %s OR details LIKE %s)
                """, (f"%Advanced application {app['id']} to AUDIT_IN_PROGRESS%", f"%Advanced application {app['id']} to INSPECTION_PLANNING%"))
                log_row = cursor.fetchone()
                
                if log_row and log_row['assign_date']:
                    start_date = log_row['assign_date']
                else:
                    start_date = app['created_at']
                    
            if not start_date:
                continue
                
            if isinstance(start_date, datetime):
                start_date = start_date.date()
                
            # Determine color based on app status
            color = '#c5a059' # Default Gold (Audit in Progress)
            if app['status'] == 'CERTIFICATE_ISSUED':
                color = '#2d5a27' # Green (Certified / Completed)
            elif app['status'] in ['TECHNICAL_REVIEW', 'FINAL_PAYMENT_PENDING', 'FINAL_PAYMENT_VERIFIED']:
                color = '#ffc107' # Amber/Yellow (Under Review / Finalization)
            
            start_date_str = start_date.strftime('%Y-%m-%d') if hasattr(start_date, 'strftime') else str(start_date)
            title = f"Audit:\n{app['company_name']}\n({app['program_type']})"
            
            events.append({
                'id': f"audit-{app['id']}",
                'title': title,
                'start': start_date_str,
                'color': color,
                'extendedProps': {
                    'type': 'audit',
                    'status': app['status'].replace('_', ' ').title(),
                    'company': app['company_name'] or 'N/A',
                    'raw_title': title,
                    'app_id': app['id'],
                    'client_id': app['client_id']
                }
            })
            
        return jsonify(events)
    except Exception as e:
        print(f"Error fetching tasks API: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/update-task-status/<int:task_id>', methods=['POST'])
def api_update_task_status(task_id):
    if 'user_id' not in session or session.get('designation') != 'Auditor':
        return jsonify({'error': 'Unauthorized'}), 403
        
    try:
        new_status = request.json.get('status')
        if new_status not in ['PENDING', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED']:
            return jsonify({'error': 'Invalid status'}), 400
            
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Verify the task belongs to the user
        cursor.execute("SELECT id FROM tasks WHERE id = %s AND assignee_id = %s", (task_id, session['user_id']))
        if not cursor.fetchone():
            cursor.close()
            conn.close()
            return jsonify({'error': 'Task not found or unauthorized'}), 404
            
        cursor.execute("UPDATE tasks SET status = %s WHERE id = %s", (new_status, task_id))
        conn.commit()
        
        cursor.close()
        conn.close()
        
        log_activity(session['user_id'], 'UPDATE_TASK', f"Updated task {task_id} status to {new_status}")
        return jsonify({'success': True, 'message': 'Task status updated'})
    except Exception as e:
        print(f"Error updating task status API: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/submit-client-feedback', methods=['POST'])
def submit_client_feedback():
    if 'user_id' not in session or session.get('designation') != 'Client':
        flash('Unauthorized access.', 'error')
        return redirect(url_for('home'))
        
    message = request.form.get('message')
    if not message:
        flash('Feedback message is required.', 'error')
        return redirect(url_for('dashboard'))
        
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO client_feedback (client_id, message) VALUES (%s, %s)",
            (session['user_id'], message)
        )
        conn.commit()
        cursor.close()
        conn.close()
        flash('Thank you for your feedback!', 'success')
    except Exception as e:
        print(f"Error submitting feedback: {e}")
        flash('Error submitting feedback.', 'error')
        
    return redirect(url_for('dashboard'))

@app.route('/submit-client-appeal', methods=['POST'])
def submit_client_appeal():
    if 'user_id' not in session or session.get('designation') != 'Client':
        flash('Unauthorized access.', 'error')
        return redirect(url_for('home'))
        
    appeal_type = request.form.get('type')
    subject = request.form.get('subject')
    description = request.form.get('description')
    
    if not appeal_type or not subject or not description:
        flash('All fields are required.', 'error')
        return redirect(url_for('dashboard'))
        
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO client_appeals (client_id, type, subject, description) VALUES (%s, %s, %s, %s)",
            (session['user_id'], appeal_type, subject, description)
        )
        conn.commit()
        cursor.close()
        conn.close()
        flash(f'Your {appeal_type.lower()} has been submitted successfully.', 'success')
    except Exception as e:
        print(f"Error submitting appeal/complaint: {e}")
        flash('Error submitting appeal or complaint.', 'error')
        
    return redirect(url_for('dashboard'))

@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    if 'user_id' not in session:
        return redirect(url_for('home'))
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/download-doc/<path:filename>')
def download_doc(filename):
    allowed_files = [
        'POL-01_Quality_Policy.pdf',
        
        'FMO05_Fee Schedule.pdf',
        'PRO03_Certification procedure.pdf',
        'PRO05_Suspension, Cancellation, Withdrawal and Appeal Procedure.pdf',
        'PRO06_Complaint procedure.pdf'
    ]
    if filename in allowed_files:
        as_attachment = request.args.get('inline') != '1'
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=as_attachment)
    return "File not found or access denied", 404

# --- Internal Training Assessment System Routes ---

@app.route('/ceo/create-assessment', methods=['GET', 'POST'])
def create_assessment():
    if 'user_id' not in session or session.get('designation') != 'CEO':
        flash('Unauthorized access.', 'error')
        return redirect(url_for('employee_login'))
    
    if request.method == 'POST':
        title = request.form.get('title')
        training_type = request.form.get('training_type')
        questions = []
        for i in range(1, 26):
            q_text = request.form.get(f'q{i}_text')
            if q_text:
                q_type = request.form.get(f'q{i}_type', 'text')
                options = request.form.get(f'q{i}_options', '')
                questions.append({
                    'id': i,
                    'text': q_text,
                    'type': q_type,
                    'options': [opt.strip() for opt in options.split(',')] if options else []
                })
        
        if not questions:
            flash('Please add at least one question.', 'error')
            return redirect(url_for('create_assessment'))
            
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO training_assessments (ceo_id, title, training_type, questions) VALUES (%s, %s, %s, %s)",
                (session['user_id'], title, training_type, json.dumps(questions))
            )
            conn.commit()
            cursor.close()
            conn.close()
            flash('Assessment created successfully.', 'success')
            return redirect(url_for('dashboard'))
        except Exception as e:
            print(f"Error creating assessment: {e}")
            flash('Error creating assessment.', 'error')
            
    return render_template('db_ceo_create_assessment.html', user=session, training_data=TRAINING_DATA)

@app.route('/ceo/assign-assessment', methods=['POST'])
def assign_assessment():
    if 'user_id' not in session or session.get('designation') != 'CEO':
        flash('Unauthorized access.', 'error')
        return redirect(url_for('employee_login'))
    
    assessment_id = request.form.get('assessment_id')
    employee_ids = request.form.getlist('employee_ids')
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        for emp_id in employee_ids:
            cursor.execute("SELECT id FROM assessment_assignments WHERE assessment_id = %s AND employee_id = %s", (assessment_id, emp_id))
            if not cursor.fetchone():
                cursor.execute(
                    "INSERT INTO assessment_assignments (assessment_id, employee_id) VALUES (%s, %s)",
                    (assessment_id, emp_id)
                )
        conn.commit()
        cursor.close()
        conn.close()
        flash('Assessments assigned successfully.', 'success')
    except Exception as e:
        print(f"Error assigning assessment: {e}")
        flash('Error assigning assessment.', 'error')
        
    return redirect(url_for('dashboard'))

@app.route('/employee/take-assessment/<int:assignment_id>', methods=['GET', 'POST'])
def take_assessment(assignment_id):
    if 'user_id' not in session:
        return redirect(url_for('employee_login'))
    user_id = session['user_id']
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT aa.*, ta.title, ta.training_type, ta.questions 
            FROM assessment_assignments aa
            JOIN training_assessments ta ON aa.assessment_id = ta.id
            WHERE aa.id = %s AND aa.employee_id = %s AND aa.status = 'PENDING'
        """, (assignment_id, user_id))
        assignment = cursor.fetchone()
        if not assignment:
            flash('Assessment not found or already completed.', 'error')
            return redirect(url_for('dashboard'))
        if request.method == 'POST':
            questions = json.loads(assignment['questions'])
            answers = {}
            for q in questions:
                answer = request.form.get(f"q{q['id']}")
                answers[str(q['id'])] = answer
            cursor.execute(
                "INSERT INTO assessment_responses (assignment_id, employee_id, answers) VALUES (%s, %s, %s)",
                (assignment_id, user_id, json.dumps(answers))
            )
            cursor.execute(
                "UPDATE assessment_assignments SET status = 'COMPLETED', completed_at = CURRENT_TIMESTAMP WHERE id = %s",
                (assignment_id,)
            )
            conn.commit()
            flash('Assessment submitted successfully.', 'success')
            return redirect(url_for('dashboard'))
        cursor.close()
        conn.close()
        assignment['questions'] = json.loads(assignment['questions'])
        return render_template('db_employee_take_assessment.html', user=session, assessment=assignment)
    except Exception as e:
        print(f"Error taking assessment: {e}")
        flash('Error loading assessment.', 'error')
        return redirect(url_for('dashboard'))

@app.route('/ceo/assessment-results/<int:assessment_id>')
def assessment_results(assessment_id):
    if 'user_id' not in session or session.get('designation') != 'CEO':
        return redirect(url_for('employee_login'))
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Get assessment info
        cursor.execute("SELECT * FROM training_assessments WHERE id = %s", (assessment_id,))
        assessment = cursor.fetchone()
        if not assessment:
            return "Assessment not found", 404
        assessment['questions'] = json.loads(assessment['questions'])
        assessment['correct_answers'] = json.loads(assessment['correct_answers']) if assessment.get('correct_answers') else None
        
        # Get ALL assignments to track who was assigned and who completed
        cursor.execute("""
            SELECT aa.*, u.full_name as employee_name, u.designation
            FROM assessment_assignments aa
            JOIN users u ON aa.employee_id = u.id
            WHERE aa.assessment_id = %s
            ORDER BY aa.status DESC, aa.completed_at DESC
        """, (assessment_id,))
        assignments = cursor.fetchall()

        # Get all responses
        cursor.execute("""
            SELECT ar.*, u.full_name as employee_name 
            FROM assessment_responses ar
            JOIN assessment_assignments aa ON ar.assignment_id = aa.id
            JOIN users u ON ar.employee_id = u.id
            WHERE aa.assessment_id = %s
        """, (assessment_id,))
        responses = cursor.fetchall()
        
        # Calculate Completion Rate
        total_assigned = len(assignments)
        completed_count = sum(1 for a in assignments if a['status'] == 'COMPLETED')
        completion_rate = f"{(completed_count / total_assigned * 100):.0f}%" if total_assigned > 0 else "0%"
        
        # Calculate Average Score
        mcq_questions = [q for q in assessment['questions'] if q['type'] == 'mcq']
        has_mcq = len(mcq_questions) > 0
        average_score_val = "N/A"
        
        if has_mcq:
            if assessment['correct_answers']:
                total_scores = []
                for resp in responses:
                    resp_answers = json.loads(resp['answers'])
                    correct_count = 0
                    for q in mcq_questions:
                        q_id = str(q['id'])
                        user_ans = str(resp_answers.get(q_id)).strip().lower()
                        correct_ans = str(assessment['correct_answers'].get(q_id)).strip().lower()
                        if user_ans == correct_ans:
                            correct_count += 1
                    score_pct = (correct_count / len(mcq_questions)) * 100
                    total_scores.append(score_pct)
                
                if total_scores:
                    avg = sum(total_scores) / len(total_scores)
                    average_score_val = f"{avg:.1f}%"
                else:
                    average_score_val = "0%"
            else:
                average_score_val = "Pending Key"
        
        analytics = {}
        for q in assessment['questions']:
            q_id = str(q['id'])
            analytics[q_id] = {}
            if q['type'] == 'mcq':
                for opt in q['options']:
                    analytics[q_id][opt] = 0
        
        for resp in responses:
            resp_answers = json.loads(resp['answers'])
            for q_id, val in resp_answers.items():
                if q_id in analytics:
                    if val in analytics[q_id]:
                        analytics[q_id][val] += 1
                    else:
                        analytics[q_id][val] = analytics[q_id].get(val, 0) + 1
        
        cursor.close()
        conn.close()
        return render_template('db_ceo_assessment_analytics.html', 
                               user=session, 
                               assessment=assessment, 
                               responses=responses, 
                               analytics=analytics, 
                               assignments=assignments,
                               completion_rate=completion_rate,
                               average_score=average_score_val)
    except Exception as e:
        print(f"Analytics error: {e}")
        return "Error loading analytics", 500

@app.route('/ceo/upload-answer-key/<int:assessment_id>', methods=['POST'])
def upload_answer_key(assessment_id):
    if 'user_id' not in session or session.get('designation') != 'CEO':
        flash('Unauthorized access.', 'error')
        return redirect(url_for('employee_login'))
    
    file = request.files.get('answer_key')
    if not file or file.filename == '':
        flash('No file selected.', 'error')
        return redirect(url_for('assessment_results', assessment_id=assessment_id))
    
    try:
        df = pd.read_excel(file)
        # Expected format: Column 0: Q No, Column 1: Correct Answer
        correct_answers = {}
        for _, row in df.iterrows():
            q_no = str(row.iloc[0]).strip().split('.')[0] # Remove .0 from numbers
            ans = str(row.iloc[1]).strip()
            if q_no and ans:
                correct_answers[q_no] = ans
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE training_assessments SET correct_answers = %s WHERE id = %s",
            (json.dumps(correct_answers), assessment_id)
        )
        conn.commit()
        cursor.close()
        conn.close()
        flash('Answer key uploaded successfully!', 'success')
    except Exception as e:
        print(f"Error uploading answer key: {e}")
        flash(f'Error processing Excel file: {str(e)}', 'error')
        
    return redirect(url_for('assessment_results', assessment_id=assessment_id))

@app.route('/ceo/archive-assessment/<int:assessment_id>', methods=['POST'])
def archive_assessment(assessment_id):
    if 'user_id' not in session or session.get('designation') != 'CEO':
        flash('Unauthorized access.', 'error')
        return redirect(url_for('employee_login'))
    
    action = request.form.get('action', 'archive')
    is_archived = 1 if action == 'archive' else 0
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE training_assessments SET is_archived = %s WHERE id = %s", (is_archived, assessment_id))
        conn.commit()
        cursor.close()
        conn.close()
        flash(f"Assessment {'archived' if is_archived else 'restored'} successfully.", 'success')
    except Exception as e:
        print(f"Error archiving assessment: {e}")
        flash('Error updating assessment status.', 'error')
        
    return redirect(url_for('dashboard'))

@app.route('/ceo/delete-assessment/<int:assessment_id>', methods=['POST'])
def delete_assessment(assessment_id):
    if 'user_id' not in session or session.get('designation') != 'CEO':
        flash('Unauthorized access.', 'error')
        return redirect(url_for('employee_login'))
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM training_assessments WHERE id = %s", (assessment_id,))
        conn.commit()
        cursor.close()
        conn.close()
        flash('Assessment deleted successfully.', 'success')
    except Exception as e:
        print(f"Error deleting assessment: {e}")
        flash('Error deleting assessment.', 'error')
        
    return redirect(url_for('dashboard'))


@app.route('/save-message-attachment-to-repo/<int:msg_id>', methods=['POST'])
def save_message_attachment_to_repo(msg_id):
    if 'user_id' not in session or session.get('designation') == 'Client':
        flash('Unauthorized access.', 'error')
        return redirect(url_for('home'))
        
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Verify user is sender or receiver of the message
        cursor.execute("SELECT * FROM messages WHERE id = %s AND (sender_id = %s OR receiver_id = %s)", (msg_id, session['user_id'], session['user_id']))
        msg = cursor.fetchone()
        
        if not msg or not msg['attachment_path']:
            flash('Attachment not found.', 'error')
            return redirect(url_for('messages', id=msg_id))
            
        # Add to employee repository
        # Note: We reuse the same physical file (attachment_path) but create a new entry in repository
        cursor.execute(
            "INSERT INTO employee_repository (user_id, filename, filepath, original_message_id) VALUES (%s, %s, %s, %s)",
            (session['user_id'], msg['attachment_filename'], msg['attachment_path'], msg_id)
        )
        conn.commit()
        cursor.close()
        conn.close()
        
        flash('Attachment saved to your repository!', 'success')
    except Exception as e:
        print(f"Error saving attachment to repo: {e}")
        flash('Error saving attachment.', 'error')
        
    return redirect(url_for('messages', id=msg_id))

@app.route('/repository', methods=['GET', 'POST'])
def repository():
    if 'user_id' not in session or session.get('designation') == 'Client':
        flash('Unauthorized access.', 'error')
        return redirect(url_for('home'))
        
    user_id = session['user_id']
    
    if request.method == 'POST':
        file = request.files.get('file')
        if not file or file.filename == '':
            flash('No file selected.', 'error')
            return redirect(url_for('repository'))
            
        try:
            from werkzeug.utils import secure_filename
            from datetime import datetime
            import os
            
            filename = secure_filename(file.filename)
            timestamp_filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_user_{user_id}_{filename}"
            
            if not os.path.exists(app.config['UPLOAD_FOLDER']):
                os.makedirs(app.config['UPLOAD_FOLDER'])
                
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], timestamp_filename)
            file.save(filepath)
            
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO employee_repository (user_id, filename, filepath) VALUES (%s, %s, %s)",
                (user_id, filename, timestamp_filename)
            )
            conn.commit()
            cursor.close()
            conn.close()
            flash('File uploaded to repository successfully!', 'success')
        except Exception as e:
            print(f"Error uploading repo file: {e}")
            flash('Error uploading file.', 'error')
            
        return redirect(url_for('repository'))
        
    # GET request
    files = []
    global_docs = []
    obsolete_docs = []
    show_archived = request.args.get('archived') == 'true'
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Personal files
        cursor.execute("SELECT * FROM employee_repository WHERE user_id = %s AND is_archived = %s ORDER BY uploaded_at DESC", 
                       (user_id, show_archived))
        files = cursor.fetchall()
        
        # Global Documents (Company Policies/Forms)
        cursor.execute("SELECT * FROM global_documents WHERE status = 'ACTIVE' ORDER BY category, filename")
        all_global_docs = cursor.fetchall()
        
        # Obsolete Global Documents
        cursor.execute("SELECT * FROM global_documents WHERE status = 'OBSOLETE' ORDER BY updated_at DESC")
        all_obsolete_docs = cursor.fetchall()
        
        import json
        
        def is_visible(doc, user_id):
            if session.get('designation') == 'CEO':
                return True
            visible_to = doc.get('visible_to', 'ALL')
            if not visible_to or visible_to == 'ALL':
                return True
            try:
                allowed_users = json.loads(visible_to)
                if str(user_id) in allowed_users:
                    return True
            except:
                pass
            return False

        global_docs = [doc for doc in all_global_docs if is_visible(doc, user_id)]
        obsolete_docs = [doc for doc in all_obsolete_docs if is_visible(doc, user_id)]
        
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Error fetching repo files: {e}")
        
    return render_template('db_repository.html', user=session, files=files, global_docs=global_docs, obsolete_docs=obsolete_docs, show_archived=show_archived)

@app.route('/repository-action/<int:file_id>/<string:action>', methods=['POST', 'GET'])
def repository_action(file_id, action):
    if 'user_id' not in session:
        return redirect(url_for('home'))
        
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM employee_repository WHERE id = %s AND user_id = %s", (file_id, session['user_id']))
        file = cursor.fetchone()
        
        if not file:
            flash('File not found or unauthorized.', 'error')
            return redirect(url_for('repository'))
            
        if action == 'download':
            return send_from_directory(app.config['UPLOAD_FOLDER'], file['filepath'], as_attachment=True, download_name=file['filename'])
            
        elif action == 'delete':
            import os
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], file['filepath'])
            if os.path.exists(filepath):
                os.remove(filepath)
            cursor.execute("DELETE FROM employee_repository WHERE id = %s", (file_id,))
            conn.commit()
            flash('File deleted from repository.', 'success')
            
        elif action == 'archive':
            cursor.execute("UPDATE employee_repository SET is_archived = NOT is_archived WHERE id = %s", (file_id,))
            conn.commit()
            flash('Archive status updated.', 'success')
            
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Error in repository action: {e}")
        flash('An error occurred.', 'error')
        
    return redirect(url_for('repository'))

@app.route('/ceo/global-docs')
def ceo_global_docs():
    if 'user_id' not in session or session.get('designation') != 'CEO':
        flash('Unauthorized access.', 'error')
        return redirect(url_for('home'))
        
    status = request.args.get('status', 'ACTIVE')
    documents = []
    employees = []
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM global_documents WHERE status = %s ORDER BY updated_at DESC", (status,))
        documents = cursor.fetchall()
        
        cursor.execute("SELECT id, full_name, designation FROM users WHERE designation != 'Client' ORDER BY full_name")
        employees = cursor.fetchall()
        
        emp_map = {str(e['id']): e['full_name'] for e in employees}
        import json
        for doc in documents:
            vt = doc.get('visible_to', 'ALL')
            if vt == 'ALL' or not vt:
                doc['visible_to_names'] = 'All Employees'
            else:
                try:
                    ids = json.loads(vt)
                    names = [emp_map.get(str(i), 'Unknown') for i in ids]
                    doc['visible_to_names'] = ', '.join(names)
                except:
                    doc['visible_to_names'] = 'Invalid Data'
                    
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Error fetching global docs: {e}")
        
    return render_template('db_ceo_global_docs.html', user=session, documents=documents, status=status, employees=employees)

@app.route('/ceo/upload-global-doc', methods=['POST'])
def upload_global_doc():
    if 'user_id' not in session or session.get('designation') != 'CEO':
        flash('Unauthorized access.', 'error')
        return redirect(url_for('home'))
        
    file = request.files.get('file')
    category = 'General'
    visible_to_list = request.form.getlist('visible_to')
    
    if not visible_to_list or 'ALL' in visible_to_list:
        visible_to = 'ALL'
    else:
        import json
        visible_to = json.dumps(visible_to_list)
    
    if not file or file.filename == '':
        flash('No file selected.', 'error')
        return redirect(url_for('ceo_global_docs'))
        
    try:
        from werkzeug.utils import secure_filename
        from datetime import datetime
        import os
        
        filename = secure_filename(file.filename)
        timestamp_filename = f"GLOBAL_{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
        
        if not os.path.exists(app.config['UPLOAD_FOLDER']):
            os.makedirs(app.config['UPLOAD_FOLDER'])
            
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], timestamp_filename)
        file.save(filepath)
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO global_documents (filename, filepath, category, uploaded_by, visible_to) VALUES (%s, %s, %s, %s, %s)",
            (filename, timestamp_filename, category, session['user_id'], visible_to)
        )
        conn.commit()
        cursor.close()
        conn.close()
        flash('Global document uploaded and synced for all employees.', 'success')
    except Exception as e:
        print(f"Error uploading global doc: {e}")
        flash('Error uploading document.', 'error')
        
    return redirect(url_for('ceo_global_docs'))

@app.route('/ceo/update-global-doc-visibility/<int:doc_id>', methods=['POST'])
def update_global_doc_visibility(doc_id):
    if 'user_id' not in session or session.get('designation') != 'CEO':
        flash('Unauthorized access.', 'error')
        return redirect(url_for('home'))
        
    visible_to_list = request.form.getlist('visible_to')
    
    if not visible_to_list or 'ALL' in visible_to_list:
        visible_to = 'ALL'
    else:
        import json
        visible_to = json.dumps(visible_to_list)
        
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE global_documents SET visible_to = %s WHERE id = %s", (visible_to, doc_id))
        conn.commit()
        cursor.close()
        conn.close()
        flash('Document visibility updated successfully.', 'success')
    except Exception as e:
        print(f"Error updating visibility: {e}")
        flash('An error occurred.', 'error')
        
    return redirect(request.referrer or url_for('ceo_global_docs'))

@app.route('/ceo/mark-doc-obsolete/<int:doc_id>', methods=['POST'])
def mark_doc_obsolete(doc_id):
    if 'user_id' not in session or session.get('designation') != 'CEO':
        flash('Unauthorized access.', 'error')
        return redirect(url_for('home'))
        
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE global_documents SET status = 'OBSOLETE' WHERE id = %s", (doc_id,))
        conn.commit()
        cursor.close()
        conn.close()
        flash('Document marked as obsolete for all employees.', 'success')
    except Exception as e:
        print(f"Error marking doc obsolete: {e}")
        flash('Error updating document status.', 'error')
        
    return redirect(url_for('ceo_global_docs'))

@app.route('/ceo/mark-doc-active/<int:doc_id>', methods=['POST'])
def mark_doc_active(doc_id):
    if 'user_id' not in session or session.get('designation') != 'CEO':
        flash('Unauthorized access.', 'error')
        return redirect(url_for('home'))
        
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE global_documents SET status = 'ACTIVE' WHERE id = %s", (doc_id,))
        conn.commit()
        cursor.close()
        conn.close()
        flash('Document restored to active for all employees.', 'success')
    except Exception as e:
        print(f"Error marking doc active: {e}")
        flash('Error updating document status.', 'error')
        
    return redirect(url_for('ceo_global_docs'))

@app.route('/ceo/delete-global-doc/<int:doc_id>', methods=['POST'])
def delete_global_doc(doc_id):
    if 'user_id' not in session or session.get('designation') != 'CEO':
        flash('Unauthorized access.', 'error')
        return redirect(url_for('home'))
        
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT filepath FROM global_documents WHERE id = %s", (doc_id,))
        doc = cursor.fetchone()
        
        if doc:
            import os
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], doc['filepath'])
            if os.path.exists(filepath):
                os.remove(filepath)
            cursor.execute("DELETE FROM global_documents WHERE id = %s", (doc_id,))
            conn.commit()
            flash('Global document permanently deleted.', 'success')
            
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Error deleting global doc: {e}")
        flash('Error deleting document.', 'error')
        
    return redirect(url_for('ceo_global_docs'))

@app.route('/download-global-doc/<int:doc_id>')
def download_global_doc(doc_id):
    if 'user_id' not in session:
        return redirect(url_for('home'))
        
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM global_documents WHERE id = %s", (doc_id,))
        doc = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if doc:
            if doc['status'] == 'OBSOLETE' and session.get('designation') != 'CEO':
                flash('Download restricted. Document is obsolete.', 'error')
                return redirect(request.referrer or url_for('dashboard'))
                
            return send_from_directory(app.config['UPLOAD_FOLDER'], doc['filepath'], as_attachment=True, download_name=doc['filename'])
    except Exception as e:
        print(f"Error downloading global doc: {e}")
        
    flash('Document not found.', 'error')
    return redirect(request.referrer or url_for('dashboard'))

@app.route('/profile')
@app.route('/profile/<int:user_id>')
def view_profile(user_id=None):
    if 'user_id' not in session:
        return redirect(url_for('home'))
        
    is_own_profile = False
    if user_id is None:
        user_id = session['user_id']
        is_own_profile = True
    elif user_id == session['user_id']:
        is_own_profile = True
        
    # Check authorization (CEO/Admin/Quality Manager can view others' profiles)
    if not is_own_profile and session.get('designation') not in ['CEO', 'Admin', 'Quality Manager', 'Qulaity Manager', 'Dy. Quality Manager']:
        flash('Unauthorized access to profile.', 'error')
        return redirect(url_for('dashboard'))
        
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Fetch user info
        cursor.execute("SELECT id, full_name, email, designation, profile_picture FROM users WHERE id = %s", (user_id,))
        user_info = cursor.fetchone()
        
        if not user_info:
            flash('Employee not found.', 'error')
            return redirect(url_for('dashboard'))
            
        # Fetch or create profile
        cursor.execute("""
            SELECT ep.*, client_user.full_name AS assigned_client_name 
            FROM employee_profiles ep
            LEFT JOIN users client_user ON ep.assigned_client_id = client_user.id
            WHERE ep.user_id = %s
        """, (user_id,))
        profile = cursor.fetchone()
        
        if not profile:
            cursor.execute("INSERT INTO employee_profiles (user_id) VALUES (%s)", (user_id,))
            conn.commit()
            cursor.execute("""
                SELECT ep.*, client_user.full_name AS assigned_client_name 
                FROM employee_profiles ep
                LEFT JOIN users client_user ON ep.assigned_client_id = client_user.id
                WHERE ep.user_id = %s
            """, (user_id,))
            profile = cursor.fetchone()
            
        cursor.close()
        conn.close()
        
        return render_template('db_profile.html', user=session, user_info=user_info, profile=profile, is_own_profile=is_own_profile)
    except Exception as e:
        print(f"Error fetching profile: {e}")
        flash('Error loading profile.', 'error')
        return redirect(url_for('dashboard'))

@app.route('/profile/update', methods=['POST'])
def update_profile():
    if 'user_id' not in session:
        return redirect(url_for('home'))
        
    user_id = session['user_id']
    bio = request.form.get('bio')
    education = request.form.get('education_json', '[]')
    trainings = request.form.get('trainings_json', '[]')
    experience = request.form.get('experience_json', '[]')
    skills = request.form.get('skills_json', '[]')
    contact_number = request.form.get('contact_number')
    address = request.form.get('address')
    date_of_joining = request.form.get('date_of_joining') or None

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE employee_profiles 
            SET bio = %s, education = %s, trainings = %s, experience = %s, skills = %s,
                contact_number = %s, address = %s, date_of_joining = %s
            WHERE user_id = %s
        """, (bio, education, trainings, experience, skills, contact_number, address, date_of_joining, user_id))
        conn.commit()
        cursor.close()
        conn.close()
        flash('Professional profile updated successfully!', 'success')
    except Exception as e:
        print(f"Error updating profile: {e}")
        flash('Error updating profile.', 'error')
        
    return redirect(url_for('view_profile'))


@app.route('/profile/upload-cv', methods=['POST'])
def upload_cv():
    """Allow an employee to upload their CV to their profile."""
    if 'user_id' not in session:
        return redirect(url_for('home'))

    user_id = session['user_id']
    file = request.files.get('cv_file')
    if not file or file.filename == '':
        flash('Please select a CV file to upload.', 'error')
        return redirect(url_for('view_profile'))

    # Validate extension
    allowed_ext = {'pdf', 'doc', 'docx'}
    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in allowed_ext:
        flash('Only PDF, DOC and DOCX files are allowed for CV upload.', 'error')
        return redirect(url_for('view_profile'))

    try:
        from datetime import datetime
        original_name = secure_filename(file.filename)
        timestamp_name = f"CV_{datetime.now().strftime('%Y%m%d%H%M%S')}_user_{user_id}_{original_name}"

        if not os.path.exists(app.config['UPLOAD_FOLDER']):
            os.makedirs(app.config['UPLOAD_FOLDER'])

        filepath = os.path.join(app.config['UPLOAD_FOLDER'], timestamp_name)
        file.save(filepath)

        conn = get_db_connection()
        cursor = conn.cursor()
        # Remove old CV file from disk if any
        cursor2 = conn.cursor(dictionary=True)
        cursor2.execute("SELECT cv_path FROM employee_profiles WHERE user_id = %s", (user_id,))
        old = cursor2.fetchone()
        if old and old.get('cv_path'):
            old_file = os.path.join(app.config['UPLOAD_FOLDER'], old['cv_path'])
            if os.path.exists(old_file):
                os.remove(old_file)
        cursor2.close()

        cursor.execute("""
            UPDATE employee_profiles
            SET cv_path = %s, cv_filename = %s, cv_verified = 0, cv_verified_by = NULL,
                cv_verified_at = NULL, cv_remarks = NULL
            WHERE user_id = %s
        """, (timestamp_name, original_name, user_id))
        conn.commit()
        cursor.close()
        conn.close()
        log_activity(user_id, 'CV_UPLOAD', f"Uploaded CV: {original_name}")
        flash('CV uploaded successfully! It will be reviewed by the Quality Manager.', 'success')
    except Exception as e:
        print(f"Error uploading CV: {e}")
        flash('Error uploading CV. Please try again.', 'error')

    return redirect(url_for('view_profile'))


@app.route('/profile/delete-cv', methods=['POST'])
def delete_cv():
    """Allow an employee to remove their uploaded CV."""
    if 'user_id' not in session:
        return redirect(url_for('home'))

    user_id = session['user_id']
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT cv_path FROM employee_profiles WHERE user_id = %s", (user_id,))
        row = cursor.fetchone()
        if row and row.get('cv_path'):
            old_file = os.path.join(app.config['UPLOAD_FOLDER'], row['cv_path'])
            if os.path.exists(old_file):
                os.remove(old_file)
        cursor2 = conn.cursor()
        cursor2.execute("""
            UPDATE employee_profiles
            SET cv_path = NULL, cv_filename = NULL, cv_verified = 0,
                cv_verified_by = NULL, cv_verified_at = NULL, cv_remarks = NULL
            WHERE user_id = %s
        """, (user_id,))
        conn.commit()
        cursor.close()
        cursor2.close()
        conn.close()
        flash('CV removed successfully.', 'success')
    except Exception as e:
        print(f"Error deleting CV: {e}")
        flash('Error removing CV.', 'error')

    return redirect(url_for('view_profile'))


@app.route('/profile/download-cv/<int:target_user_id>')
def download_cv(target_user_id):
    """Download a CV — employee can download their own; QM/CEO/Admin can download any."""
    if 'user_id' not in session:
        return redirect(url_for('home'))

    allowed_roles = ['CEO', 'Admin', 'Quality Manager', 'Qulaity Manager', 'Dy. Quality Manager']
    if target_user_id != session['user_id'] and session.get('designation') not in allowed_roles:
        flash('Unauthorized.', 'error')
        return redirect(url_for('dashboard'))

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT cv_path, cv_filename FROM employee_profiles WHERE user_id = %s", (target_user_id,))
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        if row and row.get('cv_path'):
            return send_from_directory(
                app.config['UPLOAD_FOLDER'],
                row['cv_path'],
                as_attachment=True,
                download_name=row['cv_filename'] or row['cv_path']
            )
        flash('CV not found.', 'error')
    except Exception as e:
        print(f"Error downloading CV: {e}")
        flash('Error downloading CV.', 'error')

    return redirect(request.referrer or url_for('dashboard'))


@app.route('/quality-manager/employee-profiles')
def qm_employee_profiles():
    """Quality Manager dashboard: view and verify all employee profiles & CVs."""
    if 'user_id' not in session:
        return redirect(url_for('home'))

    allowed_roles = ['Quality Manager', 'Qulaity Manager', 'Dy. Quality Manager']
    if session.get('designation') not in allowed_roles:
        flash('Unauthorized access.', 'error')
        return redirect(url_for('dashboard'))

    search = request.args.get('search', '').strip()
    filter_cv = request.args.get('filter_cv', 'all')  # all | uploaded | missing | verified | unverified

    clients = []
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT u.id, u.full_name, u.email, u.designation,
                   ep.bio, ep.contact_number, ep.address,
                   ep.education, ep.trainings, ep.experience, ep.skills,
                   ep.cv_path, ep.cv_filename, ep.cv_verified,
                   ep.cv_verified_at, ep.cv_remarks, ep.job_description,
                   ep.assigned_role, ep.assigned_scheme, ep.assigned_client_id,
                   client_user.full_name AS assigned_client_name,
                   verifier.full_name AS verified_by_name
            FROM users u
            LEFT JOIN employee_profiles ep ON u.id = ep.user_id
            LEFT JOIN users verifier ON ep.cv_verified_by = verifier.id
            LEFT JOIN users client_user ON ep.assigned_client_id = client_user.id
            WHERE u.designation NOT IN ('Client')
        """
        params = []
        if search:
            query += " AND (u.full_name LIKE %s OR u.email LIKE %s OR u.designation LIKE %s)"
            like = f"%{search}%"
            params.extend([like, like, like])
        if filter_cv == 'uploaded':
            query += " AND ep.cv_path IS NOT NULL"
        elif filter_cv == 'missing':
            query += " AND (ep.cv_path IS NULL OR ep.cv_path = '')"
        elif filter_cv == 'verified':
            query += " AND ep.cv_verified = 1"
        elif filter_cv == 'unverified':
            query += " AND ep.cv_path IS NOT NULL AND ep.cv_verified = 0"
        query += " ORDER BY u.full_name ASC"
        cursor.execute(query, params)
        employees = cursor.fetchall()

        cursor.execute("SELECT id, full_name, email FROM users WHERE designation = 'Client' ORDER BY full_name")
        clients = cursor.fetchall()

        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Error loading QM profiles: {e}")
        employees = []

    return render_template(
        'db_qm_employee_profiles.html',
        user=session,
        employees=employees,
        clients=clients,
        search=search,
        filter_cv=filter_cv
    )


@app.route('/quality-manager/verify-cv/<int:target_user_id>', methods=['POST'])
def qm_verify_cv(target_user_id):
    """Quality Manager marks a CV as verified or flags it with remarks."""
    if 'user_id' not in session:
        return redirect(url_for('home'))

    allowed_roles = ['Quality Manager', 'Qulaity Manager', 'Dy. Quality Manager']
    if session.get('designation') not in allowed_roles:
        flash('Unauthorized access.', 'error')
        return redirect(url_for('dashboard'))

    action = request.form.get('action', 'verify')  # verify | reject
    remarks = request.form.get('remarks', '').strip()
    is_verified = 1 if action == 'verify' else 0

    try:
        from datetime import datetime
        conn = get_db_connection()
        cursor = conn.cursor()
        if action == 'verify':
            assigned_role = request.form.get('assigned_role', '').strip() or None
            assigned_scheme = request.form.get('assigned_scheme', '').strip() or None
            assigned_client_raw = request.form.get('assigned_client_id')
            assigned_client_id = int(assigned_client_raw) if assigned_client_raw and assigned_client_raw.isdigit() else None

            parts = []
            if assigned_role:
                parts.append(f"Role: {assigned_role}")
            if assigned_scheme:
                parts.append(f"Scheme: {assigned_scheme}")
            if assigned_client_id:
                cursor.execute("SELECT full_name FROM users WHERE id = %s", (assigned_client_id,))
                c_row = cursor.fetchone()
                if c_row:
                    parts.append(f"Client: {c_row[0]}")
            job_description = ", ".join(parts) if parts else None

            cursor.execute("""
                UPDATE employee_profiles
                SET cv_verified = %s,
                    cv_verified_by = %s,
                    cv_verified_at = %s,
                    cv_remarks = %s,
                    job_description = %s,
                    assigned_role = %s,
                    assigned_scheme = %s,
                    assigned_client_id = %s
                WHERE user_id = %s
            """, (is_verified, session['user_id'], datetime.now(), remarks or None, job_description, assigned_role, assigned_scheme, assigned_client_id, target_user_id))
        else:
            cursor.execute("""
                UPDATE employee_profiles
                SET cv_verified = %s,
                    cv_verified_by = %s,
                    cv_verified_at = %s,
                    cv_remarks = %s
                WHERE user_id = %s
            """, (is_verified, session['user_id'], datetime.now(), remarks or None, target_user_id))
        conn.commit()
        cursor.close()
        conn.close()
        status_word = 'verified' if is_verified else 'flagged for revision'
        log_activity(session['user_id'], 'CV_VERIFY', f"CV of user {target_user_id} {status_word}")
        flash(f"CV {status_word} successfully.", 'success')
    except Exception as e:
        print(f"Error verifying CV: {e}")
        flash('Error updating CV status.', 'error')

    return redirect(url_for('qm_employee_profiles'))


@app.route('/quality-manager/download-profile/<int:target_user_id>')
def qm_download_profile(target_user_id):
    """Quality Manager: download a full employee profile as a printable HTML page."""
    if 'user_id' not in session:
        return redirect(url_for('home'))

    allowed_roles = ['Quality Manager', 'Qulaity Manager', 'Dy. Quality Manager']
    if session.get('designation') not in allowed_roles:
        flash('Unauthorized access.', 'error')
        return redirect(url_for('dashboard'))

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT u.id, u.full_name, u.email, u.designation,
                   ep.bio, ep.contact_number, ep.address,
                   ep.education, ep.trainings, ep.experience, ep.skills,
                   ep.cv_path, ep.cv_filename, ep.cv_verified,
                   ep.cv_verified_at, ep.cv_remarks, ep.job_description,
                   ep.assigned_role, ep.assigned_scheme, ep.assigned_client_id,
                   client_user.full_name AS assigned_client_name,
                   verifier.full_name AS verified_by_name
            FROM users u
            LEFT JOIN employee_profiles ep ON u.id = ep.user_id
            LEFT JOIN users verifier ON ep.cv_verified_by = verifier.id
            LEFT JOIN users client_user ON ep.assigned_client_id = client_user.id
            WHERE u.id = %s
        """, (target_user_id,))
        emp = cursor.fetchone()
        cursor.close()
        conn.close()

        if not emp:
            flash('Employee not found.', 'error')
            return redirect(url_for('qm_employee_profiles'))

        # Parse JSON fields
        def parse_json(val):
            if not val:
                return []
            if isinstance(val, (list, dict)):
                return val
            try:
                return json.loads(val)
            except:
                return []

        emp['education_data'] = parse_json(emp.get('education'))
        emp['trainings_data'] = parse_json(emp.get('trainings'))
        emp['experience_data'] = parse_json(emp.get('experience'))
        emp['skills_data'] = parse_json(emp.get('skills'))

        return render_template('qm_profile_print.html', emp=emp, user=session)
    except Exception as e:
        print(f"Error downloading profile: {e}")
        flash('Error generating profile document.', 'error')
        return redirect(url_for('qm_employee_profiles'))


if __name__ == '__main__':

    # Trigger hot reload for templates
    app.config['TEMPLATES_AUTO_RELOAD'] = True
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
# trigger reload
