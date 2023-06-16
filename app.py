from flask import Flask, render_template, request, redirect, url_for
import os
import sqlite3

CURRENT_DIRECTORY = os.path.dirname(os.path.abspath(__file__))
SEARCH_DIRECTORY = os.path.join('data')
DATABASE = os.path.join(CURRENT_DIRECTORY, 'database.db')

app = Flask(__name__)

def get_db_connection():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    return connection

def search_for_paths(guid):
    paths = []
    for root, dirs, files in os.walk(SEARCH_DIRECTORY):
        for name in files:
            if name.startswith(guid):
                paths.append(os.path.join(root, name))
    return paths

def file_typer(path):
    if path.endswith('.vtt') or path.endswith('.txt'):
        return 'text'
    elif path.endswith('.mp3'):
        return 'audio'
    elif path.endswith('.mp4') or path.endswith('.mov'):
        return 'video'
    else:
        return 'markup'

@app.route('/')
def main():
    return render_template('home.html')

@app.route('/mapper', methods=['GET','POST'])
def mapper():
    if request.method == 'POST':
        found = True
        files = request.form.getlist('file_type')
        guid = request.form['GUID']
        connection = get_db_connection()
        if len(files) == 1:
            paths = connection.execute("""SELECT file_type, server_path FROM map WHERE GUID=? and file_type=?;""", (guid, files[0])).fetchall()
        elif len(files) == 2:
            paths = connection.execute("""SELECT file_type, server_path FROM map WHERE GUID=? and file_type in (?, ?);""", (guid, files[0], files[1])).fetchall()
        elif len(files) == 3:
            paths = connection.execute("""SELECT file_type, server_path FROM map WHERE GUID=? and file_type in (?, ?, ?);""", (guid, files[0], files[1], files[2])).fetchall()
        else:
            paths = connection.execute("""SELECT file_type, server_path FROM map WHERE GUID=?;""", (guid,)).fetchall()
        connection.commit()
        if len(paths) == 0:
            results = search_for_paths(guid)
            for result in results:
                type = file_typer(result)
                connection.execute("""INSERT INTO map VALUES (?, ?, ?);""", (guid, type, result))
                connection.commit()
            if len(results) == 0:
                found=False
            else:
                if len(files) == 1:
                    paths = connection.execute("""SELECT file_type, server_path FROM map WHERE GUID=? and file_type=?;""", (guid, files[0])).fetchall()
                elif len(files) == 2:
                    paths = connection.execute("""SELECT file_type, server_path FROM map WHERE GUID=? and file_type in (?, ?);""", (guid, files[0], files[1])).fetchall()
                elif len(files) == 3:
                    paths = connection.execute("""SELECT file_type, server_path FROM map WHERE GUID=? and file_type in (?, ?, ?);""", (guid, files[0], files[1], files[2])).fetchall()
                else:
                    paths = connection.execute("""SELECT file_type, server_path FROM map WHERE GUID=?;""", (guid,)).fetchall()
                connection.commit()
        connection.close()
        if found:
            return render_template('mapper.html', GUID=guid, paths=paths)
        else:
            return render_template('filenotfound.html', GUID=guid)
    else:
        return redirect(url_for('main'))
    
if __name__ == '__main__':
    app.run()
    