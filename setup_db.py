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

        # Create activity_log table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS activity_log (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT,
                action VARCHAR(100) NOT NULL,
                details TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
            )
        """)

        # Create tasks table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INT AUTO_INCREMENT PRIMARY KEY,
                allotter_id INT NOT NULL,
                assignee_id INT NOT NULL,
                application_id INT,
                title VARCHAR(255) NOT NULL,
                description TEXT,
                priority ENUM('LOW', 'MEDIUM', 'HIGH') DEFAULT 'MEDIUM',
                status ENUM('PENDING', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED') DEFAULT 'PENDING',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                FOREIGN KEY (allotter_id) REFERENCES users(id),
                FOREIGN KEY (assignee_id) REFERENCES users(id),
                FOREIGN KEY (application_id) REFERENCES applications(id) ON DELETE CASCADE
            )
        """)

        # Create messages table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INT AUTO_INCREMENT PRIMARY KEY,
                sender_id INT NOT NULL,
                receiver_id INT NOT NULL,
                subject VARCHAR(255),
                body TEXT NOT NULL,
                is_read BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (sender_id) REFERENCES users(id),
                FOREIGN KEY (receiver_id) REFERENCES users(id)
            )
        """)

        # Create documents table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id INT AUTO_INCREMENT PRIMARY KEY,
                client_id INT NOT NULL,
                application_id INT,
                category VARCHAR(100) NOT NULL,
                filename VARCHAR(255) NOT NULL,
                filepath VARCHAR(255) NOT NULL,
                uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (client_id) REFERENCES users(id),
                FOREIGN KEY (application_id) REFERENCES applications(id) ON DELETE CASCADE
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
