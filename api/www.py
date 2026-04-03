import os
import re
import io
import sys
import json
import tempfile
from pathlib import Path
from dotenv import load_dotenv
from operator import itemgetter

from flask import Flask, request, jsonify, Blueprint, render_template
from jinja2 import Template

import mmif

import inspector
from inspector.inspect import Summary
from inspector.config import INDEX_PAGE, CSS_PAGE, JS_PAGE, VIEWS_PAGE
from inspector.config import TIMEFRAMES_PAGE, CORRELATIONS_PAGE, TRANSCRIPT_PAGE
from inspector.config import CAPTIONS_PAGE, ENTITIES_PAGE

from api.assets import search_assets
from api.errors import StorageServerError
from api.mmif_download import get_mmif_for_guid
from api.analytics import storage_analytics
from api.utils import strip_prefix, ServerDirectory, MmifFile, ParameterFile
from api.utils import hash_from_dictionary


load_dotenv()


bp = Blueprint('www', __name__, template_folder='templates')
print(f'{bp} import_name={bp.import_name} __name__={__name__}')


DEBUG = True


ASSET_DIR = os.environ.get('ASSET_DIR')
STORAGE_DIR = os.environ.get('STORAGE_DIR')


# TODO: this is a patch to make this works with the recent merge from feature
# branch pipeline_id-gen-on-sdk, should be replaced with an appropriate helper
# from the mmif.utils package.
def path_from_pipeline_specs(pipeline_spec: dict):
    """
    Helper method to read in a json object containing the names of the pipelined
    apps and their parameters, and then build a path out of the pipelined apps
    and hashed parameters.
    """
    pipeline_path = ""
    for clams_app in pipeline_spec["pipeline"]:
        # TODO: should probably use pathlib.Path
        param_hash = hash_from_dictionary(pipeline_spec["pipeline"][clams_app])
        pipeline_path += f"/{clams_app}/{param_hash}"
    # removing first "/" so it doesn't mess with os.path.join later
    return pipeline_path[1:]


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


@bp.get('/www/inspector/index.html')
def inspector_index():
    data = InspectorData('index.html')
    rendered_template = data.template.render(summary=Summary(data.summ_file, data.summary))
    return update_rendered(rendered_template, data.css_file)


@bp.get('/www/inspector/views.html')
def inspector_views():
    return display_inspector_page('views.html')


@bp.get('/www/inspector/timeframes.html')
def inspector_timeframes():
    data = InspectorData('timeframes.html')
    rendered_template = data.template.render(summary=Summary(data.summ_file, data.summary))
    return update_rendered(rendered_template, data.css_file, data.js_file)


@bp.get('/www/inspector/transcript.html')
def inspector_transcript():
    data = InspectorData('transcript.html')
    rendered_template = data.template.render(summary=Summary(data.summ_file, data.summary))
    return update_rendered(rendered_template, data.css_file, data.js_file)


@bp.get('/www/inspector/captions.html')
def inspector_captions():
    data = InspectorData('captions.html')
    rendered_template = data.template.render(summary=Summary(data.summ_file, data.summary))
    return update_rendered(rendered_template, data.css_file, data.js_file)


def display_inspector_page(page_name: str) -> str:
    data = InspectorData(page_name)
    rendered_template = data.template.render(summary=Summary(data.summ_file, data.summary))
    return update_rendered(rendered_template, data.css_file, data.js_file)


@bp.get('/www/analytics.html')
def analytics():
    analytics = json.loads(storage_analytics().data)
    properties = {p: analytics[p] for p in analytics.keys() if p != 'pipelines'}
    pipelines = sorted(analytics['workflows'], key=itemgetter('path'))
    for pl in pipelines:
        pl['full_path'] = Path(STORAGE_DIR) / pl['path']
    return render_template(
        'analytics.html', properties=properties, pipelines=pipelines)


class InspectorData:

    def __init__(self, page_name: str):
        templates_dir = Path(inspector.__file__).parent / 'templates'
        self.template = Template((Path(templates_dir) / page_name).read_text())
        self.css_file = Path(inspector.__file__).parent / 'main.css'
        self.js_file = Path(inspector.__file__).parent / 'main.js'
        mmif_file = Path(request.args.get("path"))
        self.summ_file = Path(STORAGE_DIR) / mmif_file.parent / f'{mmif_file.stem}.summ.json'

    @property
    def summary(self):
        # TODO: assumes the summary exists, may need a test here or in the template
        return json.loads(self.summ_file.read_text())

    
def update_rendered(html: str, css_file: Path, js_file: Path = None):
    """Method to add the stylesheet and javascript that the inspector files need."""
    # TODO: make adding the javascript file optional for some pages
    # TODO: this way of adding path GET variable to subpages is fragile
    path = request.args.get("path")
    buffer = io.StringIO()
    for line in html.split('\n'):
        if line == '</head>':
            buffer.write(f'<style>\n{css_file.read_text().strip()}\n</style>\n')
            if js_file is not None:
                buffer.write(f'<script>\n{js_file.read_text().strip()}\n</script>\n')
        elif '[ <a href="views.html">Views</a>' in line:
            buffer.write(f'[ <a href="views.html?path={path}">Views</a>\n')
        elif line == '| <a href="timeframes.html">TimeFrames</a>':
            buffer.write(f'| <a href="timeframes.html?path={path}"">TimeFrames</a>\n')
        elif line == '| <a href="transcript.html">Transcript</a>':
            buffer.write('| <a href="transcript.html?path={path}"">Transcript</a>\n')
        elif line == '| <a href="captions.html">Captions</a>':
            buffer.write(f'| <a href="captions.html?path={path}"">Captions</a>\n')
        else:
            buffer.write(f'{line}\n')
    return buffer.getvalue()


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

