filepath = r'c:\Users\admin\Desktop\go4agri\go4agri\go4agri\app.py'

old = "WHERE a.status IN ('APPLICATION_RECEIVED', 'PARTIAL_PAYMENT_VERIFIED')\r\n                    ORDER BY a.created_at DESC"
new = "WHERE a.status IN ('APPLICATION_RECEIVED', 'PARTIAL_PAYMENT_VERIFIED', 'REJECTED')\r\n                    ORDER BY CASE a.status WHEN 'REJECTED' THEN 0 ELSE 1 END, a.created_at DESC"

with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

if old in content:
    content = content.replace(old, new, 1)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    print('Admin dashboard query updated to include REJECTED applications.')
else:
    print('ERROR: Could not find the target query. Trying alternate line endings...')
    old2 = "WHERE a.status IN ('APPLICATION_RECEIVED', 'PARTIAL_PAYMENT_VERIFIED')\n                    ORDER BY a.created_at DESC"
    new2 = "WHERE a.status IN ('APPLICATION_RECEIVED', 'PARTIAL_PAYMENT_VERIFIED', 'REJECTED')\n                    ORDER BY CASE a.status WHEN 'REJECTED' THEN 0 ELSE 1 END, a.created_at DESC"
    if old2 in content:
        content = content.replace(old2, new2, 1)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print('Admin dashboard query updated (alternate line endings).')
    else:
        print('ERROR: Could not find target. Manual fix needed.')
