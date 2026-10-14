import sqlite3

# Connect to database
conn = sqlite3.connect('interview.db')
cursor = conn.cursor()

# Get all users
cursor.execute("SELECT email, password FROM users")
users = cursor.fetchall()

print("=" * 80)
print("USERS IN DATABASE:")
print("=" * 80)

for email, password in users:
    print(f"\nEmail: {email}")
    print(f"Password: {password[:50]}...")  # Show first 50 chars
    print("-" * 80)

conn.close()
