import os
import re
import json
import tempfile
from pathlib import Path
from dotenv import load_dotenv
from operator import itemgetter

from flask import Flask, request, jsonify, Blueprint, render_template

from summarizer import Summary

from api import search_assets
from api.mmif_storage import StorageServerError
from api.mmif_storage import path_from_pipeline_specs, get_mmif_for_guid, storage_analytics


load_dotenv()


bp = Blueprint('www', __name__, template_folder='templates')


DEBUG = True


STORAGE_DIR = os.environ.get('STORAGE_DIR')


@bp.get('/www/')
@bp.get('/www/index.html')
def index():
    return render_template('index.html')


@bp.route('/www/search_assets.html', methods=['get', 'post'])
def assets():
    term = None
    types = None
    paths = []
    if request.method == 'POST':
        term = request.form.get('searchterm')
        types = request.form.get('filetypes')
        paths = search_assets(term, types)
    types = [] if types is None else types.split()
    return render_template('assets.html', term=term, types=types, paths=paths)


@bp.route('/www/search_mmif.html', methods=['get', 'post'])
def mmif_files():
    # TODO: there is some overlap here with api.mmif_storage.download_mmif()
    # may need some refactoring
    guid = ''
    pipeline = ''
    result = ''
    result_header = ''
    if request.method == 'POST':
        guid = request.form.get('guid')
        pipeline = request.form.get('pipeline')
        debug(f'{guid} {pipeline}')
        if not pipeline:
            message = 'Missing required parameter: need at least a pipeline'
            result = jsonify({'error': message}).data.decode('utf-8')
        else:
            pipeline_path = path_from_pipeline_specs({"guid": guid, "pipeline": json.loads(pipeline)})
            debug(f'{guid} [{pipeline_path}]')
            # create full absolute pipeline path using the STORAGE_DIR environment variable
            full_pipeline_path = os.path.join(os.environ.get('STORAGE_DIR'), pipeline_path)
            if not guid:
                filenames = [p.stem for p in Path(full_pipeline_path).glob('*')]
                result_dict = {"pipeline": pipeline_path, "filenames": filenames}
                result_header = 'Pipeline path and filenames'
                result = json.dumps(result_dict, indent=2)
            elif not isinstance(guid, list):
                result_header = 'MMIF File'
                try:
                    num_apps = len(json.loads(pipeline))
                    mmif = get_mmif_for_guid(full_pipeline_path, guid, num_apps)
                    result = jsonify(mmif).data.decode("utf-8")
                except StorageServerError as e:
                    result = jsonify({"error": str(e)}).data.decode('utf-8')
            else:
                result = {}
    return render_template(
        'mmif_files.html',
        guid=guid, pipeline=pipeline, result=result, result_header=result_header)


@bp.get('/www/browse_paths.html')
def browse():
    path = Path(request.args.get("path", STORAGE_DIR))
    path_for_display = Path(*path.parts[len(Path(STORAGE_DIR).parts):])
    debug(f'base = {Path(STORAGE_DIR)}')
    debug(f'path = {path_for_display}')
    subs = []
    header = ''
    content = ''
    app_spec = False
    # For a directory, get the directories and files contained in it
    if path.is_dir():
        subs = list(path.iterdir())
    # For a JSON file with app specifications, just load those specs
    elif re.match("[0-9a-z]{32}\.json", path.name):
        app_spec = True
        header = 'App specifications'
        content = jsonify(json.loads(path.read_text())).data.decode('utf-8')
    # For a MMIF file, get its summary
    else:
        debug(f'Summarizing {path_for_display}')
        summary = Summary(path)
        summary_file = Path(tempfile.gettempdir()) / 'summary.json'
        debug(f'Summary file: {summary_file}')
        summary.report(outfile=summary_file, full=True)
        header = 'Summary of MMIF file'
        content = summary_file.read_text()
    debug(f'header={header} subs={len(subs)}')
    return render_template(
        'paths.html',
        path=path_for_display, subs=sorted(subs), app_spec=app_spec,
        header=header, content=content)


@bp.get('/www/collapsible_mmif.html')
def collapsible_mmif():
    path = Path(STORAGE_DIR) / request.args.get("path")
    path_for_display = Path(*path.parts[len(Path(STORAGE_DIR).parts):])
    debug(path)
    # TODO: same as above, refactor
    debug(f'Summarizing {path_for_display}')
    summary = Summary(path)
    summary_file = Path(tempfile.gettempdir()) / 'summary.json'
    debug(f'Summary file: {summary_file}')
    summary.report(outfile=summary_file, full=True)
    header = 'Summary of MMIF file'
    content = summary_file.read_text()
    return render_template(
        'collapsible.html', path=path_for_display, header=header, content=content)


@bp.get('/www/analytics.html')
def analytics():
    analytics = json.loads(storage_analytics().data)
    print(type(analytics['pipelines']))
    print(analytics['pipelines'][0])
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

