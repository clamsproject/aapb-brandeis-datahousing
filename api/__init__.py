import os
import sqlite3
import time
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, request, Blueprint

load_dotenv()

DATABASE = Path(__file__).parent / 'database.db'
SEARCH_DIRECTORY = os.environ.get('ASSET_DIR')
RESULT_DIRECTORY = os.environ.get('DOWNLOAD_DIR')
BUILD_DB = bool(int(os.environ.get('BUILD_DB')))
STORAGE_DIRECTORY = os.environ.get('STORAGE_DIR')

# Asset file types
file_types = [
    ('text', ['.vtt', '.txt', '.srt', '.json']),
    ('markup', ['.xml']),
    ('image', ['.png', '.jpeg', '.jpg']),
    ('audio', ['.mp3', '.wav']),
    ('video', ['.mp4', '.mov', 'webm', 'mkv'])]

file_types_idx = {}
for file_type, extensions in file_types:
    for extension in extensions:
        file_types_idx[extension] = file_type

bp = Blueprint('app', __name__, template_folder='templates')


def print_settings():
    """Debugging method."""
    print(f'>>   DATABASE           =  {DATABASE}')
    print(f'>>   SEARCH_DIRECTORY   =  {SEARCH_DIRECTORY}')
    print(f'>>   RESULT_DIRECTORY   =  {RESULT_DIRECTORY}')
    print(f'>>   BUILD_DB           =  {BUILD_DB}')


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
    connection.executemany("""INSERT INTO map VALUES (?, ?, ?, ?, ?);""", batch)
    connection.commit()


def check_asset_dir():
    """
    Validates ASSET_DIR and warns if it's a symlink or contains symlinks.
    Returns the resolved real path if ASSET_DIR is a symlink, otherwise returns the original path.
    """
    if not SEARCH_DIRECTORY:
        raise RuntimeError("ASSET_DIR is not set in environment variables")
    
    sdir = Path(SEARCH_DIRECTORY)
    if not sdir.exists():
        raise RuntimeError(f"ASSET_DIR does not exist: {SEARCH_DIRECTORY}")
    
    if not sdir.is_dir():
        raise RuntimeError(f"ASSET_DIR is not a directory: {SEARCH_DIRECTORY}")
    
    # Check if ASSET_DIR itself is a symlink
    if sdir.is_symlink():
        real_path = sdir.resolve()
        print(f"WARNING: ASSET_DIR is a symlink: {SEARCH_DIRECTORY}")
        print(f"WARNING: Resolved to real path: {real_path}")
        print(f"WARNING: For proper functionality, consider using the real path in ASSET_DIR")
        return real_path
    
    # Check if any parent directory is a symlink
    for parent in sdir.parents:
        if parent.is_symlink():
            real_path = sdir.resolve()
            print(f"WARNING: ASSET_DIR contains a symlinked parent directory: {parent}")
            print(f"WARNING: Resolved ASSET_DIR to real path: {real_path}")
            print(f"WARNING: For proper functionality, consider using the real path in ASSET_DIR")
            return real_path
    
    return sdir


def initialize_database(populate: bool = False):
    """
    Creates the database from the schema. If populate is True then an existing
    table in the database will be dropped, recreated and populated from paths in
    the assets directory. Otherwise the code just makes sure that the table exists.
    """
    connection = sqlite3.connect(DATABASE)
    if populate:
        with open(Path(__file__).parent / 'schema_scratch.sql') as f:
            connection.executescript(f.read())
        files = []
        c = 1
        sdir = check_asset_dir()
        # make sure the directory exists
        sdir.iterdir()
        time.sleep(1)
        for f in sdir.glob("**/*"):
            if check_symlink(f):
                continue
            if f.name.startswith('cpb') and '/.' not in str(f):
                file = (f'{shorten_guid(f.stem)}', f'{file_typer(f)}', f'{str(f)}', f'{date.today()}', f'{date.today()}')
                files.append(file)
                if c % 1000 == 0:
                    batch_insert(connection, files)
                    files = []
                    print(c, f)
                c += 1
        if len(files) > 0:
            batch_insert(connection, files)
    else:
        with open(Path(__file__).parent / 'schema.sql') as f:
            connection.executescript(f.read())


