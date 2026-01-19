import os
import re
import sys
import json
import tempfile
from pathlib import Path
from dotenv import load_dotenv
from operator import itemgetter

from flask import Flask, request, jsonify, Blueprint, render_template
from jinja2 import Template

import mmif

import inspector as mmif_inspector
from inspector.inspect import Summary
from inspector.config import INDEX_PAGE, CSS_PAGE, JS_PAGE, VIEWS_PAGE
from inspector.config import TIMEFRAMES_PAGE, CORRELATIONS_PAGE, TRANSCRIPT_PAGE
from inspector.config import CAPTIONS_PAGE, ENTITIES_PAGE

from api import search_assets
from api.mmif_storage import StorageServerError
from api.mmif_storage import path_from_pipeline_specs, get_mmif_for_guid, storage_analytics
from api.utils import strip_prefix, ServerDirectory, MmifFile, ParameterFile


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
def search_asset():
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
    sdir = ServerDirectory(STORAGE_DIR, request.args.get("path"))
    return render_template('browse_paths.html', sdir=sdir)


@bp.get('/www/view_parameters.html')
def view_parameters():
    pfile = ParameterFile(STORAGE_DIR, request.args.get("path"))
    return render_template('view_parameters.html', pfile=pfile)


@bp.get('/www/view_mmif.html')
def view_file():
    mode = request.args.get("mode")
    mfile = MmifFile(STORAGE_DIR, Path(request.args.get("path")))
    debug(f'mode = {mode}')
    if mode in ('summary', 'collapsible'):
        # Doing this upfront (unlike with the description) to avoid issues with
        # the summary size later.
        debug(f'Creating summary for {mfile.path.name}')
        mfile.create_summary()
    return render_template('view_mmif.html', mfile=mfile, mode=mode)


@bp.get('/www/inspector.html')
def inspector():
    templates_dir = Path(mmif_inspector.__file__).parent / 'templates'
    mmif_file = Path(request.args.get("path"))
    summ_file = Path(STORAGE_DIR) / mmif_file.parent / f'{mmif_file.stem}.summ.json'
    # TODO: assumes the summary exists, may need a test here or in the template
    summary = json.loads(summ_file.read_text())
    template_file = Path(templates_dir) / 'index.html'
    template = Template(template_file.read_text())
    rendered_template = template.render(summary=Summary(summ_file, summary))
    return render_template
    #return (
    #    f'<table cellpadding=8 cellspacing=0 border=1>\n'
    #    f'<tr><td>MMIF File</td><td>{mmif_file}</td></tr>\n'
    #    f'<tr><td>Summary</td><td>{summ_file}</td></tr>\n')


def inspector_table(path, summary, inspector, related_items):
    return (
        "<table cellspacing=0 cellpadding=8 border=1>\n"
        + f"<tr><td>path</td><td>{str(path)}</td>\n"
        + f"<tr><td>parent</td><td>{str(path.parent)}</td>\n"
        + f"<tr><td>name</td><td>{path.name}</td>\n"
        + f"<tr><td>related</td><td>{str([r.name for r in related_items])}</td>\n"
        + f"<tr><td>summary</td><td>{str(summary)}</td>\n"
        + f"<tr><td>summary exists</td><td>{summary.exists()}</td>\n"
        + f"<tr><td>inspector</td><td>{inspector}</td>\n"
        + f"<tr><td>inspector exists</td><td>{inspector.exists()}</td>\n"
        + "<table>\n")


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

