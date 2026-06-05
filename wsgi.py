import sys
import os

# Get the absolute path of the project directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Add the project directory to Python path
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

# Set environment variables
os.environ['FLASK_APP'] = 'app.py'
os.environ['FLASK_ENV'] = 'production'

# Import the Flask app
from app import app as application

# Initialize the database
with application.app_context():
    from app import init_db
    init_db()

# Configure SocketIO for production
if 'socketio' in sys.modules:
    from app import socketio
    application = socketio.run(application) 