import mmif
from fastapi import FastAPI
from enum import Enum
from pydantic import BaseModel
from typing import List, Dict
import os
import json

app = FastAPI()
# get post request from user
# read mmif inside post request, get view metadata
# store in nested directory relating to view metadata

# TODO: there's probably a better structure for this. Not sure if this works at the moment
# TODO: but either way should hopefully be changed to utilize mmif operations?
class Item(BaseModel):
    views: List[Dict[str, any]]
    documents: List[Dict[str, any]]
    data: Dict[str, any]

@app.get("/")
async def root():
    return {"message": "Storage api for pipelined mmif files"}

@app.post("/upload_mmif/")
async def upload_mmif(item:Item):
    directory = "/mmif_storage/"
    # get guid from location
    document = item.documents[0]['properties']['location'].split('/')[2].split('.')[0]
    # append '.mmif' to guid
    document = document + '.mmif'
    for view in item.views:
        # this should return the back half of the app url, so just app name and version number
        subdir_list = view['metadata']['app'].split('/')[3:]
        # create path by joining current directory with the subdirs from current metadata
        # TODO: path separators may not be correct when doing this, also maybe typing issue (any)?
        directory = os.path.join(directory, *subdir_list)
    # make directory
    os.makedirs(directory, exist_ok=True)
    # make final filepath
    file_path = os.path.join(directory, document)
    with open(file_path, "w") as f:
        json.dump(item.dict(), f)




