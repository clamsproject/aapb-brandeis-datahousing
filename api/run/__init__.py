"""

The run package takes care of all worries related to running a batch job.

This is where available apps are listed. In the final version this will inspect
either the list of running containers or allow the user so assign a host and port
to a app name. At the moment it just registers a couple of fake apps.

"""

import json
import requests

from mmif import Mmif

from api.run.app import run_job


APPS = {}


class ClamsApp:

    def __init__(self, name: str, url: str):
        self.name = name
        self.url = url

    def __str__(self):
        return f'<ClamsApp {self.name} at {self.url}>'

    def metadata(self) -> dict:
        metadata = requests.get(self.url)
        #print(json.dumps(metadata.json(), indent=2))
        return metadata.json()

    def run(self, mmif_in: Mmif, params: str) -> Mmif:
        response = requests.post(self.url, data=mmif_in.serialize(), params=json.loads(params))
        return Mmif(response.json())


def register_app(url: str):
	try:
		result = requests.get(url=url, params={}, timeout=5)
		data = result.json()
		app_id = data['identifier']
		print(f'Registered {app_id}')
		APPS[app_id] = url
	except requests.exceptions.ConnectTimeout:
		print('Connection timeout')
	except Exception:
		print('Unexpected output')
