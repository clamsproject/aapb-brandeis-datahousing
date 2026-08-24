"""

Assorted utilities for the cli script, a few are also used elsewhere.

"""


import os
import pathlib

from datetime import datetime
from rich import box, console, prompt, print
from rich.panel import Panel
from rich.text import Text
from rich.table import Table
from rich.tree import Tree
from rich.filesize import decimal
from rich.markup import escape


console = console.Console()


messages = { 'bye': 'Bye bye sailor'}


COMMANDS = {

    'help': (
        'help\n help COMMAND',
        'Print list of available commands or print help for a command.'),

    'help_all': (
        'help_all',
        'Print all available commands with their help message.'),

    'history': (
        'history\n history reset',
        'Print the command history or reset it.'),

    'apps': (
        'apps\n apps (APP_INDEX | APP_NAME)',
        'List available CLAMS apps or select an app by index or name.'),

    'register': (
        'register URL',
        'Register an application with the Shack, the URL should include the scheme.'),

    'run': (
        'run NAME',
        'Run a job under a unique name, assumes you selected an app.'),

    'jobs': (
        'jobs\n jobs NAME',
        'Print list of jobs or information from one job.'),

    'source': (
        'source FILE',
        'Run the commands in the script file given'),

    'index': (
        'index',
        'Recreate the MMIF Storage index'),

    'params': (
        'params\n params reset\n params @FILE\n params PARAM=VALUE',
        'Print all parameters, reset all parameters, load parameters from a JSON file'
        ' or add/change a parameter.'),

    'show': (
        'show\n show error\n show errors',
        'Show current ClamShack settings, show the last error or show all errors.'),

    'describe': (
        'describe INT',
        'describe MMIF file at the given index'),

    'tree': (
        'tree [-p] [-f] [-v]',
        'Print the MMIF file tree from the current path. Include MMIF files'
        ' if the -f option is added and print the parameters (if relevant) if'
        ' the -p option is added, include both with the -v option.'),

    'pwd': (
        'pwd',
        'Print the current path in the MMIF storage.'),

    'dirs': (
        'dirs [-d] [-s]',
        'Print the directories at the current path. With the -d option three levels'
        ' in the directory strructure are printed. With the -s option perviously'
        ' saved directories are printed.'),

    'files': (
        'files',
        'Print the files at the current path.'),

    'cd': (
        "cd '~' | '..' | PATH | INDEX",
        'Change the current path in the MMIF storage, either by spelling out the'
        ' path or by giving an index from the dir command.'),

    'up': (
        'up\n up N',
        'Go up one directory in the MMIF storage or go up N levels.'),

    'home': (
        'home',
        'Go to the root directory in the MMIF storage.'),

    'goto': (
        'goto INT',
        'Go to a saved directory given the index.'),

    'prune': (
        'prune',
        'Prune the current directory and everything underneath. This cannot be undone.'),

    'view': (
        'view INT',
        'View a directory given the index.'),

    'quit': (
        'quit',
        'Exit the ClamShack.'),

    'search': (
        'search assets TERM'
        '\n search mmif TERM'
        '\n search app TERM'
        '\n search params (param=value)+',
        'Search for assets or mmif files matching a string, search for'
        ' directories where the pipeline includes and app name, or search'
        ' for directories with files creating where the app was given certain'
        ' parameters.'),
}


def get_tree(directory, prefix=pathlib.Path('.'), full=False) -> Tree:
    """Get a rich.Tree instance starting at the given directory. Adapted from
    https://github.com/Textualize/rich/blob/main/examples/tree.py."""
    root = pathlib.Path(*directory.parts[len(prefix.parts):])
    root = path_as_string(root)
    root = root if root else "."
    tree = Tree(
        f":open_file_folder: [link file://{directory}]{root}",
        style="bold bright_blue", guide_style="bold bright_blue")
    walk_directory(pathlib.Path(directory), tree, full)
    return tree


def walk_directory(directory: pathlib.Path, tree: Tree, full) -> None:
    """Recursively build a Tree with directory contents. Adapted from
    https://github.com/Textualize/rich/blob/main/examples/tree.py."""
    paths = sorted(
        pathlib.Path(directory).iterdir(),
        key=lambda path: (path.is_file(), path.name.lower()))
    for path in paths:
        # Remove hidden files
        if path.name.startswith("."):
            continue
        if not full and path.suffix == ".mmif":
            continue
        if path.is_dir():
            style = "dim" if path.name.startswith("__") else ""
            branch = tree.add(
                f"[bold magenta]:open_file_folder: [link file://{path}]{escape(path.name)}",
                style=style,
                guide_style=style)
            walk_directory(path, branch, full)
        else:
            text_filename = Text(path.name, "green")
            text_filename.highlight_regex(r"\..*$", "bold red")
            text_filename.stylize(f"link file://{path}")
            file_size = path.stat().st_size
            text_filename.append(f" ({decimal(file_size)})", "blue")
            icon = "🐍 " if path.suffix == ".py" else "📄 "
            tree.add(Text(icon) + text_filename)


def log(fun):
    def wrapper(*args, **kwargs):
        print(fun.__name__, str(shack))
        return fun(*args, **kwargs)
    return wrapper


def info(text: str):
    message('INFO', 'bold dark_green', text)


def warning(text: str):
    message('WARNING', 'bold', text)
    #message('WARNING', 'bold dark_orange', text)


def error(text: str):
    message('ERROR', 'bold dark_red', text)


def message(message_type: str, style: str, text:str):
    console.print(Panel(Text(message_type, style)))
    console.print(f' {text}')


def dribble(text: str):
    console.print(text)


def bold(text: str) -> str:
    return f'\033[1m{text}\033[0m'


def timestamp() -> str:
    now = datetime.now()
    return now.strftime('%Y-%m-%dT%H:%M:%S')


def path_as_string(p: pathlib.Path) -> str:
    """Return a string for the directory path in the MMIF storage. It abbreviates
    the hash value of the parameters for clarity."""
    path_string = ''
    for triple in path_as_tuples(p):
        if len(triple) == 3:
            app, version, hash_value = triple
            if hash_value.endswith('.json'):
                path_string += f'{app}/{version}/{hash_value[:8]}.json'
            else:
                path_string += f'{app}/{version}/{hash_value[:8]}/'
        else:
            path_string += '/'.join([p for p in triple])
    return path_string if path_string else '~'


def path_as_tuples(p: pathlib.Path) -> list[tuple]:
    """Return the path a a list of tuples <appname, appversion, paramhash>. The
    last element in the list is not necessarily a tuple of lenth 3, it could also
    be <appname, appversion> or <appname>."""
    parts = p.parts
    return [parts[i:i + 3] for i in range(0, len(parts), 3)]





