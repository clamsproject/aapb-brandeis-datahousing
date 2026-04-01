import io
import json
import os
import re
import zipfile as zf
from pathlib import Path
from typing import Union
from zipfile import ZIP_DEFLATED

from clams_utils.aapb import guidhandler
from flask import request, jsonify, Blueprint, current_app, send_file
from mmif import Mmif
from mmif import utils
from mmif.utils.workflow_helper import generate_param_hash
from mmif.utils.workflow_helper import generate_workflow_identifier

from mmif import utils, Mmif, View
from clams_utils.aapb import guidhandler

from api import STORAGE_DIR
from api.utils import hash_from_dictionary

# make blueprint of app to be used in __init__.py
bp = Blueprint(__file__.split(os.sep)[-1].split('.')[0].replace('_', '-'), __name__)


API_PREFIX = '/storeapi'


class StorageServerError(Exception):
    pass


def identifier_of_first_document(mmif_file: Mmif):
    for doc in mmif_file.documents:
        if doc.id:
            return doc.id
    return None



@bp.post(f"{API_PREFIX}/upload")
def upload_mmif():
    try:
        body = request.get_data(as_text=True)
        overwrite = request.args.get('overwrite')
        overwrite = True if overwrite in ('1', 't', 'true', 'True') else False
        mmif = Mmif(body)
        # Assuming the first document is the "main" one that has the AAPB GUID
        doc_id = identifier_of_first_document(mmif)
        if doc_id is None:
            return upload_error_response(ValueError("No document with identifier found in MMIF"))
        guid = guidhandler.get_aapb_guid_from(mmif[doc_id].location)
        cur_root = Path(STORAGE_DIRECTORY)

        wfid, param_dicts = generate_workflow_identifier(
            mmif, return_param_dicts=True)
        # wf_id syntax is app1name/app1version/app1paramhash/app2name/...
        segments = wfid.split('/')
        if len(segments) % 3 != 0:
            return upload_error_response(ValueError("Malformed workflow identifier"))
        mmif_fname = None
        for i in range(0, len(segments), 3):
            appn = segments[i]
            appv = segments[i + 1]
            param_hash = segments[i + 2]
            cur_root = cur_root / Path(appn) / appv / param_hash
            cur_root.mkdir(parents=True, exist_ok=True)
            with open(cur_root.with_suffix('.json'), 'w') as f:
                json.dump(param_dicts[i // 3], f, indent=2)
            mmif_fname = cur_root / f'{guid}.mmif'
        if not mmif_fname:
            return upload_no_views_response(mmif_fname)
        if mmif_fname.exists():
            if overwrite:
                with open(mmif_fname, 'w') as f:
                    f.write(body)
                return upload_overwrite_response(mmif_fname)
            else:
                return upload_not_saved_response(mmif_fname)
        else:
            with open(mmif_fname, 'w') as f:
                f.write(body)
            return upload_created_response(mmif_fname)
    except Exception as e:
        return upload_error_response(e)


def upload_no_views_response(mmif_fname):
    return jsonify(
        {"status": "warning",
         "filename": str(mmif_fname),
         "message": f"file had no contentful views and was not saved"}), 200


def upload_created_response(mmif_fname):
    return jsonify(
        {"status": "success",
         "filename": str(mmif_fname),
         "message": "file created"}), 201


def upload_not_saved_response(mmif_fname):
    return jsonify(
        {"status": "warning",
         "filename": str(mmif_fname),
         "message": "file not saved because it already exists"}), 200


def upload_overwrite_response(mmif_fname):
    return jsonify(
        {"status": "success",
         "filename": str(mmif_fname),
         "message": "file existed and was overwritten"}), 201


def upload_no_version_response(appn):
    return jsonify(
        {"status": "error",
         "message": f"app {appn} version is underspecified"}), 400


def upload_error_response(e):
    return {
        "status": "error",
        "message": f"{type(e).__name__} - {e}", }, 400


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


@bp.route(f"{API_PREFIX}/status", methods=["GET"])
def storage_analytics():
    """
    Provide analytics and status information about the current MMIF storage system.
    This method returns info on the total number of MMIF files, number of unique workflow,
    app parameters, non-terminal MMIFs, and dirty workflow MMIFs.
    """
    # TODO (ledibr @ 10/12/25): consider adding params to show/hide certain parts e.g. full workflow specs?
    response = {"total_mmif_files": 0, "total_workflows": 0, "workflows": [],
                "non_terminal_mmif_count": 0, "dirty_workflow_mmif_count": 0}
    app_specs = {}

    for root, dirs, files in os.walk(STORAGE_DIR):
        #if current_app.config.get('DEBUG'):
        #    print("Root:", root)
        #    print("dirs:", dirs)
        #    print("files:", files)

        curr_workflow = root[root.index(STORAGE_DIRECTORY) + len(STORAGE_DIRECTORY):]
        curr_workflow = curr_workflow.lstrip('/')

        json_list = [f for f in files if re.search(r'\.json$', f)]
        for subdir in dirs:
            config = subdir + '.json'
            if config in json_list:
                curr_app = curr_workflow[curr_workflow.rfind('/', 0, curr_workflow.rfind('/'))+1:]
                full_path = os.path.join(curr_app, subdir)
                with open(os.path.join(root, config), 'r') as f:
                    app_specs[full_path] = json.load(f)
                if len(app_specs[full_path]) == 0:
                    app_specs[full_path] = {}
        mmif_list = [f for f in files if re.search(r'\.mmif$', f)]
        if mmif_list:
            response["total_mmif_files"] += len(mmif_list)
            response["total_workflows"] += 1

            workflow_stats = {"path": curr_workflow, "spec": {}, "mmif_count": len(mmif_list)}
            segments = curr_workflow.split("/")
            curr_apps = ["/".join(segments[i:i + 3]) for i in range(0, len(segments), 3)]
            for i, app in enumerate(curr_apps):
                if app in app_specs:
                    workflow_stats["spec"][app] = app_specs[app]
            response["workflows"].append(workflow_stats)

            if re.search(r'-dirty', curr_workflow):
                response["dirty_workflow_mmif_count"] += len(mmif_list)
            if dirs:
                response["non_terminal_mmif_count"] += len(mmif_list)
    # TODO (ledibr @ 10/27/25): the response seems to be in alphabetical key order, not chronological.
    # given how long these might get, do we want to potentially return this differently?
    return jsonify(response)
