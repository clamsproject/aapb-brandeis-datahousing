import pathlib

from dotenv import load_dotenv

# The api package reads its settings from the environment at import time,
# so the production settings must be loaded first.
load_dotenv(
    dotenv_path=pathlib.Path(__file__).parent / '.env.production',
    verbose=True)

from api import create_app  # noqa: E402
from api.model.database import initialize_database  # noqa: E402

# init db once here
initialize_database(True)
# so that gunicorn workers do not init db again
app = create_app(False)
