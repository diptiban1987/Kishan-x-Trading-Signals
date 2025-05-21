from flask import Flask
import logging

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)

@app.route('/')
def hello():
    try:
        return "Hello, World!"
    except Exception as e:
        logger.error(f"Error in hello route: {str(e)}")
        return "An error occurred", 500

# Error handlers
@app.errorhandler(500)
def internal_error(error):
    logger.error(f"500 error: {str(error)}")
    return "Internal Server Error", 500
