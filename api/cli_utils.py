import os
import pathlib
import sys

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
        'dirs\n dirs saved',
        'Print the directories at the current path or print the last directories saved.'),

    'ddirs': (
        'ddirs',
        'Print the directory paths at the current path, printing three levels down the tree.'),

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


class Job:

    # TODO: 
    # - a job should know what directory it is writing too
    #   (you can use the new peek functionality for that)
    # - add a variable named status with the following possible values:
    #   running, aborted, failed, finished and maybe some more
    #   (for running to check whether there is a process id that seems to 
    #   be a clamshell job, if not you have failed, aborted is for when the
    #   user aborts the job; i fpossible update the finished value)
    # - allow deleting a job (with option to remove associated files?)

    def __init__(self, path: pathlib.Path):
        self.name = path.stem
        self.path = path
        self.content = path.read_text()
        self.lines = self.content.split('\n')
        self.app = None
        self.command = []
        self.pid = None
        self.started = None
        self.finished = None
        self.guids = []
        for line in path.read_text().split('\n'):
            if line.startswith('STARTED'):
                self.started = datetime.fromisoformat(line.split('\t')[1])
            elif line.startswith('DONE'):
                self.finished = datetime.fromisoformat(line.split('\t')[1])
            elif line.startswith('COMMAND'):
                command = line.split('\t')[1].split()
                self.command = command
                self.app = command[command.index('--app-name') + 1]
            elif line.startswith('PROCESS_ID'):
                self.pid = line.split('\t')[1]
            elif line.startswith('GUID'):
                fields = line.split('\t')
                self.guids.append(fields[1:4])

    def __str__(self):
        return f'<Job {self.name} app={self.app}>'

    def time_elapsed(self) -> int:
        """Return time elapsed in seconds. if the job is still running then we take
        the total time since the job was started"""
        if self.finished is None:
            return int(((datetime.now() - self.started).total_seconds()))
        return int((self.finished - self.started).total_seconds())

    def info(self) -> Table:
        table = Table('property', 'value', box=box.ROUNDED)
        table.add_row('app', self.app)
        table.add_row('command', ' '.join(self.command))
        table.add_row('pid', self.pid)
        table.add_row('guids', str(len(self.guids)))
        table.add_row('started', str(self.started))
        table.add_row('time elapsed', str(self.time_elapsed()))
        return table

    def info_guids(self) -> Table:
        table = Table('guid', 'time', 'result', box=box.ROUNDED)
        for guid, t, result in self.guids:
            table.add_row(guid, t, result)
        return table


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





