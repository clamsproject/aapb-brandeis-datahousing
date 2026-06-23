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

    'help': ('help', 'Print available commands or help for a command'),

    'apps': (
        'apps\n apps (APP_INDEX | APP_NAME)',
        'List available CLAMS apps or select an app by index or name.'),

    'register': (
        'register URL',
        'Register an application with the Shack, the URL should include the scheme.'),

    'run': (
        'run NAME',
        'Run a job under a unique name, assumes you selected an app.'),

    'jobs': ('jobs\n jobs NAME', 'Print list of jobs or information from one job.'),

    'params': (
        'params\n params reset\n params PARAM VALUE',
        'Print all parameters, reset all parameters or add/change a parameter.'),

    'show': ('show', 'Show current settings.'),

    'tree': (
        'tree [-p] [-f]',
        '\n    Print the MMIF file tree from the current path. Include MMIF files '
        + '\n    if the -f option is added and print the parameters (if relevant) if'
        + '\n    the -p option is added.'),

    'pwd': ('pwd', 'Print the current path in the MMIF storage.'),

    'dir': ('dir', 'Print the directories at the current path.'),

    'files': ('files', 'Print the files at the current path.'),

    'cd': (
        "cd '~' | '..' | PATH | INDEX",
        'Change the current path in the MMIF storage, either by spelling out the'
        ' path or by giving an index from the dir command.'),

    'up': ('up', 'go up one directory in the MMIF storage.'),

    'home': ('home', 'go to the root directory in the MMIF storage.'),

    'quit': ('quit', 'Exit the ClamShack.'),

    'search': (
        'search guid TERM\n search app TERM',
        'Search for assets and mmif files matchng a GUID or an app name.'),
}


class Job:

    def __init__(self, path):
        self.name = path.name
        self.path = path
        self.app = None
        self.command = None
        self.started = None
        self.finished = None
        self.guids = []
        lines = path.read_text().split('\n')
        if lines:
            self.started = datetime.fromisoformat(lines[0].split('\t')[1])
        if len(lines) < 3:
            # This used to happen when you call "run <job_name" without specifying 
            # an app, resulting in a partial job file.
            return
        command = lines[1].split('\t')[1].split()
        self.command = command
        self.app = command[command.index('--app-name') + 1]
        self.pid = lines[2].split('\t')[1]
        n = 2
        # not including 'python', 'run_batch.py' and the name of the job
        pairs = [self.command[3:][i : i + n] for i in range(0, len(command), n)]
        # the parameters at the end do funky stuff so only taking the pairs
        pairs = [p for p in pairs if len(p) == 2]
        for pair in pairs:
            param, value = pair
            if param == '--app':
                self.app = value
        for line in lines[3:]:
            if line:
                fields = line.strip().split()
                if fields[0] == 'GUID':
                    self.guids.append(fields[1:4])
                elif fields[0] == 'DONE':
                    self.finished = datetime.fromisoformat(fields[1])

    def __str__(self):
        return f'<Job {self.name} app={self.app}>'

    def time_elapsed(self) -> str:
        if self.finished is None:
            return 'in-progress'
        return str(int((self.finished - self.started).total_seconds())) + ' seconds'

    def info(self) -> Table:
        table = Table('property', 'value', box=box.ROUNDED)
        table.add_row('app', self.app)
        table.add_row('command', ' '.join(self.command))
        table.add_row('pid', self.pid)
        table.add_row('guids', str(len(self.guids)))
        table.add_row('started', str(self.started))
        table.add_row('time elapsed', self.time_elapsed())
        return table

    def info_guids(self) -> Table:
        table = Table('guid', 'time', 'result', box=box.ROUNDED)
        for guid, t, result in self.guids:
            table.add_row(guid, t, result)
        return table


def walk_directory(directory: pathlib.Path, tree: Tree, full) -> None:
    """Recursively build a Tree with directory contents."""
    # Sort dirs first then by filename
    # Adapted from https://github.com/Textualize/rich/blob/main/examples/tree.py
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


def get_tree(directory, full=False):
    # Adapted from https://github.com/Textualize/rich/blob/main/examples/tree.py
    tree = Tree(
        f":open_file_folder: [link file://{directory}]{directory}",
        guide_style="bold bright_blue")
    walk_directory(pathlib.Path(directory), tree, full)
    return tree


def log(fun):
    def wrapper(*args, **kwargs):
        print(fun.__name__, str(shack))
        return fun(*args, **kwargs)
    return wrapper


def info(text: str):
    message('INFO', 'bold dark_green', text)


def warning(text: str):
    message('WARNING', 'bold dark_orange', text)


def error(text: str):
    message('ERROR', 'bold dark_red', text)


def message(message_type: str, color: str, text:str):
    console.print(Panel(Text(message_type, color)))
    console.print(f' {text}\n')


def dribble(text: str):
    console.print(text)


def bold(text: str) -> str:
    return f'\033[1m{text}\033[0m'


def timestamp() -> str:
    now = datetime.now()
    return now.strftime('%Y-%m-%dT%H:%M:%S')
