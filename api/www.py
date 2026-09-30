import os
from pathlib import Path
from dotenv import load_dotenv

from flask import Flask, request, Blueprint, render_template

from api.model.assets import search_assets
from api.utils import strip_prefix


load_dotenv()


bp = Blueprint('www', __name__, template_folder='templates')


DEBUG = True


ASSET_DIR = os.environ.get('ASSET_DIR')


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
