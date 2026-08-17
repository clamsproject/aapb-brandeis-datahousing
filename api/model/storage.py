import os
import json
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Union

from flask import jsonify

from clams_utils.aapb import guidhandler
from mmif import Mmif
from mmif.utils.workflow_helper import generate_param_hash
from mmif.utils.workflow_helper import generate_workflow_identifier

from api import STORAGE_DIR
from api.errors import StorageServerError, UploadWarning, EmptyMmifWarning


def upload_mmif(body: str, root: str = STORAGE_DIR, overwrite: str = True) -> Path:

    """Upload the MMIF file in the body to the MMIF storage. Upload includes 
    writing parameter files for the views. Do not overwrite unless overwrite is
    True. Returns the relative path of the file written. Raises an UploadWarning
    for any of the boundary cases where an upload will not occur."""

    mmif = Mmif(body)
    cur_root = root
    guid = get_guid(mmif)

    # Generate the workflow identifier from the MMIF views and retrieve the
    # parameter dictionaries from them, then write the parameter dictionaries
    # to the appropriate directories. The syntax of the path is
    # /local_storage_dir/app1name/app1version/app1paramhash/app2name/...
    wfid, param_dicts = generate_workflow_identifier(mmif, return_param_dicts=True)
    if wfid == '':
        # this happens when there are no views, just ignore these
        raise EmptyMmifWarning()
    write_parameters(cur_root, wfid, param_dicts)

    # Note that the absolute path is not necessarily absolute because cur_root
    # is allowed to be relative.
    relative_path = Path(wfid) / f'{guid}.mmif'
    absolute_path = cur_root / wfid / f'{guid}.mmif'

    # Check for cases when there will be no upload.
    if not mmif.views:
        raise UploadWarning('Upload file has no view content', path=relative_path)
    if absolute_path.exists() and not overwrite:
        raise UploadWarning(
            'Upload file already exists, use overwrite=True if you want to overwrite.',
            path=relative_path)

    with open(absolute_path, 'w') as f:
        f.write(body)

    return relative_path


def get_guid(mmif: Mmif):
    """Get the first document and calculate the GUID from the its location,
    assumes that the first document is the main one that has the AAPB GUID.
    Raise an UploadWarning if no GUID could be found."""
    guid = guidhandler.get_aapb_guid_from(mmif.documents[0].location)
    if guid is None:
        raise UploadWarning('Document has no identifier')
    return guid


def get_files_at_workflow(workflow_path: Union[str, Path]) -> list:
    """Return the list of MMIF files at the workflow path."""
    return [p.stem for p in Path(workflow_path).glob('*.mmif')]


def write_parameters(root: str, wfid: str, param_dicts: list):
    """Write json parameter files for each step in the workflow."""
    path_name = None
    segments = wfid.split('/')
    if len(segments) % 3 != 0:
        raise UploadWarning(f"Malformed workflow identifier: {wfid} ")   
    for i in range(0, len(segments), 3):
        appn = segments[i]
        appv = segments[i + 1]
        param_hash = segments[i + 2]
        root = root / Path(appn) / appv / param_hash
        root.mkdir(parents=True, exist_ok=True)
        # TODO. This now overwrites an already existing parameter file, add some
        # kind of check here to catch weird cases? Maybe do not overwrite but warn
        # if contents are different.
        with open(root.with_suffix('.json'), 'w') as f:
            json.dump(param_dicts[i // 3], f, indent=2)


def get_mmif_for_guid(workflow_id: str, identifier: str, num_views: int):
    """
    Retrieve the MMIF file for a workflow and an identifier. If none was found
    raise a StorageServerError.
    """
    fname = identifier + ".mmif"
    path = os.path.join(workflow_id, fname)
    # If the filepath exists, we return the content
    try:
        with open(path, 'r') as file:
            return json.loads(file.read())
    # Otherwise we use the rewinder to check if the user provided a prefix of a
    # mmif workflow that we have previously stored.
    except FileNotFoundError:
        try:
            return rewind_time(workflow_id, fname, num_views)
        except FileNotFoundError:
            # The rewinder does not always succeed so we catch this exception
            # again and raise an application-specific exception.
            raise StorageServerError(f'Did not find: {fname.split(".")[0]}')


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


def create_zipfile(workflow_id: str, guids: list) -> BytesIO:
    """
    When retrieving multiple MMIFs for a workflow, we construct a zip file that
    contains a file for each guid.
    """
    errors = dict()
    mem_file = BytesIO()
    with zipfile.ZipFile(mem_file, 'w', zipfile.ZIP_DEFLATED) as mmif_zip:
        for guid in guids:
            try:
                mmif_name = guid + ".mmif"
                path = os.path.join(workflow_id, mmif_name)
                mmif_zip.write(filename=path, arcname=f'storage-response/files/{mmif_name}')
            except FileNotFoundError:
                errors[guid] = {"Error": f"Did not find {guid}"}
        mmif_zip.writestr(zinfo_or_arcname="storage-response/workflow_path.txt", data=workflow_id)
        error_dump = json.dumps(errors, indent=2)
        mmif_zip.writestr(zinfo_or_arcname="storage-response/errors.json", data=error_dump)
    mem_file.seek(0)
    return mem_file


def generate_workflow_identifier_from_workflow_data(data: dict) -> str:
    """
    Build the relative workflow storage path from the request's JSON data. For
    example, with input like

        {"workflow": {"swt-detection/v2.0": {"pretty": "True"}}}

    this function should return

        "swt-detection/v2.0/5fe49d06725497b274b6eaaf0fe0c5d2"

    This is similar to generate_workflow_identifier in mmif.utils.workflow_helper,
    but the latter takes full MMIF input. We should probably merge this into the 
    workflow_helper module.
    """
    wfid_segments = []
    for clams_app, params in data.items():
        try:
            param_hash = generate_param_hash(params)
        except AttributeError:
            # in case the parameters input is not a proper dictionary
            param_hash = generate_param_hash({})
        wfid_segments.extend([clams_app, param_hash])
    wfid = '/'.join(wfid_segments)
    return wfid
