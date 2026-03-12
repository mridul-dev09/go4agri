filepath = r'c:\Users\admin\Desktop\go4agri\go4agri\go4agri\templates\db_client.html'

banner = '''
    {% for app in applications %}
    {% if app.restart_count and app.restart_count > 0 and app.status == 'DOCUMENT_REVIEW' %}
    <div style="background: #fff3cd; border: 1px solid #ffc107; border-left: 5px solid #e74c3c; border-radius: 8px; padding: 15px 20px; margin-bottom: 20px; display: flex; align-items: flex-start; gap: 15px;">
        <i class="fas fa-exclamation-triangle" style="color: #e74c3c; font-size: 1.4rem; margin-top: 3px;"></i>
        <div>
            <strong style="color: #c0392b; font-size: 0.95rem;">&#9888; Action Required: Application Restarted (Attempt #{{ app.restart_count }})</strong>
            <p style="margin: 5px 0 0; color: #555; font-size: 0.88rem;">
                Your application <strong>{{ app.company_name }}</strong> has been reviewed and requires corrections.
                Please check your <a href="/messages" style="color: #0072bc; font-weight: 700;">Messages Inbox</a> for the reason and re-upload corrected documents below.
            </p>
        </div>
    </div>
    {% endif %}
    {% endfor %}

'''

anchor = '<!-- Bank Details & Instructions -->'

with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

if anchor in content:
    content = content.replace(anchor, banner + anchor)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    print('Restart banner inserted successfully.')
else:
    # fallback: insert after the header div close
    header_close = '    </div>\n\n'
    idx = content.find(header_close)
    if idx != -1:
        insert_at = idx + len(header_close)
        content = content[:insert_at] + banner + content[insert_at:]
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print('Restart banner inserted via fallback.')
    else:
        print('ERROR: Could not find insertion point.')
