from db_config import get_db_connection
from werkzeug.security import generate_password_hash

try:
    conn = get_db_connection()
    cursor = conn.cursor()
    hashed_pw = generate_password_hash('password123')
    auditors = [
        ('Auditor One', 'auditor1@go4agri.co.in', 'Auditor', hashed_pw),
        ('Auditor Two', 'auditor2@go4agri.co.in', 'Auditor', hashed_pw),
        ('Auditor Three', 'auditor3@go4agri.co.in', 'Auditor', hashed_pw),
        ('Auditor Four', 'auditor4@go4agri.co.in', 'Auditor', hashed_pw),
        ('Auditor Five', 'auditor5@go4agri.co.in', 'Auditor', hashed_pw)
    ]
    cursor.execute("SELECT email FROM users WHERE designation = 'Auditor'")
    existing_emails = [r[0] for r in cursor.fetchall()]
    to_insert = [a for a in auditors if a[1] not in existing_emails]
    cursor.executemany("INSERT INTO users (full_name, email, designation, password) VALUES (%s, %s, %s, %s)", to_insert)
    conn.commit()
    print(f'Inserted {len(to_insert)} auditors.')
    cursor.close()
    conn.close()
except Exception as e:
    print(f'Error: {e}')
