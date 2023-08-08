import argparse
import sqlite3
from collections import defaultdict
from datetime import date
from pathlib import Path

from flask import Flask, render_template, request

DATABASE = 'database.db'

app = Flask(__name__)


def shorten_guid(guid):
    if guid.startswith('cpb'):
        return '-'.join(guid[10:].split('.', 1)[0].split('-')[:2])
    return guid


def initialize(start):
    """initializes the database"""
    connection = sqlite3.connect(DATABASE)
    if start:
        with open('schema_scratch.sql') as f:
            connection.executescript(f.read())
    else:
        with open('schema.sql') as f:
            connection.executescript(f.read())
    if start:
        d = defaultdict(lambda: defaultdict(list))
        for f in Path(SEARCH_DIRECTORY).glob("**/*"):
            if f.name.startswith('cpb'):
                d[shorten_guid(f.stem)][file_typer(f)].append(f)
        # TODO (krim @ 8/8/23): bulk insert all findings (d) into the database 
        # connection.execute`many`("""INSERT INTO map VALUES (?, ?, ?, ?, ?);""", (guid, type, str(result), date.today(), date.today()))


def get_db_connection():
    """gets connection to the database in order to work with it"""
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    return connection


def directory_search(guid):
    """returns the locations of all files in the SEARCH_DIRECTORY that begin with the given guid"""
    paths = []
    for file in Path(SEARCH_DIRECTORY).glob("**/*"):
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


@app.route('/')
def main():
    return render_template('home.html')


@app.route('/search', methods=['GET', 'POST'])
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


@app.route('/searchapi', methods=['GET'])
def search_api():
    if 'file' in request.args:
        file = [request.args['file']]
    else:
        file = []
    guid = request.args['guid']
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
        return paths[0]['server_path']
    else:
        return 'The requested file does not exist in our server'


@app.route('/generate', methods=['GET', 'POST'])
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


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-s', '--search_directory', nargs='?',
                        help="the root directory that contains the files to search in")
    parser.add_argument('-r', '--result_directory', nargs='?', help="the subdirectory you'd like to store new files in",
                        default="newfiles")
    parser.add_argument('--host', nargs='?', help="the host name", default="0.0.0.0")
    parser.add_argument('-p', '--port', nargs='?', help="the port to run the app from", default="8001")
    parser.add_argument('-n', '--new_database', help="create the database from scratch", action='store_true')
    args = parser.parse_args()
    SEARCH_DIRECTORY = args.search_directory
    RESULT_DIRECTORY = args.result_directory
    HOST = args.host
    PORT = args.port
    START_NEW = args.new_database
    initialize(START_NEW)
    app.run(host=HOST, port=PORT)
