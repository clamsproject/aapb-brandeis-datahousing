"""

The run package takes care of interactions with the CLAMS App (which runs on
some port, typically but not necessarily in a container).

This is also where available apps are registered. Registration is manual via
a URL provided by the user. In the future registration may be automatic by
scanning running containers.

"""

import json
import requests

from mmif import Mmif

from api.run.app import run_job


APPS = {}

DEBUG = False


class ClamsApp:

    """Class to wrap a CLAMS App runnning on a URL. Just there as a way to send
    GET and POST requests and return the result in a useful format."""

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
        envelope = create_envelope(mmif_in, json.loads(params))
        response = requests.post(self.url, data=envelope, params={})
        return Mmif(response.json())


def register_app(url: str):
    """Check the input url with a GET request to see if it is a CLAMS app, if
    so register the url in the APPS variable under the identifier of the app."""
    # TODO: check whether the http:// part is there
    if not url.startswith('http://'):
        url = f'http://{url}'
    try:
        result = requests.get(url=url, params={}, timeout=5)
        data = result.json()
        if is_clams_app_result(data):
            app_id = data['identifier']
            APPS[app_id] = url
            print(f'Registered {app_id}')
        else:
            print('The URL does not point to a CLAMS App')
    except requests.exceptions.ConnectTimeout:
        print('Connection timeout')
    except Exception:
        print('Unexpected output')


def is_clams_app_result(data: json) -> bool:
    """Return True if the data are the results of a CLAMS App GET request."""
    required_properties = (
        "name", "description", "app_version", "mmif_version", "identifier", "url")
    return all([prop in data for prop in required_properties])


def create_envelope(mmif: Mmif, parameters: dict) -> str:
    """
    Create a JSON envelope string wrapping a MMIF obejct and parameters.

    :param mmif: an instance of mmif.serialize.mmif.Mmif
    :param parameters: parameter dict with JSON-native values
    :returns: JSON string of the envelope

    Based on clams.envelop.create_envelope().
    """

    mmif_obj = json.loads(mmif.serialize())
    envelope = {'parameters': parameters, 'mmif': mmif_obj}
    if DEBUG:
        with open('envelope.json', 'w') as fh:
            fh.write(json.dumps(envelope, indent=2))
    return json.dumps(envelope)

