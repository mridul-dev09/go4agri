import mysql.connector
import os
from dotenv import load_dotenv

load_dotenv()

def migrate():
    try:
        connection = mysql.connector.connect(
            user=os.getenv('DB_USER', 'root'),
            password=os.getenv('DB_PASSWORD'),
            host=os.getenv('DB_HOST', 'localhost'),
            database=os.getenv('DB_NAME', 'GoforAgri')
        )
        cursor = connection.cursor()
        
        print("Running migrations...")
        
        alter_queries = [
            "ALTER TABLE applications ADD COLUMN plan_submission_days INT DEFAULT 0",
            "ALTER TABLE applications ADD COLUMN draft_asr_days INT DEFAULT 0",
            "ALTER TABLE applications ADD COLUMN audit_start_date DATE NULL",
            "ALTER TABLE applications ADD COLUMN audit_end_date DATE NULL",
            "ALTER TABLE applications ADD COLUMN restart_count INT DEFAULT 0",
        ]
        
        for query in alter_queries:
            try:
                cursor.execute(query)
                print(f"Executed: {query}")
            except mysql.connector.Error as err:
                if err.errno == 1060: # Column already exists
                    print(f"Column already exists, skipping.")
                else:
                    print(f"Error executing: {err}")
        
        # Create application_restarts table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS application_restarts (
                id INT AUTO_INCREMENT PRIMARY KEY,
                application_id INT NOT NULL,
                restarted_by INT NOT NULL,
                restart_count INT DEFAULT 1,
                rejection_reason TEXT NOT NULL,
                restarted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (application_id) REFERENCES applications(id),
                FOREIGN KEY (restarted_by) REFERENCES users(id)
            )
        """)
        print("Created/verified 'application_restarts' table.")
        
        connection.commit()
        cursor.close()
        connection.close()
        print("Migration completed successfully.")
    except Exception as e:
        print(f"Migration failed: {e}")

if __name__ == "__main__":
    migrate()
