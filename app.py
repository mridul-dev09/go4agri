from flask import Flask, render_template, request, redirect, url_for, flash, session
import os
from werkzeug.security import check_password_hash, generate_password_hash
from db_config import get_db_connection
import pandas as pd
import io

app = Flask(__name__)
app.secret_key = 'go4agri_secret_key_2026'

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
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        if designation == 'Client':
            cursor.execute("SELECT * FROM applications WHERE client_id = %s ORDER BY created_at DESC", (session['user_id'],))
        elif designation == 'CEO':
            cursor.execute("SELECT * FROM applications ORDER BY created_at DESC")
            apps = cursor.fetchall()
            cursor.execute("SELECT * FROM enquiries ORDER BY created_at DESC")
            enquiries = cursor.fetchall()
            print(f"DEBUG: Fetched {len(enquiries)} enquiries for CEO")
        elif designation == 'Admin':
            cursor.execute("SELECT * FROM applications WHERE status = 'PENDING_ADMIN_REVIEW' ORDER BY created_at DESC")
        elif designation == 'QA':
            cursor.execute("SELECT * FROM applications WHERE status = 'PENDING_QA_REVIEW' ORDER BY created_at DESC")
        elif designation == 'Initial reviewer':
            cursor.execute("SELECT * FROM applications WHERE status = 'PENDING_INITIAL_REVIEW' ORDER BY created_at DESC")
        elif designation == 'Evaluator':
            cursor.execute("SELECT * FROM applications WHERE status = 'PENDING_EVALUATION' ORDER BY created_at DESC")
        elif designation == 'Technical reviewer':
            cursor.execute("SELECT * FROM applications WHERE status = 'PENDING_TECHNICAL_REVIEW' ORDER BY created_at DESC")
        elif designation == 'Certification officer':
            cursor.execute("SELECT * FROM applications WHERE status = 'PENDING_CERTIFICATION_OFFICER' ORDER BY created_at DESC")
        elif designation == 'Certifier':
            cursor.execute("SELECT * FROM applications WHERE status = 'PENDING_CERTIFIER_APPROVAL' ORDER BY created_at DESC")
        else:
            cursor.execute("SELECT * FROM applications ORDER BY created_at DESC LIMIT 5")
            
        if designation not in ['CEO']:
            apps = cursor.fetchall()
            
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"DEBUG: Error fetching dashboard data: {e}")
        
    return render_template(template, user=session, applications=apps, enquiries=enquiries)

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
    except Exception as e:
        print(f"Error submitting enquiry: {e}")
        flash('An error occurred. Please try again later.', 'error')
        
    return redirect(url_for('certification_schemes'))

@app.route('/update-application-status/<int:app_id>', methods=['POST'])
def update_application_status(app_id):
    if 'user_id' not in session:
        return redirect(url_for('employee_login'))
        
    role = session.get('designation')
    
    # Define status flow
    flow = {
        'CEO': 'PENDING_ADMIN_REVIEW',
        'Admin': 'PENDING_QA_REVIEW',
        'QA': 'PENDING_INITIAL_REVIEW',
        'Initial reviewer': 'PENDING_EVALUATION',
        'Evaluator': 'PENDING_TECHNICAL_REVIEW',
        'Technical reviewer': 'PENDING_CERTIFICATION_OFFICER',
        'Certification officer': 'PENDING_CERTIFIER_APPROVAL',
        'Certifier': 'PENDING_TRANSACTION',
    }
    
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
    session.clear()
    return redirect(url_for('home'))

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

if __name__ == '__main__':
    app.run(debug=True)
