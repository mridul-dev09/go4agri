import mysql.connector
import os
from dotenv import load_dotenv

load_dotenv()

def migrate_db():
    try:
        connection = mysql.connector.connect(
            user=os.getenv('DB_USER', 'root'),
            password=os.getenv('DB_PASSWORD'),
            host=os.getenv('DB_HOST', 'localhost'),
            database=os.getenv('DB_NAME', 'GoforAgri')
        )
        cursor = connection.cursor()

        try:
            cursor.execute("ALTER TABLE applications ADD COLUMN scope VARCHAR(255)")
            print("Added 'scope' column to applications table.")
        except Exception as e:
            print(f"applications table error: {e}")

        try:
            cursor.execute("ALTER TABLE enquiries ADD COLUMN scope VARCHAR(255)")
            print("Added 'scope' column to enquiries table.")
        except Exception as e:
            print(f"enquiries table error: {e}")

        connection.commit()
        cursor.close()
        connection.close()
        print("Migration complete.")
    except Exception as e:
        print(f"Connection error: {e}")

if __name__ == "__main__":
    migrate_db()
