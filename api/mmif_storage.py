import hashlib
import json
import os
from pathlib import Path

from clams import mmif_utils
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


def split_appname_appversion(long_app_id):
    """
    Helper method for splitting the app name and version number from a json string.
    This assumes the identifier is in the form of "uri://APP_DOMAIN/APP_NAME/APP_VERSION"
    """
    try:
        _, appname, appversion = long_app_id.rsplit('/', maxsplit=2)
    except ValueError:
        return long_app_id, None
    if appname.endswith(appversion):
        appname = appname[:-len(appversion) - 1]
    if appname.endswith('/'):
        appname = appname[:-1]
    if appversion == 'unresolvable':
        appversion = None
    return appname, appversion


@bp.route(f"{API_PREFIX}/upload", methods=["POST"])
def upload_mmif():
    body = request.get_data(as_text=True)
    # read local storage directory from .env
    directory = os.environ.get('STORAGE_DIR')
    mmif = Mmif(body)
    # get guid from the FIRST document in the mmif
    # TODO (krim @ 3/21/25): hardcoding of document id might be a bad idea, fix this after https://github.com/clamsproject/mmif-python/pull/304 is merged
    guid = guidhandler.get_aapb_guid_from(mmif.get_document_by_id('d1').location)
    cur_root = Path(STORAGE_DIRECTORY)
    mmif_fname = None
    for view_i, view in enumerate(mmif.views):

        # now we want to convert the parameter dictionary to a string and then hash it.
        # this hash will be the name of another subdirectory.
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
        appp = param_hash
        appn, appv = split_appname_appversion(view.metadata.app)
        if appv is None:
            return jsonify({'error': f'app {appn} version is underspecified'}), 400
        # TODO (krim @ 3/21/25): we might want "sanitize" appn, appv, appp to make sure they are valid directory names
        cur_root = cur_root / appn / appv / appp
        cur_root.mkdir(parents=True, exist_ok=True)
        with open(cur_root.parent / f'{appp}.json', 'w') as f:
            json.dump(param_dict, f, indent=2)
    if not mmif_fname:
        return jsonify({'error': 'no contentful views in the mmif'}), 400
    if mmif_fname.exists():
        msg = f"File already exists: {mmif_fname}\n"
    else:
        with open(mmif_fname, 'w') as f:
            f.write(mmif.serialize())
            msg = f"Successfully stored: {mmif_fname}\n"
    return msg, 201


@bp.route(f"{API_PREFIX}/download", methods=["POST"])
def download_mmif():
    data = json.loads(request.data.decode('utf-8'))
    # get both pipeline and guid from data
    # obtain pipeline using helper method
    pipeline = pipeline_from_param_json(data)
    # get number of views for rewind if necessary
    num_views = len(data['pipeline'])
    guid = data.get('guid')
    # validate existence of pipeline, guid is not necessary if you just want the pipeline returned
    if not pipeline:
        return jsonify({'error': 'Missing required parameters: need at least a pipeline'})
    # load environment variables to concat pipeline with local storage path
    directory = os.environ.get('STORAGE_DIR')
    pipeline = os.path.join(directory, pipeline)
    # if this is a "zero-guid" request, the user will receive just the local storage pipeline
    # this allows clients to utilize the api without downloading files (for working with local files)
    if not guid:
        return jsonify({'pipeline': pipeline})
    # CHECK IF GUID IS SINGLE VALUE OR LIST
    if not isinstance(guid, list):
        guid = guid + ".mmif"
        # get file from storage directory
        path = os.path.join(pipeline, guid)
        # if file exists, we can return it
        try:
            with open(path, 'r') as file:
                mmif = file.read()
            return mmif
        # otherwise we will use the rewinder
        # this assumes the user has provided a subset of a mmif pipeline that we have previously stored
        # in the case where this is not true, we return a FileNotFound error.
        except FileNotFoundError:
            return rewind_time(pipeline, guid, num_views)
    else:
        # in the case where we want multiple mmifs retrieved, we construct a json to store
        # each guid as a key and each mmif as the value.
        mmifs_by_guid = dict()
        for curr_guid in guid:
            curr_guid = curr_guid + ".mmif"
            # get file from storage directory
            path = os.path.join(pipeline, curr_guid)
            # if file exists, we can put it in the json
            try:
                with open(path, 'r') as file:
                    mmif = file.read()
                # place serialized mmif into dictionary/json with guid key (remove file ext)
                mmifs_by_guid[curr_guid.split('.')[0]] = mmif
            # otherwise we will use the rewinder
            # as with the single-guid case, this assumes the pipeline is a proper subset of
            # another guid-matching mmif's pipeline.
            # otherwise we store a string representing the lack of a file for that guid.
            except FileNotFoundError:
                try:
                    mmif = rewind_time(pipeline, curr_guid, num_views)
                    mmifs_by_guid[curr_guid.split('.')[0]] = mmif
                except FileNotFoundError:
                    # TODO: figure out a good way to mark file not found
                    mmifs_by_guid[curr_guid.split('.')[0]] = "File not found"
        # now turn the dictionary into a json and return it
        return json.dumps(mmifs_by_guid)


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


def rewind_time(pipeline, guid, num_views):
    """
    This method takes in a pipeline (path), a guid, and a number of views, and uses os.walk to iterate through
    directories that begin with that pipeline. It takes the first mmif file that matches the guid and uses the
    rewind feature to include only the views indicated by the pipeline.
    """
    for home, dirs, files in os.walk(pipeline):
        # find mmif with matching guid to rewind
        for file in files:
            if guid == file:
                # rewind the mmif
                with open(os.path.join(home, file), 'r') as f:
                    mmif = Mmif(f.read())
                    # we need to calculate the number of views to rewind
                    rewound = mmif_utils.rewind.rewind_mmif(mmif, len(mmif.views) - num_views)
                return rewound.serialize()
    raise FileNotFoundError
