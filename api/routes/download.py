"""

Route for MMIF downloads.

Example requests:

# Just a workflow, makes the request act as a search for filename and a list
# of filenames (and the workflow) will be in the return value.

curl -X POST 127.0.0.1:8001/storeapi/download \
    -H 'Content-Type: "application/json"' \
    -d '{"workflow": {"swt-detection/v7.4": {"pretty": "true"}}}'

# Adding a single GUID, now the return value is a MMIF file.

curl -X POST 127.0.0.1:8001/storeapi/download \
    -H 'Content-Type: "application/json"' \
    -d '{"guid": "cpb-aacip-507-154dn40c26",
         "workflow": {
            "swt-detection/v7.4": {"pretty": "true"}}}'

# Now with less trivial parameters, returns a list of files.

curl -X POST 127.0.0.1:8001/storeapi/download \
    -H 'Content-Type: "application/json"' \
    -d '{"workflow": {
            "swt-detection/v6.1": {
                "useStitcher": "false", 
                "runningTime": "true", 
                "hwFetch": "true"}}}'

# Same, but with multiple GUIDs added, writes a zip file.

curl -X POST 127.0.0.1:8001/storeapi/download \
    -H 'Content-Type: "application/json"' \
    --output tmp.zip \
    -d '{"workflow": {
            "swt-detection/v6.1": {
                "useStitcher": "false",
                "runningTime": "true", 
                "hwFetch": "true"}},
         "guid": ["cpb-aacip-259-wh2dcb8p","cpb-aacip-c72fd5cbadc"]}'

"""

import json
import os
from pathlib import Path
from typing import Union

from flask import request, jsonify, Blueprint, send_file

from mmif.utils.workflow_helper import generate_param_hash
from mmif import utils, Mmif

from api import STORAGE_DIR
from api.model.storage import get_mmif_for_guid, create_zipfile
from api.errors import StorageServerError


bp = Blueprint('mmif_download', __name__)
#print(f'{bp} import_name={bp.import_name} __name__={__name__}')


API_PREFIX = '/storeapi'


@bp.post(f"{API_PREFIX}/download")
def download_mmif():
    data = json.loads(request.data.decode('utf-8'))
    # build workflow storage path from request JSON
    # e.g. {"workflow": {"swt-detection/v2.0": {"pretty": "True"}}}
    # becomes "swt-detection/v2.0/paramhash"
    wfid_segments = []
    for clams_app, params in data["workflow"].items():
        wfid_segments.append(clams_app)
        try:
            wfid_segments.append(generate_param_hash(params))
        except AttributeError:
            wfid_segments.append(generate_param_hash({}))
    wfid = '/'.join(wfid_segments)
    # get number of views for rewind if necessary
    num_views = len(data.get('workflow', []))
    guid = data.get('guid')
    # validate existence of workflow, guid is not necessary if you just want the workflow returned
    if not wfid:
        return jsonify({'error': 'Missing required parameters: need at least a workflow'})
    # load environment variables to concat workflow with local storage path
    directory = os.environ.get('STORAGE_DIR')
    wfid = os.path.join(directory, wfid)
    if not guid:
        return zero_guid_download_response(wfid)
    # Checking if the GUID is a single value or a list
    if not isinstance(guid, list):
        return single_guid_download_response(wfid, guid, num_views)
    else:
        return multi_guid_download_response(wfid, guid, num_views)


def zero_guid_download_response(workflow_id: Union[str, Path]):
    """
    For a "zero-guid" request, the user will receive just the local storage workflow
    and the list of files found there. This allows clients to utilize the api without
    downloading files (for working with local files).
    """
    filenames = [p.stem for p in Path(workflow_id).glob('*.mmif')]
    return jsonify({'workflow': workflow_id, 'filenames': filenames})


def single_guid_download_response(workflow_id: str, guid: str, num_views: int):
    """
    When retrieving the MMIF object for a workflow and a single GUID, just return
    the MMIF object or an error if the search failed.
    """
    try:
        mmif = get_mmif_for_guid(workflow_id, guid, num_views)
        return mmif
    except StorageServerError as e:
        return {"error": str(e)}, 201


def multi_guid_download_response(workflow_id: str, guids: list, num_views: int):
    """
    When retrieving multiple MMIFs for a workflow, we return a zip file.
    """
    # User will need to add '--output <FILE>' arg to curl request
    # NOTE (mv 12/12/25), the --output is needed even with the use of download_name
    # below. In fact, it still works for me without removing that parameter, but
    # keeping it anyway.
    mem_file = create_zipfile(workflow_id, guids)
    return send_file(
        mem_file, mimetype='zip', as_attachment=True,
        download_name='multi-guid-response.zip')
