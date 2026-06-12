from db_config import get_db_connection

def update_db():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if column exists
        cursor.execute("SHOW COLUMNS FROM applications LIKE 'post_cert_status'")
        result = cursor.fetchone()
        
        if not result:
            print("Adding post_cert_status column to applications table...")
            cursor.execute("ALTER TABLE applications ADD COLUMN post_cert_status ENUM('Active', 'Surrender', 'Withdraw', 'Suspended') DEFAULT NULL")
            conn.commit()
            print("Column added successfully.")
        else:
            print("Column already exists.")
            
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    update_db()
