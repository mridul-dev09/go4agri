"""
Migration: Add current_status column to applications table.
Run this script once to apply the schema change.
"""
from db_config import get_db_connection

def migrate():
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Check if column already exists
        cursor.execute("SHOW COLUMNS FROM applications LIKE 'current_status'")
        if cursor.fetchone():
            print("ℹ️  Column 'current_status' already exists. Skipping.")
            return

        # Add current_status column
        cursor.execute("""
            ALTER TABLE applications 
            ADD COLUMN current_status VARCHAR(100) DEFAULT 'Active'
        """)
        conn.commit()
        print("✅ Migration successful: 'current_status' column added to applications.")
    except Exception as e:
        print(f"❌ Migration failed: {e}")
    finally:
        cursor.close()
        conn.close()

if __name__ == '__main__':
    migrate()
