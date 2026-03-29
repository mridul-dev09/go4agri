from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory, send_file, jsonify
import os
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

app = Flask(__name__)
app.secret_key = 'go4agri_secret_key_2026'

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
    certified = []
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT a.id, a.company_name, a.program_type, a.scope, a.current_status,
                   a.created_at, a.updated_at,
                   u.full_name as client_name
            FROM applications a
            JOIN users u ON a.client_id = u.id
            WHERE a.status = 'CERTIFICATE_ISSUED'
            ORDER BY a.updated_at DESC
        """)
        certified = cursor.fetchall()
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Error fetching certified clients: {e}")
    return render_template('clients.html', certified=certified)

@app.route('/updates')
def updates():
    return render_template('updates.html')

@app.route('/appeal')
def appeal():
    return render_template('appeal.html')

@app.route('/complaints')
def complaints():
    return render_template('complaints.html')

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
    return redirect('/#certification-process')

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
        'Admin': 'db_admin.html',
        'CEO': 'db_ceo.html',
        'Client': 'db_client.html',
        'Accounts': 'db_accounts.html',
        'Initial reviewer': 'db_employee.html',
        'Inspection planner': 'db_employee.html',
        'Auditor': 'db_employee.html',
        'Technical reviewer': 'db_employee.html',
        'Certifier': 'db_employee.html',
        'Recruiter': 'db_recruiter.html'
    }
    print(f"DEBUG: Dashboard requested for {designation}")
    template = template_map.get(designation, 'db_base.html')
    print(f"DEBUG: Using template {template}")
    
    enquiries = []
    apps = []
    all_applications = []
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
                SELECT a.*, u.full_name as lead_auditor_name 
                FROM applications a
                LEFT JOIN users u ON a.lead_auditor_id = u.id
                WHERE a.status = 'FINAL_PAYMENT_VERIFIED'
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
            # Role-based workflow filtering
            if designation == 'Admin':
                cursor.execute("""
                    SELECT a.*, u.full_name as lead_auditor_name 
                    FROM applications a
                    LEFT JOIN users u ON a.lead_auditor_id = u.id
                    WHERE a.status IN ('APPLICATION_RECEIVED', 'PARTIAL_PAYMENT_VERIFIED', 'REJECTED')
                    ORDER BY CASE a.status WHEN 'REJECTED' THEN 0 ELSE 1 END, a.created_at DESC
                """)
                apps = cursor.fetchall()
            elif designation == 'Accounts':
                cursor.execute("""
                    SELECT a.*, u.full_name as client_name 
                    FROM applications a
                    JOIN users u ON a.client_id = u.id
                    WHERE a.status IN ('CONTRACT_UPLOADED', 'FINAL_PAYMENT_SUBMITTED')
                    ORDER BY a.created_at DESC
                """)
                apps = cursor.fetchall()
            elif designation == 'Initial reviewer':
                cursor.execute("""
                    SELECT a.*, u.full_name as lead_auditor_name 
                    FROM applications a
                    LEFT JOIN users u ON a.lead_auditor_id = u.id
                    WHERE a.status = 'DOCUMENT_REVIEW'
                    ORDER BY a.created_at DESC
                """)
                apps = cursor.fetchall()
            elif designation == 'Inspection planner':
                cursor.execute("""
                    SELECT a.*, u.full_name as lead_auditor_name 
                    FROM applications a
                    LEFT JOIN users u ON a.lead_auditor_id = u.id
                    WHERE a.status = 'INSPECTION_PLANNING'
                    ORDER BY a.created_at DESC
                """)
                apps = cursor.fetchall()
                cursor.execute("SELECT id, full_name, email FROM users WHERE designation = 'Auditor'")
                auditors = cursor.fetchall()
            elif designation == 'Auditor':
                cursor.execute("""
                    SELECT a.*, u.full_name as lead_auditor_name 
                    FROM applications a
                    LEFT JOIN users u ON a.lead_auditor_id = u.id
                    WHERE a.status = 'AUDIT_IN_PROGRESS'
                    ORDER BY a.created_at DESC
                """)
                apps = cursor.fetchall()
            elif designation == 'Technical reviewer':
                cursor.execute("""
                    SELECT a.*, u.full_name as lead_auditor_name 
                    FROM applications a
                    LEFT JOIN users u ON a.lead_auditor_id = u.id
                    WHERE a.status = 'TECHNICAL_REVIEW'
                    ORDER BY a.created_at DESC
                """)
                apps = cursor.fetchall()
            elif designation in ['Certifier', 'CEO']:
                cursor.execute("""
                    SELECT a.*, u.full_name as lead_auditor_name 
                    FROM applications a
                    LEFT JOIN users u ON a.lead_auditor_id = u.id
                    WHERE a.status = 'FINAL_PAYMENT_VERIFIED'
                    ORDER BY a.created_at DESC
                """)
                apps = cursor.fetchall()
            else:
                cursor.execute("""
                    SELECT a.*, u.full_name as lead_auditor_name 
                    FROM applications a
                    LEFT JOIN users u ON a.lead_auditor_id = u.id
                    ORDER BY a.created_at DESC LIMIT 10
                """)
                apps = cursor.fetchall()

        # Shared Data for Management (CEO & Admin)
        if designation in ['CEO', 'Admin']:
            cursor.execute("SELECT * FROM enquiries ORDER BY created_at DESC")
            enquiries = cursor.fetchall()
            cursor.execute("SELECT id, full_name, email, created_at FROM users WHERE designation = 'Client' ORDER BY created_at DESC")
            registered_clients = cursor.fetchall()
            cursor.execute("""
                SELECT a.*, u.full_name as lead_auditor_name
                FROM applications a
                LEFT JOIN users u ON a.lead_auditor_id = u.id
                ORDER BY a.created_at DESC
            """)
            all_applications = cursor.fetchall()

        if designation == 'Recruiter':
            cursor.execute("SELECT * FROM job_applications ORDER BY created_at DESC")
            job_applications = cursor.fetchall()
            
            if designation == 'Recruiter':
                cursor.execute("SELECT * FROM job_applications ORDER BY created_at DESC")
                job_applications = cursor.fetchall()
            cursor.execute("SELECT id, full_name, email, created_at FROM users WHERE designation = 'Client' ORDER BY created_at DESC")
            registered_clients = cursor.fetchall()
            # Fetch ALL applications (all statuses) for the Registered Clients dropdown
            cursor.execute("""
                SELECT a.*, u.full_name as lead_auditor_name
                FROM applications a
                LEFT JOIN users u ON a.lead_auditor_id = u.id
                ORDER BY a.created_at DESC
            """)
            all_applications = cursor.fetchall()

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
            
        # Fetch unread message count for badge
        unread_count = 0
        if 'user_id' in session:
            cursor.execute("SELECT COUNT(*) as count FROM messages WHERE receiver_id = %s AND is_read = FALSE", (session['user_id'],))
            unread_count = cursor.fetchone()['count']

        print(f"DEBUG: Designation={designation}, Apps Found={len(apps)}")
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"DEBUG: Error fetching dashboard data: {e}")
        
    return render_template(template, user=session, applications=apps, all_applications=all_applications, enquiries=enquiries, activities=activities, tasks=tasks, employees=employees, documents=documents, registered_clients=registered_clients, unread_count=unread_count, job_applications=job_applications, auditors=auditors)

@app.route('/submit-application', methods=['POST'])
def submit_application():
    company_name = request.form.get('company_name')
    program_type = request.form.get('program_type')
    scope = request.form.get('scope')
    
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
                
            cursor.execute(
                "INSERT INTO applications (client_id, company_name, program_type, scope, status) VALUES (%s, %s, %s, %s, 'PENDING_CONTRACT_QUOTATION')",
                (session['user_id'], company_name, program_type, scope)
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
        print(f"Error submitting app: {e}")
        flash('Error submitting application.', 'error')
        return redirect(url_for('apply'))

@app.route('/submit-contract/<int:app_id>', methods=['POST'])
def submit_contract(app_id):
    if 'user_id' not in session or session.get('designation') != 'Client':
        flash('Unauthorized access.', 'error')
        return redirect(url_for('client_login'))
        
    contract_file = request.files.get('contract')
    receipt_file = request.files.get('payment_receipt')
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
        
        # Update application status
        cursor.execute(
            "UPDATE applications SET status = 'CONTRACT_UPLOADED', partial_payment_txn = %s WHERE id = %s",
            (txn_no, app_id)
        )
        
        conn.commit()
        cursor.close()
        conn.close()
        
        log_activity(session['user_id'], 'UPLOAD_CONTRACT_PAYMENT', f"Uploaded contract, receipt and txn {txn_no} for app {app_id}")
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

@app.route('/download-sample-contract')
def download_sample_contract():
    filename = 'Professional Service Contract.pdf'
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=True)

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
        'DOCUMENT_REVIEW': { 'Initial reviewer': 'INSPECTION_PLANNING' },
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
        cursor = conn.cursor()
        
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
            client_id = result[0] if result else None
            
            if client_id:
                cursor.execute(
                    "INSERT INTO documents (client_id, application_id, filename, filepath, category) VALUES (%s, %s, %s, %s, 'AUDIT_REPORT')",
                    (client_id, app_id, filename, filename)
                )

        # Inspection Planner specific logic: Must upload planning doc if not rejecting
        elif role == 'Inspection planner' and current_status == 'INSPECTION_PLANNING' and action != 'reject':
            plan_file = request.files.get('planning_doc')
            if not plan_file or plan_file.filename == '':
                flash('Planning document is mandatory for submission.', 'error')
                return redirect(url_for('dashboard'))
                
            auditor_id = request.form.get('auditor_id')
            if not auditor_id:
                flash('Assigning an auditor is mandatory.', 'error')
                return redirect(url_for('dashboard'))
            
            filename = secure_filename(f"planning_doc_{app_id}_{plan_file.filename}")
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            plan_file.save(filepath)
            
            # Fetch client_id for document entry
            cursor.execute("SELECT client_id FROM applications WHERE id = %s", (app_id,))
            result = cursor.fetchone()
            client_id = result[0] if result else None
            
            if client_id:
                cursor.execute(
                    "INSERT INTO documents (client_id, application_id, filename, filepath, category) VALUES (%s, %s, %s, %s, 'PLANNING_DOCUMENT')",
                    (client_id, app_id, filename, filename)
                )
                
            # Update application with assigned auditor
            cursor.execute("UPDATE applications SET lead_auditor_id = %s WHERE id = %s", (auditor_id, app_id))
        
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
        
    return redirect(url_for('dashboard'))

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
        cursor.execute("""
            UPDATE applications 
            SET plan_submission_days = %s, 
                draft_asr_days = %s, 
                audit_start_date = %s, 
                audit_end_date = %s 
            WHERE id = %s
        """, (plan_days, asr_days, start_date or None, end_date or None, app_id))
        conn.commit()
        cursor.close()
        conn.close()
        log_activity(session['user_id'], 'UPDATE_AUDIT_DETAILS', f"Updated audit details for application {app_id}")
        flash('Audit details updated successfully.', 'success')
    except Exception as e:
        print(f"Error updating audit details: {e}")
        flash('Error updating audit details.', 'error')
        
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
            cursor.execute(
                "INSERT INTO users (full_name, email, designation, password) VALUES (%s, %s, %s, %s)",
                (full_name, email, 'Client', hashed_pw)
            )
            client_id = cursor.lastrowid
            flash_msg = f'Successfully registered client {full_name}.'
            
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
            flash_msg = f'User with email {email} already exists. Enquiry linked to existing account.'
            
        if enquiry_id:
            cursor.execute("SELECT company_name, program_type FROM enquiries WHERE id = %s", (enquiry_id,))
            enq = cursor.fetchone()
            if enq:
                company_name, program_type = enq
                cursor.execute("SELECT id FROM applications WHERE client_id = %s AND program_type = %s", (client_id, program_type))
                if cursor.fetchone() is None:
                    cursor.execute(
                        "INSERT INTO applications (client_id, company_name, program_type, status) VALUES (%s, %s, %s, 'PENDING_CONTRACT_QUOTATION')",
                        (client_id, company_name, program_type)
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
        cursor.execute("DELETE FROM enquiries WHERE id = %s", (enquiry_id,))
        conn.commit()
        cursor.close()
        conn.close()
        log_activity(session['user_id'], 'DELETE_ENQUIRY', f"Deleted enquiry {enquiry_id}")
        flash('Enquiry deleted successfully.', 'success')
    except Exception as e:
        print(f"Error deleting enquiry: {e}")
        flash('Error deleting enquiry.', 'error')
        
    return redirect(url_for('dashboard'))

@app.route('/delete-application/<int:app_id>', methods=['POST'])
def delete_application(app_id):
    if 'user_id' not in session or session.get('designation') not in ['CEO', 'Admin']:
        flash('Unauthorized access.', 'error')
        return redirect(url_for('home'))
        
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM applications WHERE id = %s", (app_id,))
        conn.commit()
        cursor.close()
        conn.close()
        log_activity(session['user_id'], 'DELETE_APPLICATION', f"Deleted application {app_id}")
        flash('Application deleted successfully.', 'success')
    except Exception as e:
        print(f"Error deleting application: {e}")
        # Could be foreign key constraint from tasks or documents, etc.
        flash('Error deleting application. It may be linked to tasks or documents.', 'error')
        
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
            if task['due_date']:
                color = '#0072bc' # default info
                if task['status'] == 'COMPLETED':
                    color = '#27ae60' # success
                elif task['priority'] == 'HIGH':
                    color = '#e74c3c' # danger
                elif task['priority'] == 'MEDIUM':
                    color = '#f39c12' # warning
                    
                events.append({
                    'id': str(task['id']),
                    'title': task['title'] if designation in ['CEO', 'Admin'] else task['title'],
                    'start': task['due_date'].strftime('%Y-%m-%d'),
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
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Fetch messages based on active tab
        if active_tab == 'sent':
            cursor.execute("""
                SELECT m.*, u.full_name as receiver_name 
                FROM messages m
                JOIN users u ON m.receiver_id = u.id
                WHERE m.sender_id = %s
                ORDER BY m.created_at DESC
            """, (user_id,))
        else: # Default to inbox
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
                
        # Fetch contacts (all employees, and clients if CEO/Admin/Recruiter)
        if session['designation'] in ['CEO', 'Admin', 'Recruiter']:
            cursor.execute("SELECT id, full_name, designation FROM users WHERE id != %s", (user_id,))
        else:
            cursor.execute("SELECT id, full_name, designation FROM users WHERE designation != 'Client' AND id != %s", (user_id,))
        contacts = cursor.fetchall()
        
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Error fetching messages: {e}")
        
    return render_template('db_messages.html', user=session, messages=msgs, selected_message=selected_msg, contacts=contacts, active_tab=active_tab)

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
        
        # Notify CEO (ID 7) Only (as requested: "messages only ceo")
        system_user_id = 1
        targets = [7] 
        
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
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Insert into job_applications table for Recruiter Dashboard
        cursor.execute(
            "INSERT INTO job_applications (full_name, email, phone, position, resume_path) VALUES (%s, %s, %s, %s, %s)",
            (name, email, phone, position, filename)
        )
        
        # Send message to CEO
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
    allowed_roles = ['CEO', 'Admin', 'QA', 'Initial reviewer', 'Inspection planner', 'Auditor', 'Technical reviewer', 'Certifier']
    if 'user_id' not in session or session.get('designation') not in allowed_roles:
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
            SELECT a.*, u.full_name as lead_auditor_name 
            FROM applications a
            LEFT JOIN users u ON a.lead_auditor_id = u.id
            WHERE a.client_id = %s 
            ORDER BY a.created_at DESC
        """, (client_id,))
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
        
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Fetch tasks for this auditor, joining with applications for company info
        cursor.execute("""
            SELECT t.id, t.title, t.due_date, t.status, a.company_name, t.assignee_id 
            FROM tasks t
            LEFT JOIN applications a ON t.application_id = a.id
            WHERE t.assignee_id = %s
        """, (session['user_id'],))
        
        tasks = cursor.fetchall()
        cursor.close()
        conn.close()
        
        # Format for FullCalendar
        events = []
        for task in tasks:
            if not task['due_date']:
                continue
                
            # Determine color based on status and date
            color = '#3788d8' # Default Blue (Pending)
            if task['status'] == 'COMPLETED':
                color = '#28a745' # Green
            elif task['status'] == 'CANCELLED':
                color = '#dc3545' # Red
            elif task['due_date'] < datetime.now().date() and task['status'] not in ['COMPLETED', 'CANCELLED']:
                color = '#dc3545' # Red (Overdue)
            
            events.append({
                'id': task['id'],
                'title': f"{task['title']} - {task['company_name'] if task['company_name'] else 'Internal'}",
                'start': task['due_date'].strftime('%Y-%m-%d'),
                'color': color,
                'extendedProps': {
                    'status': task['status'],
                    'company': task['company_name'] or 'N/A',
                    'raw_title': task['title']
                }
            })
            
        return jsonify(events)
    except Exception as e:
        print(f"Error fetching tasks API: {e}")
        return jsonify({'error': str(e)}), 500

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

if __name__ == '__main__':
    # Trigger hot reload for templates
    app.config['TEMPLATES_AUTO_RELOAD'] = True
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