def get_db_connection():
    """gets connection to the database in order to work with it"""
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    return connection


def directory_search(guid):
    """returns the locations of all files in the SEARCH_DIRECTORY that begin with the
    given guid"""
    paths = []
    for file in Path(SEARCH_DIRECTORY).glob("**/*"):
        if check_symlink(file):
            continue
        if guid in file.stem:
            paths.append(file)
    return paths


def file_typer(path):
    """determines the file type based on its extension"""
    return file_types_idx.get(path.suffix, 'other')


def database_search(connection, guid, types):
    """searches the database for files"""
    guid = shorten_guid(guid)
    if len(types) == 1:
        paths = connection.execute("""SELECT file_type, server_path FROM map WHERE (GUID MATCH ?) AND (file_type MATCH ?) GROUP BY file_type, server_path;""", (f'"{guid}"', types[0])).fetchall()
        connection.execute("""UPDATE map SET date_last_accessed=? WHERE (GUID MATCH ?) AND (file_type MATCH ?);""", (date.today(), f'"{guid}"', types[0]))
    elif len(types) == 2:
        paths = connection.execute("""SELECT file_type, server_path FROM map WHERE (GUID MATCH ?) AND (file_type IN (?, ?)) GROUP BY file_type, server_path;""", (f'"{guid}"', types[0], types[1])).fetchall()
        connection.execute("""UPDATE map SET date_last_accessed=? WHERE (GUID MATCH ?) AND (file_type IN (?, ?));""", (date.today(), f'"{guid}"', types[0], types[1]))
    elif len(types) == 3:
        paths = connection.execute("""SELECT file_type, server_path FROM map WHERE (GUID MATCH ?) AND (file_type IN (?, ?, ?)) GROUP BY file_type, server_path;""", (f'"{guid}"', types[0], types[1], types[2])).fetchall()
        connection.execute("""UPDATE map SET date_last_accessed=? WHERE (GUID MATCH ?) AND (file_type IN (?, ?, ?));""", (date.today(), f'"{guid}"', types[0], types[1], types[2]))
    else:
        paths = connection.execute("""SELECT file_type, server_path FROM map WHERE GUID MATCH ? GROUP BY file_type, server_path;""", (f'"{guid}"',)).fetchall()
        connection.execute("""UPDATE map SET date_last_accessed=? WHERE GUID MATCH ?;""", (date.today(), f'"{guid}"'))
    connection.commit()
    return paths


def insert_into_db(connection, guid, result):
    """inserts new entry into the database"""
    guid = shorten_guid(guid)
    type = file_typer(result)
    connection.execute(
        """INSERT INTO map VALUES (?, ?, ?, ?, ?);""",
        (guid, type, str(result), date.today(), date.today()))
    connection.commit()


def aapb_generate(guid, extension):
    """generates a file from AAPB given a guid and file type, for future use, currently NOT IN USE"""
    # TODO: needs to be updated with AAPB API
    root = Path(SEARCH_DIRECTORY)
    dir = root.joinpath(RESULT_DIRECTORY)
    if not dir.is_dir():
        dir.mkdir()
    filename = dir.joinpath(guid + extension)
    filename.touch()
    return filename


@bp.route('/searchapi', methods=['GET'])
def search_api():
    file_type = request.args.getlist('file') if 'file' in request.args else []
    guid = request.args['guid']
    only_first = request.args.get('onlyfirst', False)
    connection = get_db_connection()
    paths = database_search(connection, guid, file_type)
    # TODO (marc @ 4/15/25): this looks like you do a full directory search each
    # time you do not find results in the database, could be very inefficient
    if len(paths) == 0:
        results = directory_search(guid)
        if len(results) > 0:
            for result in results:
                insert_into_db(connection, guid, result)
            paths = database_search(connection, guid, file_type)
            connection.commit()
    connection.close()
    if len(paths) > 0:
        if only_first:
            return paths[0]['server_path']
        else:
            return [path['server_path'] for path in paths]
    else:
        return 'The requested file does not exist in our server', 404


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
