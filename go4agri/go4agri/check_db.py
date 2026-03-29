import mysql.connector
import os
from dotenv import load_dotenv

load_dotenv()

def check_schema():
    try:
        connection = mysql.connector.connect(
            user=os.getenv('DB_USER', 'root'),
            password=os.getenv('DB_PASSWORD'),
            host=os.getenv('DB_HOST', 'localhost'),
            database=os.getenv('DB_NAME', 'GoforAgri')
        )
        cursor = connection.cursor()
        
        cursor.execute("SHOW TABLES")
        tables = cursor.fetchall()
        print("Tables in GoforAgri database:")
        for (table_name,) in tables:
            print(f"\n--- Table: {table_name} ---")
            cursor.execute(f"DESCRIBE `{table_name}`")
            columns = cursor.fetchall()
            for col in columns:
                print(col)
        
        cursor.close()
        connection.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_schema()
