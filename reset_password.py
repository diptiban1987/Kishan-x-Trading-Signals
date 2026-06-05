import sqlite3
import os
from werkzeug.security import generate_password_hash

def _get_db_path():
    try:
        from branding_config import branding
        return branding.db_path
    except ImportError:
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'trading.db')

def reset_password(username, new_password):
    try:
        # Connect to database
        conn = sqlite3.connect(_get_db_path())
        cursor = conn.cursor()
        
        # Generate new password hash using SHA256 method
        password_hash = generate_password_hash(new_password, method='sha256')
        
        # Update the password
        cursor.execute('UPDATE users SET password = ? WHERE username = ?', (password_hash, username))
        
        # Commit the changes
        conn.commit()
        
        # Check if any row was affected
        if cursor.rowcount > 0:
            print(f"Successfully reset password for user: {username}")
        else:
            print(f"No user found with username: {username}")
            
    except Exception as e:
        print(f"Error resetting password: {str(e)}")
    finally:
        conn.close()

if __name__ == "__main__":
    username = input("Enter username: ")
    new_password = input("Enter new password: ")
    reset_password(username, new_password) 