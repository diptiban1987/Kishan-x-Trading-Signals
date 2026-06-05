import sqlite3
conn = sqlite3.connect('trading.db')
print("Users:", conn.execute("SELECT id, username, is_premium FROM users WHERE username='satyadeep'").fetchall())
print("Subscriptions:", conn.execute("SELECT * FROM subscriptions WHERE user_id = (SELECT id FROM users WHERE username='satyadeep')").fetchall())
