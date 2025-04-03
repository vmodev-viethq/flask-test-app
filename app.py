from flask import Flask

from src.db import db
from src.settings import Settings
from src.blueprints import register_blueprints


def create_app():
    app = Flask(__name__)
    app.config.from_object(Settings)
    # By default Flask will auto-redirect `/path` to `/path/`, this disables that
    app.url_map.strict_slashes = False

    # Initialize our database connection
    db.init_app(app)
    register_blueprints(app)
    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)
