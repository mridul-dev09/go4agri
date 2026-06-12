"""
Script to reset all employee passwords to 'employee123'
Run this from the go4agri directory where app.py is located.
"""

import os
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash
from db_config import get_db_connection

load_dotenv()

NEW_PASSWORD = "employee123"
hashed_password = generate_password_hash(NEW_PASSWORD)

try:
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Fetch all non-client users (employees only)
    cursor.execute("SELECT id, full_name, email, designation FROM users WHERE designation != 'Client'")
    employees = cursor.fetchall()

    if not employees:
        print("No employee accounts found.")
    else:
        print(f"Found {len(employees)} employee(s). Resetting passwords...\n")

        # Reset passwords
        cursor.execute(
            "UPDATE users SET password = %s WHERE designation != 'Client'",
            (hashed_password,)
        )
        conn.commit()

        print("Password reset successful for the following employees:\n")
        print(f"{'ID':<5} {'Full Name':<30} {'Email':<40} {'Designation'}")
        print("-" * 100)
        for emp in employees:
            print(f"{emp['id']:<5} {emp['full_name']:<30} {emp['email']:<40} {emp['designation']}")

        print(f"\n✅ All {len(employees)} employee passwords have been reset to: {NEW_PASSWORD}")

    cursor.close()
    conn.close()

except Exception as e:
    print(f"❌ Error: {e}")
