from mmif import Mmif
from clams import mmif_utils
from flask import Flask, request, jsonify, send_from_directory
from enum import Enum
from pydantic import BaseModel
from typing import List, Dict
from typing_extensions import Annotated
import os
import yaml
import hashlib
import json
from dotenv import load_dotenv


app = Flask(__name__)
# get post request from user
# read mmif inside post request, get view metadata
# store in nested directory relating to view metadata

# TODO: this app accepts "unresolvable" as an app version number; it needs to be fixed because
# TODO: "unresolvable" is not specific and can represent multiple versions.


@app.route("/")
def root():
    return {"message": "Storage api for pipelined mmif files"}


@app.route("/storeapi/mmif/", methods=["POST"])
def upload_mmif():
    body = request.get_data(as_text=True)
    # read local storage directory from .env
    load_dotenv()
    directory = os.getenv('storage_dir')
    mmif = Mmif(body)
    # get guid from location
    document = mmif.documents['d1']['properties'].location.split('/')[2].split('.')[0]
    # append '.mmif' to guid
    document = document + '.mmif'
    # IMPORTANT: In order to enable directory creation after this loop and also store each parameter
    # dictionary in its proper directory, I create a dictionary to associate the current path level with
    # its param dict. After this loop, I create the dirs and then iterate through this dictionary to
    # place the param dicts in their proper spots.
    param_path_dict = {}
    for view in mmif.views:
        # this should return the back half of the app url, so just app name and version number
        subdir_list = view.metadata.app.split('/')[3:]
        # create path string for this view
        view_path = os.path.join('', *subdir_list)
        # now we want to convert the parameter dictionary to a string and then hash it.
        # this hash will be the name of another subdirectory.
        try:
            param_dict = view.metadata["parameters"]
            param_list = ['='.join(pair) for pair in param_dict.items()]
            param_list.sort()
            param_string = ','.join(param_list)
        except KeyError:
            param_dict = ""
            param_string = ""
        # hash the (sorted and concatenated list of params) string and join with path
        # NOTE: this is *not* for security purposes, so the usage of md5 is not an issue.
        param_hash = hashlib.md5(param_string.encode('utf-8')).hexdigest()
        view_path = os.path.join(view_path, param_hash)
        # check if this is a duplicate view. if it is, skip the current view.
        # NOTE: duplicate views are those with the same app, version number, AND parameter dict.
        if view_path in directory:
            continue
        # create path by joining directory with the current view path
        directory = os.path.join(directory, view_path)
        # now that we know it's not a duplicate view and we have the proper path location, we
        # store it and the associated param dict inside param_path_dict.
        param_path_dict[directory] = param_dict
    # we have finished looping through the views. now time to create the directories
    # and dump the param dicts
    os.makedirs(directory, exist_ok=True)
    for path in param_path_dict:
        file_path = os.path.join(os.path.dirname(path), 'parameters.json')
        with open(file_path, "w") as f:
            json.dump(param_path_dict[path], f)
    # put mmif into the lowest level directory with filename based on guid
    file_path = os.path.join(directory, document)
    with open(file_path, "w") as f:
        f.write(mmif.serialize())
    return "Success", 201


@app.route("/searchapi/mmif/", methods=["POST"])
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
    load_dotenv()
    directory = os.getenv('storage_dir')
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




if __name__ == "__main__":
    app.run(port=8912)




