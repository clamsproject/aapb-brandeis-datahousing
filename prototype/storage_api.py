from mmif import Mmif
from flask import Flask, request
from enum import Enum
from pydantic import BaseModel
from typing import List, Dict
from typing_extensions import Annotated
import os
import yaml
import hashlib
import json

app = Flask(__name__)
# get post request from user
# read mmif inside post request, get view metadata
# store in nested directory relating to view metadata


@app.route("/")
def root():
    return {"message": "Storage api for pipelined mmif files"}


@app.route("/upload_mmif/", methods=["POST"])
def upload_mmif():
    body = request.get_data(as_text=True)
    # read local storage directory from config.yml
    with open('config.yml', 'r') as file:
        config = yaml.safe_load(file)
    directory = config['storage_dir']
    mmif = Mmif(body)
    # get guid from location
    # document = body.[0]['properties']['location'].split('/')[2].split('.')[0]
    document = mmif.documents['d1']['properties'].location.split('/')[2].split('.')[0]
    # append '.mmif' to guid
    document = document + '.mmif'
    # IMPORTANT: In order to enable directory creation after this loop and also store each parameter
    # dictionary in its proper directory, I create a dictionary to associate the current path level with
    # its param dict. After this loop, I create the dirs and then iterate through this dictionary to
    # place the param dicts in their proper spots.
    param_path_dict = {}
    print(directory)
    for view in mmif.views:
        print(directory)
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
        print(view_path)
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
        file_path = os.path.join(path, '.json')
        with open(file_path, "w") as f:
            json.dump(param_path_dict[path], f)
    # put mmif into the lowest level directory with filename based on guid
    file_path = os.path.join(directory, document)
    with open(file_path, "w") as f:
        f.write(mmif.serialize())
    return "Success", 201


if __name__ == "__main__":
    app.run()




