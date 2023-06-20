from flask import Flask, render_template, request, redirect, url_for
import sqlite3
import argparse
from pathlib import Path

DATABASE = 'database.db'

app = Flask(__name__)

def initialize():
    """initializes the database"""
    connection = sqlite3.connect(DATABASE)
    with open('schema.sql') as f:
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
        if file.stem.startswith(guid):
            paths.append(file)
    return paths

def file_typer(path):
    """determines the file type based on its extension"""
    file_types = {'.vtt': 'text', '.txt': 'text', '.mp3': 'audio', '.mp4': 'video', '.mov': 'video', '.xml': 'markup'}
    if str(path.suffix) in file_types:
        return file_types[str(path.suffix)]
    else:
        return 'other'
    
def database_search(connection, guid, types):
    """searches the database for files"""
    if len(types) == 1:
        paths = connection.execute("""SELECT file_type, server_path FROM map WHERE GUID=? and file_type=?;""", (guid, types[0])).fetchall()
    elif len(types) == 2:
        paths = connection.execute("""SELECT file_type, server_path FROM map WHERE GUID=? and file_type in (?, ?);""", (guid, types[0], types[1])).fetchall()
    elif len(types) == 3:
        paths = connection.execute("""SELECT file_type, server_path FROM map WHERE GUID=? and file_type in (?, ?, ?);""", (guid, types[0], types[1], types[2])).fetchall()
    else:
        paths = connection.execute("""SELECT file_type, server_path FROM map WHERE GUID=?;""", (guid,)).fetchall()
    connection.commit()
    return paths

def insert_into_db(connection, guid, result):
    """inserts new entry into the database"""
    type = file_typer(result)
    connection.execute("""INSERT INTO map VALUES (?, ?, ?);""", (guid, type, str(result)))
    connection.commit()

@app.route('/')
def main():
    return render_template('home.html')

@app.route('/mapper', methods=['GET','POST'])
def mapper():
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
        return redirect(url_for('main'))
    
if __name__ == '__main__':
    initialize()
    parser = argparse.ArgumentParser()
    parser.add_argument('search_directory', nargs='?', help="the root directory that contains the files to search in")
    parser.add_argument('result_directory', nargs='?', help="the subdirectory you'd like to store new files in", default="newfiles")
    args = parser.parse_args()
    SEARCH_DIRECTORY = args.search_directory
    RESULT_DIRECTORY = args.result_directory
    app.run()
    