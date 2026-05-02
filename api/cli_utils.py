import datetime
from rich import box, console, prompt
from rich.panel import Panel
from rich.text import Text


console = console.Console()


messages = { 'bye': 'Bye bye sailor'}


COMMANDS = {

    'apps': (
        'apps\n apps (APP_INDEX | APP_NAME)',
        'List available CLAMS apps or select an app by index or name.'),

    'run': (
        'run NAME',
        'Run a job under a unique name, assumes you selected an app.'),

    'params': (
        'params\n params reset\n params PARAM VALUE',
        'Print all parameters, reset all parameters or add/change a parameter'),

    'init': ('init DIRECTORY', 'Initialize a CLAM Shack in DIRECTORY.'),

    'populate': (
        'populate FILENAME',
        'Add paths from the file as assets to the Shack.'),

    'use': ('use DIRECTORY', 'Use the CLAM Shack in DIRECTORY.'),

    'show': ('show', 'Show current settings.'),

    'quit': ('quit', 'Exit the ClamShack.'),

    'search': ('search TERM', 'Search assets that match TERM.'),
}


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
    now = datetime.datetime.now()
    return now.strftime('%Y-%m-%dT%H:%M:%S')
