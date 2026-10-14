import sqlite3

# Connect to database
conn = sqlite3.connect('interview.db')
cursor = conn.cursor()

# Add the missing columns
try:
    cursor.execute('ALTER TABLE users ADD COLUMN is_verified INTEGER DEFAULT 0')
    print("✅ Added is_verified column")
except:
    print("⚠️ is_verified column already exists")

try:
    cursor.execute('ALTER TABLE users ADD COLUMN verification_token TEXT')
    print("✅ Added verification_token column")
except:
    print("⚠️ verification_token column already exists")

# Mark all existing users as verified (so they can still login)
cursor.execute('UPDATE users SET is_verified = 1 WHERE is_verified IS NULL OR is_verified = 0')
print("✅ Marked existing users as verified")

conn.commit()
conn.close()
print("\n✅ Database updated successfully!")
