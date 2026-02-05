import mysql.connector
import os
from dotenv import load_dotenv

load_dotenv()

def debug_app():
    try:
        connection = mysql.connector.connect(
            user=os.getenv('DB_USER', 'root'),
            password=os.getenv('DB_PASSWORD'),
            host=os.getenv('DB_HOST', 'localhost'),
            database=os.getenv('DB_NAME', 'GoforAgri')
        )
        cursor = connection.cursor(dictionary=True)
        print(f"Connected to: {connection.database}")
        
        cursor.execute("SELECT email, designation, full_name FROM users")
        users = cursor.fetchall()
        print("\nUsers in database:")
        for user in users:
            print(f" - {user['email']}: Designation='{user['designation']}'")
            
        cursor.execute("SELECT id, name, status FROM enquiries")
        enq = cursor.fetchall()
        print("\nEnquiries in database:")
        for e in enq:
            print(f" - ID={e['id']}, Name='{e['name']}', Status='{e['status']}'")
            
        cursor.close()
        connection.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    debug_app()
