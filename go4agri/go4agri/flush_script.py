import sys
sys.path.append('.')
from db_config import get_db_connection

def count_tables():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SHOW TABLES")
    tables = cursor.fetchall()
    
    for t in tables:
        table_name = t[0]
        if table_name == 'users':
            cursor.execute(f"SELECT COUNT(*) FROM {table_name} WHERE designation = 'Client'")
            count = cursor.fetchone()[0]
            print(f"{table_name} (Clients): {count} rows")
    
    print("\n--- Deleting Registered Clients ---")
    cursor.execute("SET FOREIGN_KEY_CHECKS = 0;")
    cursor.execute("DELETE FROM users WHERE designation = 'Client';")
    cursor.execute("SET FOREIGN_KEY_CHECKS = 1;")
    conn.commit()
    print("Registered Clients flushed!")

    print("\n--- Remaining Counts ---")
    cursor.execute("SHOW TABLES")
    tables = cursor.fetchall()
    for t in tables:
        table_name = t[0]
        if table_name == 'users':
            cursor.execute(f"SELECT COUNT(*) FROM {table_name} WHERE designation = 'Client'")
            count = cursor.fetchone()[0]
            print(f"{table_name} (Clients): {count} rows")

    cursor.close()
    conn.close()

if __name__ == '__main__':
    count_tables()
