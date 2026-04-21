"""

Module to build and access the assets database.

"""

# TODO: must test whether the database can be initialized
# TODO: must revisit how entires are added to the databse since updates from
#       api.model.assets did not seem to take hold.
# TODO: must put in guard rails to update the index anytime an asset is added

import time
import sqlite3
from datetime import date
from pathlib import Path

from api import DATABASE
from api.model.assets import file_typer, check_asset_dir, check_symlink


def get_db_connection() -> sqlite3.Connection:
    """Returns the database connection"""
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    return connection


def batch_insert(connection, batch):
    """inserts a batch of files into the database"""
    connection.executemany("INSERT INTO map VALUES (?, ?, ?, ?, ?);", batch)
    connection.commit()


def initialize_database(populate: bool = False):
    """
    Creates the database from the schema. If populate is True then an existing
    table in the database will be dropped, recreated and populated from paths in
    the assets directory. Otherwise the code just makes sure the schema exist.
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


def database_search(guid, types):
    """searches the database for files"""
    connection = get_db_connection()
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
    connection.close()
    return [p['server_path'] for p in paths]


def insert_into_db(connection, guid, result):
    """inserts new entry into the database"""
    guid = shorten_guid(guid)
    type = file_typer(result)
    connection.execute(
        "INSERT INTO map VALUES (?, ?, ?, ?, ?);",
        (guid, type, str(result), date.today(), date.today()))
    connection.commit()


def shorten_guid(guid):
    """Removes the leading 10 characters of the guid, those characters are
    always 'cpb-aacip-'."""
    # TODO: his should probably be in another module but at the moment only this
    #       module uses it
    # TODO: this is AAPB specific, should be revisited
    # TODO: is the official guid without those 10 characters?
    # TODO: why don't we just leave it on
    if guid.startswith('cpb'):
        return '-'.join(guid[10:].split('.', 1)[0].split('-')[:2])
    return guid
