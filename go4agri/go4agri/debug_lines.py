with open('app.py', 'r') as f:
    lines = f.readlines()
for i in range(450, 490):
    print(f"{i+1}:{repr(lines[i])}")
