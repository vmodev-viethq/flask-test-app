from flask_sqlalchemy import SQLAlchemy

# Create our SQLAlchemy database client
# DEV: `db` gets configured in `app.py:create_app` since it relies on a created/running Flask app
db = SQLAlchemy()
