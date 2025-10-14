from dotenv import load_dotenv
import pathlib
load_dotenv(dotenv_path=pathlib.Path(__file__).parent/'.env.production', verbose=True)

import api
# init db once here
api.initialize(True)
# so that gunicorn workers do not init db again
app = api.create_app(False)
