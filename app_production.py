from dotenv import load_dotenv
import pathlib

from api import create_app
from api.model.database import initialize_database

load_dotenv(dotenv_path=pathlib.Path(__file__)/'.env.production', verbose=True)

# init db once here
initialize_database(True)
# so that gunicorn workers do not init db again
app = create_app(False)
