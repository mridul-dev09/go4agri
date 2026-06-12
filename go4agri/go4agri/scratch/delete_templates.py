import mysql.connector

try:
    conn = mysql.connector.connect(
        user='root',
        password='MySQL@091610',
        host='localhost',
        database='GoforAgri'
    )
    cursor = conn.cursor(dictionary=True)
    
    # Let's delete all templates for app 7
    cursor.execute("DELETE FROM documents WHERE application_id = 7 AND category = 'REVIEW_TEMPLATE'")
    # Let's also revert status to DOCUMENT_REVIEW
    cursor.execute("UPDATE applications SET status = 'DOCUMENT_REVIEW' WHERE id = 7")
    
    conn.commit()
    print("Database cleaned up successfully for application 7.")
    cursor.close()
    conn.close()
except Exception as e:
    print("Error during cleanup:", e)
