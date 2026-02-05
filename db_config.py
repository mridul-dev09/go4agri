import os
import mysql.connector
from dotenv import load_dotenv

load_dotenv()

def get_db_connection():
    try:
        connection = mysql.connector.connect(
            user=os.getenv('DB_USER', 'root'),
            password=os.getenv('DB_PASSWORD'),
            host=os.getenv('DB_HOST', 'localhost'),
            database=os.getenv('DB_NAME', 'GoforAgri')
        )
        return connection
    except mysql.connector.Error as err:
        print(f"Error connecting to database: {err}")
        raise err
