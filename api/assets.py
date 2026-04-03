"""

This module is the interface to the source assets.

"""

import sqlite3
import time
from datetime import date
from pathlib import Path

from flask import request, Blueprint

from api import DATABASE, ASSET_DIR


bp = Blueprint('assets', __name__)
print(f'{bp} import_name={bp.import_name} __name__={__name__}')


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


@bp.get('/api/assets/search')
@bp.get('/searchapi')
def search_api():
    file_type = request.args.getlist('file') if 'file' in request.args else []
    guid = request.args['guid']
    only_first = request.args.get('onlyfirst', False)
    paths = search_assets(guid, file_type)
    if len(paths) > 0:
        return paths[0] if only_first else paths
    else:
        return 'The requested file does not exist in our server', 404



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
    if not ASSET_DIR:
        raise RuntimeError("ASSET_DIR is not set in environment variables")
    
    sdir = Path(ASSET_DIR)
    if not sdir.exists():
        raise RuntimeError(f"ASSET_DIR does not exist: {ASSET_DIR}")
    
    if not sdir.is_dir():
        raise RuntimeError(f"ASSET_DIR is not a directory: {ASSET_DIR}")
    
    # Check if ASSET_DIR itself is a symlink
    if sdir.is_symlink():
        real_path = sdir.resolve()
        print(f"WARNING: ASSET_DIR is a symlink: {ASSET_DIR}")
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
                    print(f'{c} paths loaded'   )
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
    """returns the locations of all files in the ASSET_DIR that begin with the
    given guid"""
    paths = []
    for file in Path(ASSET_DIR).glob("**/*"):
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
    if types:
        type_clause = f'file_type IN ({",".join(["?"] * len(types))})'
        query = f"SELECT file_type, server_path FROM map WHERE (GUID MATCH ?) AND {type_clause};"
        paths = connection.execute(query, (f'"{guid}"',) + tuple(types)).fetchall()
    else:
        query = "SELECT file_type, server_path FROM map WHERE GUID MATCH ?;"
        paths = connection.execute(query, (f'"{guid}"',)).fetchall()
        connection.execute(
            """UPDATE map SET date_last_accessed=? WHERE GUID MATCH ?;""",
            (date.today(), f'"{guid}"'))
    connection.commit()
    return [p['server_path'] for p in paths]


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
    root = Path(ASSET_DIR)
    dir = root.joinpath(DOWNLOAD_DIR)
    if not dir.is_dir():
        dir.mkdir()
    filename = dir.joinpath(guid + extension)
    filename.touch()
    return filename


def search_assets(guid, file_type=None):
    if file_type is None:
        file_type = []
    connection = get_db_connection()
    paths = database_search(connection, guid, file_type)
    # TODO (marc @ 12/12/25): doing a full directory search each time you do not find
    # results in the database, this is not horribly time consuming at the moment (on my
    # desktop it takes about two seconds when you have 16K files), but this needs to be
    # revisited when the number of assets gets much higher.
    if len(paths) == 0:
        # making sure the paths are strings, to match the paths from the database search
        paths = [str(p) for p in directory_search(guid)]
        # NOTE: disabling this for now because in some cases the update still results
        # in a fulll directory scan
        #if len(results) > 0:
        #    for result in results:
        #        insert_into_db(connection, guid, result)
        #    paths = database_search(connection, guid, file_type)
    connection.close()
    return paths

