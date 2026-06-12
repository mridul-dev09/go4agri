import requests
from io import BytesIO
import mysql.connector

def get_db_conn():
    return mysql.connector.connect(
        user='root',
        password='MySQL@091610',
        host='localhost',
        database='GoforAgri'
    )

try:
    print("--- STARTING WORKFLOW INTEGRATION VERIFICATION ---")
    
    # 1. Start session
    session = requests.Session()
    
    # 2. Login as Initial Reviewer
    print("\n1. Logging in as Initial Reviewer...")
    login_response = session.post('http://localhost:5000/login', data={
        'email': 'initial@go4agri.co.in',
        'password': 'employee123',
        'login_type': 'employee'
    }, allow_redirects=False)
    print("   Response status:", login_response.status_code)
    
    # Ensure app 7 is reset to DOCUMENT_REVIEW first
    conn = get_db_conn()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("UPDATE applications SET status = 'DOCUMENT_REVIEW' WHERE id = 7")
    cursor.execute("DELETE FROM documents WHERE application_id = 7 AND filename LIKE '%dummy%'")
    conn.commit()
    print("   Application 7 reset to DOCUMENT_REVIEW.")
    
    # 3. Test Initial Reviewer: Upload & Send
    print("\n2. Testing Initial Reviewer Upload & Send (Single step)...")
    file_data = {
        'review_templates': ('dummy_test_template.xlsx', BytesIO(b"dummy template content"), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    }
    upload_response = session.post(
        'http://localhost:5000/upload-review-templates/7',
        files=file_data,
        data={'submit_action': 'upload_and_send'},
        allow_redirects=False
    )
    print("   Upload & Send response status:", upload_response.status_code)
    print("   Location header:", upload_response.headers.get('Location'))
    
    # Check DB status
    cursor.execute("SELECT status FROM applications WHERE id = 7")
    app_data = cursor.fetchone()
    print("   Application 7 status in DB:", app_data['status'])
    assert app_data['status'] == 'CLIENT_DOCUMENT_SUBMISSION_PENDING', f"Expected CLIENT_DOCUMENT_SUBMISSION_PENDING, got {app_data['status']}"
    
    # 4. Login as Client
    print("\n3. Logging in as Client (Benny)...")
    client_session = requests.Session()
    client_login_response = client_session.post('http://localhost:5000/login', data={
        'email': 'benny@gmail.com',
        'password': 'client123',
        'login_type': 'client'
    }, allow_redirects=False)
    print("   Response status:", client_login_response.status_code)
    
    # 5. Test Client: Upload & Submit
    print("\n4. Testing Client Upload & Submit (Single step)...")
    client_file_data = {
        'client_review_docs': ('dummy_test_filled_doc.xlsx', BytesIO(b"dummy filled content"), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    }
    client_response = client_session.post(
        'http://localhost:5000/submit-client-review-documents/7',
        files=client_file_data,
        data={'action': 'upload_and_submit'},
        allow_redirects=True
    )
    print("   Upload & Submit response status:", client_response.status_code)
    import re
    flashes = re.findall(r'class="flash-item\s+[^"]*">\s*(.*?)\s*</div>', client_response.text, re.DOTALL)
    print("   Flash messages received:", flashes)
    
    # Check DB status
    conn.commit()
    cursor.execute("SELECT status FROM applications WHERE id = 7")
    app_data = cursor.fetchone()
    print("   Application 7 status in DB:", app_data['status'])
    assert app_data['status'] == 'CLIENT_DOCUMENT_SUBMITTED', f"Expected CLIENT_DOCUMENT_SUBMITTED, got {app_data['status']}"
    
    # 6. Test Client: Submit without selecting files (Bypassing browser validation)
    print("\n5. Testing Client Submit only (when files already exist)...")
    # Change status back to CLIENT_DOCUMENT_SUBMISSION_PENDING
    cursor.execute("UPDATE applications SET status = 'CLIENT_DOCUMENT_SUBMISSION_PENDING' WHERE id = 7")
    conn.commit()
    
    # Send request with action=submit and empty files
    client_response_empty = client_session.post(
        'http://localhost:5000/submit-client-review-documents/7',
        data={'action': 'submit'},
        allow_redirects=True
    )
    print("   Submit only response status:", client_response_empty.status_code)
    flashes_empty = re.findall(r'class="flash-item\s+[^"]*">\s*(.*?)\s*</div>', client_response_empty.text, re.DOTALL)
    print("   Flash messages received (empty):", flashes_empty)
    
    # Check DB status
    conn.commit()
    cursor.execute("SELECT status FROM applications WHERE id = 7")
    app_data = cursor.fetchone()
    print("   Application 7 status in DB:", app_data['status'])
    assert app_data['status'] == 'CLIENT_DOCUMENT_SUBMITTED', f"Expected CLIENT_DOCUMENT_SUBMITTED, got {app_data['status']}"
    
    # 7. Clean up
    print("\n6. Cleaning up database state...")
    cursor.execute("UPDATE applications SET status = 'DOCUMENT_REVIEW' WHERE id = 7")
    cursor.execute("DELETE FROM documents WHERE application_id = 7 AND (filename LIKE '%dummy_test_template%' OR filename LIKE '%dummy_test_filled_doc%')")
    conn.commit()
    print("   Cleanup completed successfully.")
    
    cursor.close()
    conn.close()
    
    print("\n--- ALL VERIFICATIONS PASSED SUCCESSFULLY! ---")

except Exception as e:
    print("\nVerification failed:", e)
