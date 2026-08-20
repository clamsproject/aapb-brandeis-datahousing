"""

Route for MMIF downloads, for the time being this also includes the peek
endpoint.

All routes:

    api/mmif/peek
    api/mmif/download
    storeapi/peek
    storeapi/download

The latter two are older routes and those are used in the examples below.

Example requests:

# Peek into a workflow directory. When you enter a workflow as a dictionary it will
# create the workflow identifier and return it, and if the workflow actually exists
# in the storage then it will also return all MMIF files under that workflow.

curl -X POST 127.0.0.1:8001/api/mmif/peek \
    -H 'Content-Type: "application/json"' \
    -d '{"swt-detection/v8.6": {}}'

curl -X POST 127.0.0.1:8001/api/mmif/peek \
    -H 'Content-Type: "application/json"' \
    -d '{"workflow": {"swt-detection/v8.6": {"pretty": "True"}}}'


# Downloading a single MMIF file. In addition to a workflow this also requires
# an identifier (a GUID in the aapb case). The return value is a MMIF file.

curl -X POST 127.0.0.1:8001/api/mmif/download \
    -H 'Content-Type: "application/json"' \
    -d '{"guid": "cpb-aacip-4071f72dd46-clip1",
         "workflow": {"swt-detection/v8.6": {}}}'

curl -X POST 127.0.0.1:8001/api/mmif/download \
    -H 'Content-Type: "application/json"' \
    -d '{"guid": "cpb-aacip-4071f72dd46-clip1",
         "workflow": {"swt-detection/v8.6": {"pretty": "True"}}}'


# Same as above, but now with a list of identifiers, which returns a zip file.
# The list can be of lenth one in which case you still get a zip file and not
# a JSON/MMIF file as above.

curl -X POST 127.0.0.1:8001/api/mmif/download \
    -H 'Content-Type: "application/json"' \
    --output tmp.zip \
    -d '{"guid": ["cpb-aacip-4071f72dd46-clip1", "cpb-aacip-c72fd5cbadc"],
         "workflow": {"swt-detection/v8.6": {}}}'

# Using workflow identifiers. As an alternative we can use the workflow identifier,
# this works whether the guid value is a string or a list.

curl -X POST 127.0.0.1:8001/api/mmif/download \
    -H 'Content-Type: "application/json"' \
    -d '{"guid": "cpb-aacip-4071f72dd46-clip1",
         "workflow_id": "swt-detection/v8.6/d41d8cd98f00b204e9800998ecf8427e"}'

curl -X POST 127.0.0.1:8001/api/mmif/download \
    -H 'Content-Type: "application/json"' \
    --output tmp.zip \
    -d '{"guid": ["cpb-aacip-4071f72dd46-clip1", "cpb-aacip-c72fd5cbadc"],
         "workflow_id": "swt-detection/v8.6/d41d8cd98f00b204e9800998ecf8427e"}'



"""

import json
import io
import os
from pathlib import Path
from typing import Union

from flask import request, jsonify, Blueprint, send_file

from mmif import utils, Mmif

from api import STORAGE_DIR
from api.model.storage import get_mmif_for_guid
from api.model.storage import generate_workflow_identifier_from_workflow_data
from api.model.storage import get_files_at_workflow, create_zipfile
from api.errors import StorageServerError


bp = Blueprint('mmif_download', __name__)
#print(f'{bp} import_name={bp.import_name} __name__={__name__}')


@bp.post('/api/mmif/peek')
@bp.post('/storeapi/peek')
def peek():
    data = json.loads(request.data.decode('utf-8'))
    wfid = generate_workflow_identifier_from_workflow_data(data)
    if not wfid:
        return jsonify(
            {'error': 'Could not build a workflow identifier from the input given.'})
    # load environment variable to concat workflow with local storage path
    directory = os.environ.get('STORAGE_DIR')
    wfpath = os.path.join(directory, wfid)
    return jsonify({'workflow_id': wfid, 'filenames': get_files_at_workflow(wfpath)})


@bp.post('/api/mmif/download')
@bp.post('/storeapi/download')
def download_mmif():
    data = json.loads(request.data.decode('utf-8'))
    if 'workflow_id' in data:
        # TODO: maybe add a check that the value is an existing workflow
        wfid = data['workflow_id']
    else:
        wfid = generate_workflow_identifier_from_workflow_data(data['workflow'])
    # get number of views for rewind if necessary
    num_views = len(data.get('workflow', []))
    guid = data.get('guid')
    # validate existence of workflow, guid is not necessary if you just want the workflow returned
    if not wfid:
        return jsonify({'error': 'Missing required parameters: need at least a workflow'})
    # load environment variables to concat workflow with local storage path
    directory = os.environ.get('STORAGE_DIR')
    wfid = os.path.join(directory, wfid)
    # Checking if the GUID is a single value or a list
    if not isinstance(guid, list):
        return get_mmif_file(wfid, guid, num_views)
    else:
        return get_mmif_files(wfid, guid, num_views)


def get_mmif_file(workflow_id: str, guid: str, num_views: int) -> dict:
    """
    Return the MMIF object (as a dictionary) for a workflow and a single file
    identifier. If there is no such MMIF file return a dictionary with an error
    message.
    """
    try:
        return get_mmif_for_guid(workflow_id, guid, num_views)
    except StorageServerError as e:
        return {"error": str(e)}, 201


def get_mmif_files(workflow_id: str, guids: list, num_views: int):
    """
    When retrieving multiple MMIFs for a workflow, we return a zip file.

    The user will need to add '--output <FILE>' arg to the curl request, which
    seems to be needed even with the use of download_name below. In fact, that
    parameter does not seem to be needed when using --output. Need to look into
    this a bit.
    """
    mem_file = create_zipfile(workflow_id, guids)
    return send_file(
        mem_file, mimetype='zip', as_attachment=True,
        download_name='storage-response.zip')
