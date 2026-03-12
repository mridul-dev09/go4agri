import mysql.connector
import os
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash

load_dotenv()

def migrate_database():
    try:
        print("Connecting to database...")
        connection = mysql.connector.connect(
            user=os.getenv('DB_USER', 'root'),
            password=os.getenv('DB_PASSWORD'),
            host=os.getenv('DB_HOST', 'localhost'),
            database=os.getenv('DB_NAME', 'GoforAgri')
        )
        print("Connected!")
        cursor = connection.cursor()
        
        # 1. Update applications table schema
        print("Updating applications table schema...")
        columns_to_add = [
            ("signed_contract_path", "VARCHAR(512) DEFAULT NULL"),
            ("partial_payment_txn", "VARCHAR(100) DEFAULT NULL"),
            ("final_payment_txn", "VARCHAR(100) DEFAULT NULL"),
            ("payment_status", "VARCHAR(50) DEFAULT 'UNPAID'")
        ]
        
        for col_name, col_def in columns_to_add:
            try:
                cursor.execute(f"ALTER TABLE applications ADD COLUMN {col_name} {col_def}")
                print(f"Added column: {col_name}")
            except mysql.connector.Error as err:
                if err.errno == 1060: # Duplicate column name
                    print(f"Column {col_name} already exists.")
                else:
                    print(f"Error adding column {col_name}: {err}")

        # 2. Ensure all required roles/users exist
        print("\nEnsuring required user roles exist...")
        required_roles = [
            ("Admin", "admin@go4agri.com"),
            ("Accounts", "accounts@go4agri.com"),
            ("Initial reviewer", "reviewer@go4agri.com"),
            ("Inspection planner", "planner@go4agri.com"),
            ("Auditor", "auditor@go4agri.com"),
            ("Technical reviewer", "technical@go4agri.com"),
            ("Certifier", "certifier@go4agri.com"),
            ("CEO", "ceo@go4agri.com")
        ]
        
        print("Generating default password hash...")
        default_password = generate_password_hash("password123")
        print("Hash generated.")
        
        for role, email in required_roles:
            cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
            if cursor.fetchone():
                print(f"User with email {email} (Role: {role}) already exists.")
            else:
                cursor.execute(
                    "INSERT INTO users (full_name, email, designation, password) VALUES (%s, %s, %s, %s)",
                    (f"Test {role}", email, role, default_password)
                )
                print(f"Created user: {email} with role {role}")
        
        connection.commit()
        print("\nMigration completed successfully!")
        
        cursor.close()
        connection.close()
    except Exception as e:
        print(f"Migration error: {e}")

if __name__ == "__main__":
    migrate_database()
