import io
import json
import os
import zipfile as zf
from pathlib import Path
from typing import Union
from zipfile import ZIP_DEFLATED

from flask import request, jsonify, Blueprint, send_file

from mmif.utils.workflow_helper import generate_param_hash
from mmif import utils, Mmif

from api import STORAGE_DIR
from api.errors import StorageServerError
from api.utils import hash_from_dictionary


bp = Blueprint('mmif_download', __name__)
print(f'{bp} import_name={bp.import_name} __name__={__name__}')


API_PREFIX = '/storeapi'


@bp.post(f"{API_PREFIX}/download")
def download_mmif():
    # TODO (krim @ 2025-12-17): need to update this after https://github.com/clamsproject/aapb-brandeis-datahousing/issues/34 is resolved
    """
    request payload format:

    {
        "workflow": { "swt-detection/v2.0-38-g7838415": {"pretty": "True"} },
        "guid": "NON-EXISTING GUID"
    }
    or
    {
        "workflow": { "whisper-wrapper/v3": {"modelSize": "tiny"} },
        "guid": ["cpb-aacip-507-154dn40c26", "cpb-aacip-507-v40js9j432", "NO-SUCH-GUID"]
    }
    {"workflow": {"swt-detection/v2.0-38-g7838415": {"pretty": "True"}}}

    """
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
    filenames = [p.stem for p in Path(workflow_id).glob('*')]
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
    When retrieving multiple MMIFs for a workflow, we construct a json object to
    store each guid as a key and each MMIF as the value.
    """
    errors = dict()
    mem_file = io.BytesIO()
    with zf.ZipFile(mem_file, 'w', ZIP_DEFLATED) as mmif_zip:
        for guid in guids:
            try:
                # mmif = get_mmif_for_guid(workflow, guid, num_views)
                # instead of using get_mmif_for_guid and needing to re-dump mmif
                mmif_name = guid + ".mmif"
                path = os.path.join(workflow_id, mmif_name)
                mmif_zip.write(filename=path, arcname=f'multi-guid-response/files/{mmif_name}')
            except FileNotFoundError:
                errors[guid] = {"Error": f"Did not find {guid}"}
        mmif_zip.writestr(zinfo_or_arcname="multi-guid-response/workflow_path.txt", data=workflow_id)
        error_dump = json.dumps(errors, indent=2)
        mmif_zip.writestr(zinfo_or_arcname="multi-guid-response/errors.json", data=error_dump)
    mem_file.seek(0)
    # User will need to add '--output <FILE>' arg to curl request
    # NOTE (mv 12/12/25), the --output is needed even with the use of download_name
    # below. In fact, it still works for me withoutremove that parameter, but keeping
    # it anyway.
    return send_file(
        mem_file, mimetype='zip', as_attachment=True,
        download_name='multi-guid-response.zip')


def get_mmif_for_guid(workflow_id: str, guid: str, num_views: int):
    """
    Retrieve the MMIF file for a workflow and GUID. If none was found raise a
    StorageServerError.
    """
    guid = guid + ".mmif"
    path = os.path.join(workflow_id, guid)
    # if filepath exists, we can return it
    try:
        with open(path, 'r') as file:
            mmif = json.loads(file.read())
        return mmif
    # otherwise we will use the rewinder to check if the user provided a prefix of a
    # mmif workflow that we have previously stored
    except FileNotFoundError:
        try:
            return rewind_time(workflow_id, guid, num_views)
        except FileNotFoundError:
            # the rewinder does not always succeed so we catch this exception again
            # and raise an application-specific exception
            raise StorageServerError(f'Did not find: {guid.split(".")[0]}')


def rewind_time(workflow_id, guid, num_views):
    """
    This method takes in a workflow (path), a guid, and a number of views, and uses
    os.walk to iterate through directories that begin with that workflow. It takes
    the first mmif file that matches the guid and uses the rewind feature to include
    only the views indicated by the workflow.
    """
    for home, dirs, files in os.walk(workflow_id):
        # find mmif with matching guid to rewind
        for file in files:
            if guid == file:
                # rewind the mmif
                with open(os.path.join(home, file), 'r') as f:
                    mmif = Mmif(f.read())
                    # we need to calculate the number of views to rewind
                    rewound = utils.rewind.rewind_mmif(mmif, len(mmif.views) - num_views)
                return rewound.serialize()
    raise FileNotFoundError
