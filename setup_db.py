import mysql.connector
import os
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash

load_dotenv()

def setup_database():
    try:
        connection = mysql.connector.connect(
            user=os.getenv('DB_USER', 'root'),
            password=os.getenv('DB_PASSWORD'),
            host=os.getenv('DB_HOST', 'localhost')
        )
        cursor = connection.cursor()
        
        # Create database if not exists
        db_name = os.getenv('DB_NAME', 'GoforAgri')
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {db_name}")
        cursor.execute(f"USE {db_name}")
        
        # Create users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                email VARCHAR(255) UNIQUE NOT NULL,
                password VARCHAR(255) NOT NULL,
                designation VARCHAR(100) NOT NULL,
                full_name VARCHAR(255) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Create applications table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS applications (
                id INT AUTO_INCREMENT PRIMARY KEY,
                client_id INT NOT NULL,
                company_name VARCHAR(255) NOT NULL,
                program_type VARCHAR(100) NOT NULL,
                status VARCHAR(100) DEFAULT 'PENDING_INITIAL_REVIEW',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                FOREIGN KEY (client_id) REFERENCES users(id)
            )
        """)

        # Create enquiries table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS enquiries (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                email VARCHAR(255) NOT NULL,
                phone VARCHAR(20) NOT NULL,
                program_type VARCHAR(100) NOT NULL,
                message TEXT,
                status VARCHAR(50) DEFAULT 'NEW',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        designations = [
            ('CEO', 'ceo@go4agri.com', 'ceo123'),
            ('Admin', 'admin@go4agri.com', 'admin123'),
            ('QA', 'qa@go4agri.com', 'qa123'),
            ('Initial reviewer', 'initial@go4agri.com', 'initial123'),
            ('Evaluator', 'evaluator@go4agri.com', 'evaluator123'),
            ('Technical reviewer', 'technical@go4agri.com', 'technical123'),
            ('Certification officer', 'officer@go4agri.com', 'officer123'),
            ('Certifier', 'certifier@go4agri.com', 'certifier123'),
            ('Scheduler', 'scheduler@go4agri.com', 'scheduler123'),
            ('Auditor', 'auditor@go4agri.com', 'auditor123'),
            ('Client', 'client@test.com', 'client123')
        ]
        
        for desig, email, password in designations:
            hashed_password = generate_password_hash(password)
            name = f"{desig} User"
            
            # Check if user exists
            cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
            if cursor.fetchone() is None:
                cursor.execute(
                    "INSERT INTO users (email, password, designation, full_name) VALUES (%s, %s, %s, %s)",
                    (email, hashed_password, desig, name)
                )
                print(f"Created user: {email} ({desig})")
            else:
                print(f"User already exists: {email}")
        
        connection.commit()
        cursor.close()
        connection.close()
        print("Database setup complete.")
        
    except mysql.connector.Error as err:
        print(f"Error: {err}")

if __name__ == "__main__":
    setup_database()
