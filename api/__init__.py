import os
import sqlite3
from datetime import date
from pathlib import Path
from string import Template

from flask import Flask, render_template, request, Blueprint, jsonify


DATABASE = Path(__file__).parent / 'database.db'
SEARCH_DIRECTORY = os.environ.get('ASSET_DIR')
RESULT_DIRECTORY = os.environ.get('DOWNLOAD_DIR')
BUILD_DB = bool(int(os.environ.get('BUILD_DB')))
STORAGE_DIRECTORY = os.environ.get('STORAGE_DIR')


bp = Blueprint('app', __name__, template_folder='templates')


def shorten_guid(guid):
    if guid.startswith('cpb'):
        return '-'.join(guid[10:].split('.', 1)[0].split('-')[:2])
    return guid


def check_symlink(fpath):
    """checks if a file is a symlink"""
    if not fpath.exists() or not fpath.is_file():
        return False
    if fpath.is_symlink():
        return True
    if any(p.is_symlink() for p in fpath.parents):
        return True
    return False


def batch_insert(connection, batch):
    """inserts a batch of files into the database"""
    q = f"INSERT INTO map VALUES {batch};"
    connection.execute(q)
    connection.commit()


def initialize_database(build_database: bool):
    connection = sqlite3.connect(DATABASE)
    if build_database:
        with open(Path(__file__).parent / 'schema_scratch.sql') as f:
            connection.executescript(f.read())
        files = []
        file_template = Template("""('${guid}', '${type}', '${path}', '${created}', '${accessed}')""")
        c = 0
        sdir = Path(SEARCH_DIRECTORY)
        # make sure the directory exists
        sdir.iterdir()
        import time
        time.sleep(1)
        for f in sdir.glob("**/*"):
            if check_symlink(f):
                continue
            if f.name.startswith('cpb') and '/.' not in str(f):
                file = file_template.substitute(guid=shorten_guid(f.stem), type=file_typer(f), path=str(f), created=date.today(), accessed=date.today())
                files.append(file)
                if c % 1000 == 0:
                    batch_insert(connection, ", ".join(files))
                    files= []
                    print(c, f)
                c += 1
        if len(files) > 0:
            batch_insert(connection, ", ".join(files))
    else:
        with open(Path(__file__).parent / 'schema.sql') as f:
            connection.executescript(f.read())


def get_db_connection():
    """gets connection to the database in order to work with it"""
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    return connection


def directory_search(guid):
    """returns the locations of all files in the SEARCH_DIRECTORY that begin with the given guid"""
    paths = []
    for file in Path(SEARCH_DIRECTORY).glob("**/*"):
        if check_symlink(file):
            continue
        if guid in file.stem:
            paths.append(file)
    return paths


def file_typer(path):
    """determines the file type based on its extension"""
    file_types = {'.vtt': 'text', '.txt': 'text', '.mp3': 'audio', '.mp4': 'video', '.mov': 'video', '.xml': 'markup'}
    if path.suffix in file_types:
        return file_types[path.suffix]
    else:
        return 'other'


def database_search(connection, guid, types):
    """searches the database for files"""
    guid = shorten_guid(guid)
    if len(types) == 1:
        paths = connection.execute("""SELECT file_type, server_path FROM map WHERE GUID=? and file_type=? GROUP BY file_type, server_path;""", (guid, types[0])).fetchall()
        connection.execute("""UPDATE map SET date_last_accessed=? WHERE GUID=? and file_type=?;""", (date.today(), guid, types[0]))
    elif len(types) == 2:
        paths = connection.execute("""SELECT file_type, server_path FROM map WHERE GUID=? and file_type in (?, ?) GROUP BY file_type, server_path;""", (guid, types[0], types[1])).fetchall()
        connection.execute("""UPDATE map SET date_last_accessed=? WHERE GUID=? and file_type in (?, ?);""", (date.today(), guid, types[0], types[1]))
    elif len(types) == 3:
        paths = connection.execute("""SELECT file_type, server_path FROM map WHERE GUID=? and file_type in (?, ?, ?) GROUP BY file_type, server_path;""", (guid, types[0], types[1], types[2])).fetchall()
        connection.execute("""UPDATE map SET date_last_accessed=? WHERE GUID=? and file_type in (?, ?, ?);""", (date.today(), guid, types[0], types[1], types[2]))
    else:
        paths = connection.execute("""SELECT file_type, server_path FROM map WHERE GUID=? GROUP BY file_type, server_path;""", (guid,)).fetchall()
        connection.execute("""UPDATE map SET date_last_accessed=? WHERE GUID=?;""", (date.today(), guid))
    connection.commit()
    return paths


def insert_into_db(connection, guid, result):
    """inserts new entry into the database"""
    guid = shorten_guid(guid)
    type = file_typer(result)
    connection.execute("""INSERT INTO map VALUES (?, ?, ?, ?, ?);""", (guid, type, str(result), date.today(), date.today()))
    connection.commit()


def aapb_generate(guid, extension):
    """generates a file from AAPB given a guid and file type"""
    # TODO: needs to be updated with AAPB API
    root = Path(SEARCH_DIRECTORY)
    dir = root.joinpath(RESULT_DIRECTORY)
    if not dir.is_dir():
        dir.mkdir()
    filename = dir.joinpath(guid + extension)
    filename.touch()
    return filename


@bp.route('/')
def main():
    return render_template('home.html')


@bp.route('/search', methods=['GET', 'POST'])
def search():
    if request.method == 'POST':
        files = request.form.getlist('file_type')
        guid = request.form['GUID']
        connection = get_db_connection()
        paths = database_search(connection, guid, files)
        if len(paths) == 0:
            results = directory_search(guid)
            if len(results) == 0:
                connection.close()
                return render_template('filenotfound.html', GUID=guid)
            else:
                for result in results:
                    insert_into_db(connection, guid, result)
                paths = database_search(connection, guid, files)
                connection.commit()
        connection.close()
        return render_template('search_results.html', GUID=guid, paths=paths)
    else:
        return render_template('search.html')


@bp.route('/searchapi', methods=['GET'])
def search_api():
    if 'file' in request.args:
        file = [request.args['file']]
    else:
        file = []
    guid = request.args['guid']
    only_first = request.args.get('onlyfirst', False)
    connection = get_db_connection()
    paths = database_search(connection, guid, file)
    if len(paths) == 0:
        results = directory_search(guid)
        if len(results) > 0:
            for result in results:
                insert_into_db(connection, guid, result)
            paths = database_search(connection, guid, file)
            connection.commit()
    connection.close()
    if len(paths) > 0:
        if only_first:
            return paths[0]['server_path']
        else:
            return [path['server_path'] for path in paths]
    else:
        return 'The requested file does not exist in our server'


@bp.route('/generate', methods=['GET', 'POST'])
def add():
    if request.method == 'POST':
        extension = request.form['file_extension']
        guid = request.form['GUID']
        file = aapb_generate(guid, extension)
        connection = get_db_connection()
        insert_into_db(connection, guid, file)
        return render_template('generate_results.html', GUID=guid, path=file)
    else:
        return render_template('generate.html')


def create_app(build_db=BUILD_DB):

    initialize_database(build_db)

    app = Flask(__name__)
    app.config.from_prefixed_env()
    app.register_blueprint(bp)

    from api.mmif_storage import bp as mmif_bp
    # instead of using `url_prefix`, we use dedicated `API_PREFIX` vars in blueprints
    # this will eliminate unnecessary redirection step (and forced use of `-L` flag in curl command)
    app.register_blueprint(mmif_bp)

    return app
