import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask


load_dotenv()

DATABASE = Path(__file__).parent / 'database.db'
ASSET_DIR = os.environ.get('ASSET_DIR')
BUILD_DB = bool(int(os.environ.get('BUILD_DB')))


def create_app(build_db=BUILD_DB):

    from api.model.database import initialize_database
    
    app = Flask(__name__)
    app.config.from_prefixed_env()
    register_blueprints(app)
    initialize_database(build_db)

    @app.cli.command("create-db")
    def create_db():
        """Create the assets database and populate it."""
        initialize_database(populate=True)
        print('Assets database created and populated')

    return app


def register_blueprints(app: Flask):

    from api.www import bp as bp_www
    from api.routes.home import bp as bp_home
    from api.routes.assets import bp as bp_assets

    app.register_blueprint(bp_www)
    app.register_blueprint(bp_home)
    app.register_blueprint(bp_assets)
