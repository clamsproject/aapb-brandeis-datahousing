"""

The run module takes care of interactions with the CLAMS App (which runs on
some port, typically but not necessarily in a container).

This is also where available apps are registered. Registration is manual via
a URL provided by the user. In the future registration may be automatic by
scanning running containers.

"""

import json
import requests
import sys
import time
import argparse
import subprocess
from pathlib import Path
from random import Random

from mmif import Mmif, AnnotationTypes, DocumentTypes
from mmif.serialize.annotation import Annotation, Document


APPS = {}

DEBUG = False


class ClamsApp:

    """Class to wrap a CLAMS App runnning on a URL. Just so there is a way to
    send GET and POST requests and return the result in a useful format."""

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
        #response = requests.post(self.url, data=envelope, params={})
        response = requests.post(self.url, data=envelope)
        return Mmif(response.json())


def register_app(url: str):
    """Check the input url with a GET request to see if it is a CLAMS app, if
    so register the url in the APPS variable under the identifier of the app."""
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


def run_job(timestamp: str, name: str, shack: 'ClamShack') -> str:
    """Call the run_batch.py script to run a ClamShack job. Initializes the jobs
    file (with a timestamp and other goodies), spins off a subprocess, and returns
    the process identifier."""
    param_string = json.dumps(shack.params)
    cmd = ['python', 'run_batch.py', name,
           '--location', str(shack.location),
           '--path', str(shack.cwd()),
           '--app-name', shack.app.name,
           '--app-url', shack.app.url,
           '--params', param_string]
    cmd_str = ' '.join(str(p) for p in cmd)
    process = subprocess.Popen(cmd, start_new_session=True)
    job_file = shack.job_file(name)
    shack._jobs.append(job_file)
    with open(job_file, 'a') as fh:
        fh.write(f'STARTED\t{timestamp}\n')
        fh.write(f'COMMAND\t{cmd_str}\n')
        fh.write(f'PROCESS_ID\t{process.pid}\n')
    return(process.pid)


def create_document(doc_id: str, path: Path) -> Document:
    # TODO: this should be generalized and deal with all mime types
    doc = Document()
    doc.id = doc_id
    # TODO: should not just rely on the path and the MIME type needs to take
    # the extension into account
    if 'video' in path.parts:
        doc.at_type = DocumentTypes.VideoDocument
        doc.add_property('mime', f'video/{path.suffix[1:]}')
    elif 'text' in path.parts:
        doc.at_type = DocumentTypes.TextDocument
        doc.add_property('mime', f'text/plain')
    elif 'audio' in path.parts:
        doc.at_type = DocumentTypes.TextDocument
        doc.add_property('mime', f'audio/wav')
    else:
        print('Warning: could not determine @type')
    doc.add_property('location', str(path))
    return doc


def create_source(docs: list[Path]) -> Mmif:
    """Creates a MMIF source from a list of document paths. This assumes it is
    possible to generate a document type from each path."""
    mmif = Mmif()
    for i, path in enumerate(docs):
        doc = create_document(f'd{i+1}', path)
        mmif.documents.append(doc)
    return mmif


def update_source(source_path: Path, asset_path: Path) -> Mmif:
    """Returns a Mmif object with the asset_path added if it was not already
    in there."""
    mmif = Mmif(source_path.read_text())
    locations = set([doc.location for doc in mmif.documents])
    # When searching the location we need to add the file:// prefix
    asset_loc = f'file://{str(asset_path)}'
    if asset_loc in locations:
        return mmif
    else:
        identifier = f'd{len(mmif.documents)+1}'
        doc = create_document(identifier, asset_path)
        mmif.documents.append(doc)
    return mmif


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

