import hashlib
import io
import json
import os
import re
import zipfile as zf
from collections import Counter
from pathlib import Path
from typing import List, Dict, Tuple
from zipfile import ZIP_DEFLATED

from clams_utils.aapb import guidhandler
from flask import request, jsonify, Blueprint, current_app, send_file
from mmif import Mmif
from mmif import utils
from mmif.utils.workflow_helper import _split_appname_appversion
from mmif.utils.workflow_helper import generate_param_hash
from mmif.utils.workflow_helper import group_views_by_app

from api import STORAGE_DIRECTORY

# make blueprint of app to be used in __init__.py
bp = Blueprint(__file__.split(os.sep)[-1].split('.')[0].replace('_', '-'), __name__)
# get post request from user
# read mmif inside post request, get view metadata
# store in nested directory relating to view metadata


API_PREFIX = '/storeapi'


class StorageServerError(Exception):
    pass


def identifier_of_first_document(mmif_file: Mmif):
    for doc in mmif_file.documents:
        if doc.id:
            return doc.id
    return None


def generate_workflow_identifier(data: Mmif) -> Tuple[str, List[Dict]]:
    """
    Mostly copied from mmif.utils.workflow_helper.generate_workflow_identifier version 1.2.1
    with addition of getting the raw parameter dicts.
    TODO In the future when mmif.utils.workflow_helper.generate_workflow_identifier supports returning
    parameter dicts, we can switch to that.
    """
    segments = []
    # First prefix is source information, sorted by document type
    sources = Counter(doc.at_type.shortname for doc in data.documents)
    segments.append('-'.join([f'{k}-{sources[k]}' for k in sorted(sources.keys())]))

    # Group views into runs
    grouped_apps = group_views_by_app(data.views)

    param_dicts = []
    for app_execution in grouped_apps:
        # Use the first view in the run as representative for metadata
        first_view = app_execution[0]

        # Skip runs where the representative view has errors or warnings
        if first_view.has_error() or first_view.has_warnings():
            continue

        app = first_view.metadata.get("app")
        if app is None:
            continue
        app_name, app_version = _split_appname_appversion(app)

        # Use raw parameters from the first view for reproducibility
        try:
            param_dict = first_view.metadata.parameters
        except (KeyError, AttributeError):
            param_dict = {}
        param_dicts.append(param_dict)

        param_hash = generate_param_hash(param_dict)

        # Build segment: app_name/version/hash
        name_str = app_name if app_name else "unknown"
        version_str = app_version if app_version else "unversioned"
        segments.append(f"{name_str}/{version_str}/{param_hash}")

    return '/'.join(segments), param_dicts


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

        wfid, param_dicts = generate_workflow_identifier(mmif)
        # wf_id syntax is source_info/app1name/app1version/app1paramhash/app2name/...
        # need to pull appname/appversion from the id and find corresponding views to extract params from view metadata
        segments = wfid.split('/')
        # start from the first "source info" segment
        cur_root = cur_root / Path(segments[0])
        segments = segments[1:]
        # make sure segments is multiple of 3
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
    data = json.loads(request.data.decode('utf-8'))
    # get both pipeline and guid from data
    # obtain pipeline using helper method
    pipeline = generate_workflow_identifier(data)
    # get number of views for rewind if necessary
    num_views = len(data.get('pipeline', []))
    guid = data.get('guid')
    # validate existence of pipeline, guid is not necessary if you just want the pipeline returned
    if not pipeline:
        return jsonify({'error': 'Missing required parameters: need at least a pipeline'})
    # load environment variables to concat pipeline with local storage path
    directory = os.environ.get('STORAGE_DIR')
    pipeline = os.path.join(directory, pipeline)
    if not guid:
        return zero_guid_download_response(pipeline)
    # Checking if the GUID is a single value or a list
    if not isinstance(guid, list):
        return single_guid_download_response(pipeline, guid, num_views)
    else:
        return multi_guid_download_response(pipeline, guid, num_views)


def parse_parameters(view):
    """
    Convert the parameter dictionary to a string and then hash it, this hash will be
    the name of another subdirectory of the path. Return the dictionary and the hash.
    """
    try:
        param_dict = view.metadata.parameters
        param_list = ['='.join([k, str(v)]) for k, v in param_dict.items()]
        param_list.sort()
        param_string = ','.join(param_list)
    except KeyError:
        param_dict = ""
        param_string = ""
    # hash the (sorted and concatenated list of params) string and join with path
    # NOTE: this is *not* for security purposes, so the usage of md5 is not an issue.
    param_hash = hashlib.md5(param_string.encode('utf-8')).hexdigest()
    return param_dict, param_hash


def zero_guid_download_response(pipeline: str):
    """
    For a "zero-guid" request, the user will receive just the local storage pipeline
    and the list of files found there. This allows clients to utilize the api without
    downloading files (for working with local files).
    """
    filenames = [p.stem for p in Path(pipeline).glob('*')]
    return jsonify({'pipeline': pipeline, 'filenames': filenames})


