import pandas as pd

# Create dummy employee data
data = {
    'full_name': ['Test Auditor', 'New Secretary'],
    'email': ['test_auditor@go4agri.com', 'secretary@go4agri.com'],
    'designation': ['Auditor', 'Certification officer'],
    'password': ['pass123', 'pass456']
}

df = pd.DataFrame(data)

# Save to Excel
df.to_excel('test_employees.xlsx', index=False)
print("Created test_employees.xlsx")
