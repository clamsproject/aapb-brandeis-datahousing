import hashlib
import json
import os
from pathlib import Path

from mmif import utils
from clams_utils.aapb import guidhandler
from flask import request, jsonify, Blueprint
from mmif import Mmif

from api import STORAGE_DIRECTORY


# make blueprint of app to be used in __init__.py
bp = Blueprint(__file__.split(os.sep)[-1].split('.')[0].replace('_', '-'), __name__)
# get post request from user
# read mmif inside post request, get view metadata
# store in nested directory relating to view metadata


API_PREFIX = '/storeapi'


class StorageServerError(Exception):
    pass


def split_appname_appversion(long_app_id):
    """
    Helper method for splitting the app name and version number from a string. This
    assumes the long identifier looks like "uri://APP_DOMAIN/APP_NAME/APP_VERSION"
    """
    app_path = Path(long_app_id).parts
    app_name = app_path[2] if len(app_path) > 2 else None
    app_version = app_path[3] if len(app_path) > 3 else None
    if app_version is not None and app_name.endswith(app_version):
        app_name = app_name[:-len(app_version) - 1]
    if app_version == 'unresolvable':
        app_version = None
    return app_name, app_version


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
        # TODO (krim @ 3/21/25): hardcoding of document id might be a bad idea,
        # fix this after https://github.com/clamsproject/mmif-python/pull/304 is merged
        # NOTE (marc @ 4/15/25): I had examples where the identifier was not 'd1' so I got 
        # rid of the hard-wired doc id with the hack below awaiting the merge above
        identifier = identifier_of_first_document(mmif)
        guid = guidhandler.get_aapb_guid_from(mmif.get_document_by_id(identifier).location)
        cur_root = Path(STORAGE_DIRECTORY)
        last_suffix = None
        mmif_fname = None
        for view in mmif.views:
            if not view.annotations and view.metadata.warnings:
                # skip "warning" views
                continue
            param_dict, param_hash = parse_parameters(view)
            appn, appv = split_appname_appversion(view.metadata.app)
            if appv is None:
                return upload_no_version_response(appn)
            # TODO (krim @ 3/21/25): we might want "sanitize" appn and appv to make sure
            # they are valid directory names
            cur_suffix = Path(appn) / appv / param_hash
            if cur_suffix != last_suffix:
                cur_root = cur_root / cur_suffix
                last_suffix = cur_suffix
            cur_root.mkdir(parents=True, exist_ok=True)
            with open(cur_root.parent / f'{param_hash}.json', 'w') as f:
                json.dump(param_dict, f, indent=2)
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
    pipeline = pipeline_from_param_json(data)
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
        param_list = ['='.join(pair) for pair in param_dict.items()]
        param_list.sort()
        param_string = ','.join(param_list)
    except KeyError:
        param_dict = ""
        param_string = ""
    # hash the (sorted and concatenated list of params) string and join with path
    # NOTE: this is *not* for security purposes, so the usage of md5 is not an issue.
    param_hash = hashlib.md5(param_string.encode('utf-8')).hexdigest()
    return param_dict, param_hash


# helper method for extracting pipeline
def pipeline_from_param_json(param_json):
    """
    This method reads in a json containing the names of the pipelined apps and their
    respective parameters, and then builds a path out of the pipelined apps and hashed
    parameters.
    """
    pipeline = ""
    for clams_app in param_json["pipeline"]:
        # not using os path join until later for testing purposes
        pipeline = pipeline + "/" + clams_app
        # try to get param items
        try:
            param_list = ['='.join(pair) for pair in param_json["pipeline"][clams_app].items()]
            param_list.sort()
            param_string = ','.join(param_list)
        # throws attribute error if empty (because empty means it's a set and not dict)
        except AttributeError:
            param_string = ""
        # hash parameters
        param_hash = hashlib.md5(param_string.encode('utf-8')).hexdigest()
        pipeline = pipeline + "/" + param_hash
    # removing first "/" so it doesn't mess with os.path.join later
    pipeline = pipeline[1:]
    return pipeline


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
    mmifs_by_guid = dict()
    for guid in guids:
        response = single_guid_download_response(pipeline, guid, num_views)
        try:
            mmif = get_mmif_for_guid(pipeline, guid, num_views)
            mmifs_by_guid[guid] = mmif
        except StorageServerError as e:
            mmifs_by_guid[guid] = {"error": str(e)}
    return mmifs_by_guid


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