def single_guid_download_response(pipeline: str, guid: str, num_views: int):
    """
    When retrieving the MMIF object for a pipeline and a single GUID, just return
    the MMIF object or an error if the search failed.
    """
    try:
        mmif = get_mmif_for_guid(pipeline, guid, num_views)
        return mmif
    except StorageServerError as e:
        return {"error": str(e)}, 201


def multi_guid_download_response(pipeline: str, guids: list, num_views: int):
    """
    When retrieving multiple MMIFs for a pipeline, we construct a json object to
    store each guid as a key and each MMIF as the value.
    """
    errors = dict()
    mem_file = io.BytesIO()
    with zf.ZipFile(mem_file, 'w', ZIP_DEFLATED) as mmif_zip:
        for guid in guids:
            try:
                # mmif = get_mmif_for_guid(pipeline, guid, num_views)
                # instead of using get_mmif_for_guid and needing to re-dump mmif
                mmif_name = guid + ".mmif"
                path = os.path.join(pipeline, mmif_name)
                mmif_zip.write(filename=path, arcname=f'multi-guid-response/files/{mmif_name}')
            except FileNotFoundError:
                errors[guid] = {"Error": f"Did not find {guid}"}
        mmif_zip.writestr(zinfo_or_arcname="multi-guid-response/pipeline_path.txt", data=pipeline)
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


def get_mmif_for_guid(pipeline: str, guid: str, num_views: int):
    """
    Retrieve the MMIF file for a pipeline and GUID. If none was found raise a
    StorageServerError.
    """
    guid = guid + ".mmif"
    path = os.path.join(pipeline, guid)
    # if filepath exists, we can return it
    try:
        with open(path, 'r') as file:
            mmif = json.loads(file.read())
        return mmif
    # otherwise we will use the rewinder to check if the user provided a prefix of a
    # mmif pipeline that we have previously stored
    except FileNotFoundError:
        try:
            return rewind_time(pipeline, guid, num_views)
        except FileNotFoundError:
            # the rewinder does not always succeed so we catch this exception again
            # and raise an application-specific exception
            raise StorageServerError(f'Did not find: {guid.split(".")[0]}')


def rewind_time(pipeline, guid, num_views):
    """
    This method takes in a pipeline (path), a guid, and a number of views, and uses
    os.walk to iterate through directories that begin with that pipeline. It takes
    the first mmif file that matches the guid and uses the rewind feature to include
    only the views indicated by the pipeline.
    """
    for home, dirs, files in os.walk(pipeline):
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
    This method returns info on the total number of MMIF files, number of unique pipelines,
    app parameters, non-terminal MMIFs, and dirty pipeline MMIFs.
    """
    # TODO (ledibr @ 10/12/25): consider adding params to show/hide certain parts e.g. full pipeline specs?
    response = {"total_mmif_files": 0, "total_pipelines": 0, "pipelines": [],
                "non_terminal_mmif_count": 0, "dirty_pipeline_mmif_count": 0}
    app_specs = {}

    for root, dirs, files in os.walk(STORAGE_DIRECTORY):
        if current_app.config.get('DEBUG'):
            print("Root:", root)
            print("dirs:", dirs)
            print("files:", files)

        curr_pipeline = root[root.index(STORAGE_DIRECTORY) + len(STORAGE_DIRECTORY):]
        curr_pipeline = curr_pipeline.lstrip('/')

        json_list = [f for f in files if re.search(r'\.json$', f)]
        for subdir in dirs:
            config = subdir + '.json'
            if config in json_list:
                curr_app = curr_pipeline[curr_pipeline.rfind('/', 0, curr_pipeline.rfind('/'))+1:]
                full_path = os.path.join(curr_app, subdir)
                with open(os.path.join(root, config), 'r') as f:
                    app_specs[full_path] = json.load(f)
                if len(app_specs[full_path]) == 0:
                    app_specs[full_path] = {}
        mmif_list = [f for f in files if re.search(r'\.mmif$', f)]
        if mmif_list:
            response["total_mmif_files"] += len(mmif_list)
            response["total_pipelines"] += 1

            pipeline_stats = {"path": curr_pipeline, "spec": {}, "mmif_count": len(mmif_list)}
            segments = curr_pipeline.split("/")
            curr_apps = ["/".join(segments[i:i + 3]) for i in range(0, len(segments), 3)]
            for i, app in enumerate(curr_apps):
                if app in app_specs:
                    pipeline_stats["spec"][app] = app_specs[app]
            response["pipelines"].append(pipeline_stats)

            if re.search(r'-dirty', curr_pipeline):
                response["dirty_pipeline_mmif_count"] += len(mmif_list)
            if dirs:
                response["non_terminal_mmif_count"] += len(mmif_list)
    # TODO (ledibr @ 10/27/25): the response seems to be in alphabetical key order, not chronological.
    # given how long these might get, do we want to potentially return this differently?
    return jsonify(response)
