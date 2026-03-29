import re

filepath = r'c:\Users\admin\Desktop\go4agri\go4agri\go4agri\app.py'

new_routes = '''

@app.route('/restart-application/<int:app_id>', methods=['POST'])
def restart_application(app_id):
    if 'user_id' not in session or session.get('designation') != 'Admin':
        flash('Unauthorized access.', 'error')
        return redirect(url_for('employee_login'))
    rejection_reason = request.form.get('rejection_reason', '').strip()
    if not rejection_reason:
        flash('A rejection reason is mandatory to restart the application.', 'error')
        return redirect(url_for('dashboard'))
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute('SELECT * FROM applications WHERE id = %s', (app_id,))
        application = cursor.fetchone()
        if not application or application['status'] != 'REJECTED':
            flash('Only REJECTED applications can be restarted.', 'error')
            cursor.close()
            conn.close()
            return redirect(url_for('dashboard'))
        new_restart_count = (application.get('restart_count') or 0) + 1
        cursor.execute(
            'UPDATE applications SET status = %s, restart_count = %s WHERE id = %s',
            ('DOCUMENT_REVIEW', new_restart_count, app_id)
        )
        cursor.execute(
            'INSERT INTO application_restarts (application_id, restarted_by, restart_count, rejection_reason) VALUES (%s, %s, %s, %s)',
            (app_id, session['user_id'], new_restart_count, rejection_reason)
        )
        conn.commit()
        cursor.execute(
            'INSERT INTO messages (sender_id, receiver_id, subject, body, is_read) VALUES (%s, %s, %s, %s, 0)',
            (session['user_id'], application['client_id'],
             f'Application #{app_id} Restarted (Attempt #{new_restart_count})',
             f'Your application requires corrections.\\n\\nReason: {rejection_reason}\\n\\nPlease re-upload the corrected documents from your dashboard.')
        )
        conn.commit()
        cursor.close()
        conn.close()
        log_activity(session['user_id'], 'RESTART_APPLICATION', f'Restarted application {app_id} (Attempt #{new_restart_count}). Reason: {rejection_reason}')
        flash(f'Application #{app_id} has been restarted (Attempt #{new_restart_count}). Client has been notified.', 'success')
    except Exception as e:
        print(f'Error restarting application: {e}')
        flash('Error restarting application.', 'error')
    return redirect(url_for('dashboard'))


@app.route('/restart-history/<int:app_id>')
def restart_history(app_id):
    allowed_roles = ['CEO', 'Admin', 'QA', 'Initial reviewer', 'Inspection planner', 'Auditor', 'Technical reviewer', 'Certifier']
    if 'user_id' not in session or session.get('designation') not in allowed_roles:
        flash('Unauthorized access.', 'error')
        return redirect(url_for('dashboard'))
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute('SELECT * FROM applications WHERE id = %s', (app_id,))
        application = cursor.fetchone()
        cursor.execute(
            'SELECT r.*, u.full_name as restarted_by_name FROM application_restarts r JOIN users u ON r.restarted_by = u.id WHERE r.application_id = %s ORDER BY r.restarted_at ASC',
            (app_id,)
        )
        history = cursor.fetchall()
        cursor.close()
        conn.close()
        return render_template('restart_history.html', user=session, application=application, history=history)
    except Exception as e:
        print(f'Error fetching restart history: {e}')
        flash('Error loading restart history.', 'error')
        return redirect(url_for('dashboard'))

'''

with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

marker = "if __name__ == '__main__':"
if marker in content:
    content = content.replace(marker, new_routes + marker)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    print('Routes appended successfully.')
else:
    print('ERROR: Could not find insertion point.')
