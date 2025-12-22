import os
import re
import sys
import json
import tempfile
from pathlib import Path
from dotenv import load_dotenv
from operator import itemgetter

from flask import Flask, request, jsonify, Blueprint, render_template

import mmif

from summarizer import Summary

from api import search_assets
from api.mmif_storage import StorageServerError
from api.mmif_storage import path_from_pipeline_specs, get_mmif_for_guid, storage_analytics
from api.utils import strip_prefix, StorageUnit


load_dotenv()


bp = Blueprint('www', __name__, template_folder='templates')


DEBUG = True


ASSET_DIR = os.environ.get('ASSET_DIR')
STORAGE_DIR = os.environ.get('STORAGE_DIR')


@bp.get('/www/')
@bp.get('/www/index.html')
def index():
    return render_template('index.html')


@bp.route('/www/search_assets.html', methods=['get', 'post'])
def search_assets():
    term = ''
    types = []
    paths = []
    if request.method == 'POST':
        term = request.form.get('searchterm')
        types = request.form.get('filetypes').split()
        paths = search_assets(term, types)
        paths = [str(strip_prefix(ASSET_DIR, Path(p))) for p in paths]
        paths = list(enumerate(paths))
    return render_template('search_assets.html', term=term, types=types, paths=paths)


@bp.route('/www/search_mmif.html', methods=['get', 'post'])
def search_mmif():
    # TODO: there is some overlap here with api.mmif_storage.download_mmif()
    # may need some refactoring
    guid = request.form.get('guid', '')
    pipeline = request.form.get('pipeline', '')
    debug(f'guid = {guid}')
    debug(f'pipeline = {" ".join(str(pipeline).split())}')
    status = None
    message = None
    mmif_file = None
    mmif_files = None
    pipeline_path = None
    if not pipeline:
        status = 'no-pipeline'
        message = 'Missing required parameter: need at least a pipeline'
        message = json.dumps({"message": message}, indent=2)
    else:
        pipeline_path = path_from_pipeline_specs(
            {"guid": guid, "pipeline": json.loads(pipeline)})
        debug(f'pipeline_path = {pipeline_path}')
        full_pipeline_path = os.path.join(os.environ.get('STORAGE_DIR'), pipeline_path)
        if not guid:
            # get the files at the pipeline path
            status = 'pipeline'
            mmif_files = sorted([p.stem for p in Path(full_pipeline_path).glob('*')])
            debug(f'Found {len(mmif_files)} MMIF files for pipeline')
        elif isinstance(guid, str):
            # get the one MMIF file, but check for its existence
            status = 'pipeline-guid'
            mmif_file = Path(full_pipeline_path) / f'{guid}.mmif'
            if not mmif_file.exists():
                status = 'pipeline-guid-no-files'
                message = json.dumps(
                    {"message" : f"File does not exist at that path",
                     "filename": mmif_file.name,
                     "pathname": pipeline_path}, indent=2)
    debug(f'status = {status}')
    return render_template(
        'search_mmif.html',
        status=status, message=message, guid=guid, pipeline=pipeline,
        path=pipeline_path, mmif_file=mmif_file, mmif_files=mmif_files)


@bp.get('/www/browse_paths.html')
def browse_paths():
    def is_derived(path):
        return path.name.endswith('.summ.json') or path.name.endswith('.desc.json')
    path = Path(request.args.get("path", STORAGE_DIR))
    path_for_display = Path(*path.parts[len(Path(STORAGE_DIR).parts):])
    debug(f'base = {Path(STORAGE_DIR)}')
    debug(f'path = {path_for_display}')
    subs = list(sorted(path.iterdir())) if path.is_dir() else []
    subs = [sub for sub in subs if not is_derived(sub)]
    # At the moment the template distinguishes between property files and MMIF 
    # simply by using the extension. There may be a use case for doing it here
    # and use somehwhat more sophisticated code like using a regular expression
    # to get the property file: re.match("[0-9a-z]{32}\.json", path.name
    return render_template(
        'browse_paths.html', path=path_for_display, subs=subs)


@bp.get('/www/view_parameters.html')
def view_parameters():
    path = Path(request.args.get("path"))
    parameters = json.dumps(json.loads(path.read_text()), indent=2)
    size = path.stat().st_size
    size_str = f'{size:,d}'
    return render_template(
        'view_parameters.html', path=path, size=size_str, parameters=parameters)


@bp.get('/www/view_mmif.html')
def view_file():
    mode = request.args.get("mode")
    path = Path(request.args.get("path"))
    unit = StorageUnit(STORAGE_DIR, path)
    debug(f'mode = {mode}')
    return render_template('view_mmif.html', mode=mode, unit=unit, path=unit.path)


@bp.get('/www/analytics.html')
def analytics():
    analytics = json.loads(storage_analytics().data)
    properties = {p: analytics[p] for p in analytics.keys() if p != 'pipelines'}
    pipelines = sorted(analytics['pipelines'], key=itemgetter('path'))
    for pl in pipelines:
        pl['full_path'] = Path(STORAGE_DIR) / pl['path']
    return render_template(
        'analytics.html', properties=properties, pipelines=pipelines)


def debug(message: str):
    if DEBUG:
        print(f'DEBUG {message}')


'''

Zero-guid scenario example:

curl -X POST 127.0.0.1:8001/storeapi/download \
    -H 'Content-Type: "application/json"' \
    -d '{"pipeline": {"chyron-detection/v1.0": {}}}'

GUID: None
Pipeline: {"chyron-detection/v1.0": {}}


Single-guid scenario example:

curl -X POST 127.0.0.1:8001/storeapi/download \
    -H 'Content-Type: "application/json"' \
    -d '
    {
        "pipeline": { "chyron-detection/v1.0": {} },
        "guid": "cpb-aacip-525-028pc2v94s"
    }'

GUID: cpb-aacip-525-028pc2v94s
Pipeline: {"chyron-detection/v1.0": {}}

'''

