import mysql.connector
from db_config import get_db_connection

def migrate():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Create client_feedback table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS client_feedback (
                id INT AUTO_INCREMENT PRIMARY KEY,
                client_id INT NOT NULL,
                message TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (client_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        # Create client_appeals table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS client_appeals (
                id INT AUTO_INCREMENT PRIMARY KEY,
                client_id INT NOT NULL,
                subject VARCHAR(255) NOT NULL,
                description TEXT NOT NULL,
                type ENUM('Appeal', 'Complaint') NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (client_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        conn.commit()
        print("Migration successful: client_feedback and client_appeals tables created.")
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Migration error: {e}")

if __name__ == "__main__":
    migrate()
