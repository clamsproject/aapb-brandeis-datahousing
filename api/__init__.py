import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, Blueprint


load_dotenv()

DATABASE = Path(__file__).parent / 'database.db'
ASSET_DIR = os.environ.get('ASSET_DIR')
DOWNLOAD_DIR = os.environ.get('DOWNLOAD_DIR')
STORAGE_DIR = os.environ.get('STORAGE_DIR')
BUILD_DB = bool(int(os.environ.get('BUILD_DB')))
DEVELOPER_MODE = bool(int(os.environ.get('DEVELOPER_MODE')))


bp = Blueprint('api', __name__)
print(f'{bp} import_name={bp.import_name} __name__={__name__}')


@bp.get('/')
def index():
    return {"message": "This is the MMIF storage server"}


def create_app(build_db=BUILD_DB, developer_mode=DEVELOPER_MODE):

    from api.assets import initialize_database
    initialize_database(build_db)

    app = Flask(__name__)
    app.config.from_prefixed_env()
    app.register_blueprint(bp)

    from api.www import bp as www_bp
    from api.assets import bp as assets_bp
    from api.analytics import bp as bp_analytics
    from api.mmif_upload import bp as bp_upload
    from api.mmif_download import bp as bp_download

    app.register_blueprint(www_bp)
    app.register_blueprint(assets_bp)
    app.register_blueprint(bp_analytics)
    app.register_blueprint(bp_upload)
    app.register_blueprint(bp_download)
    
    if developer_mode:
        from api.experiments import bp as exp_bp
        app.register_blueprint(exp_bp)
    
    return app
