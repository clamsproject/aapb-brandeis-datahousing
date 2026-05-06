from datetime import datetime
from rich import box, console, prompt
from rich.panel import Panel
from rich.text import Text


console = console.Console()


messages = { 'bye': 'Bye bye sailor'}


COMMANDS = {

    'help': ('help', 'Print available commands or help for a command'),

    'apps': (
        'apps\n apps (APP_INDEX | APP_NAME)',
        'List available CLAMS apps or select an app by index or name.'),

    'run': (
        'run NAME',
        'Run a job under a unique name, assumes you selected an app.'),

    'jobs': ('jobs', 'Print list of jobs associated with the Shack'),

    'params': (
        'params\n params reset\n params PARAM VALUE',
        'Print all parameters, reset all parameters or add/change a parameter'),

    'init': ('init DIRECTORY', 'Initialize a CLAM Shack in DIRECTORY.'),

    'populate': (
        'populate FILENAME',
        'Add paths from the file as assets to the Shack.'),

    'use': ('use DIRECTORY', 'Use the CLAM Shack in DIRECTORY.'),

    'show': ('show', 'Show current settings.'),

    'pwd': ('pwd', 'Print the current path in the MMIF storage'),

    'dir': ('dir', 'Print the directories at the current path'),

    'files': ('files', 'Print the files at the current path'),

    'cd': (
        'cd PATH | INDEX',
        'Change the current path in the MMIF storage, either by spelling out the'
        ' path or by giving an index from the dir command'),

    'quit': ('quit', 'Exit the ClamShack.'),

    'search': ('search TERM', 'Search assets that match TERM.'),
}


class Job:

    def __init__(self, path):
        self.name = path.name
        self.path = path
        self.app = None
        self.batch = None
        lines = path.read_text().split('\n')
        self.started = datetime.fromisoformat(lines[0].split('\t')[1])
        self.finished = None
        command = lines[1].split('\t')[1].split()
        # not including 'python', 'run_batch.py' and the name of the job
        self.command = command[3:]
        self.pid = lines[2].split('\t')[1]
        n = 2
        pairs = [self.command[i : i + n] for i in range(0, len(command), n)]
        # the parameters at the end do funky stuff so only taking the pairs
        pairs = [p for p in pairs if len(p) == 2]
        for pair in pairs:
            param, value = pair
            if param == '--app':
                self.app = value
            if param == '--batch':
                self.batch = value
        self.guids = []
        for line in lines[3:]:
            if line:
                fields = line.strip().split()
                if fields[0] == 'GUID':
                    self.guids.append(fields[1:4])
                elif fields[0] == 'DONE':
                    self.finished = datetime.fromisoformat(fields[1])

    def __str__(self):
        return f'<Job {self.started} {self.finished} {self.name} app={self.app} batch={self.batch}'


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
