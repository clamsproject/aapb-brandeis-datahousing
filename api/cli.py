import sys
import time
import datetime
from cmd import Cmd
from pathlib import Path
import argparse

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich.text import Text
from rich.markdown import Markdown
from rich.syntax import Syntax

import api
import api.run


console = Console()

shack = None

messages = { 'bye': 'Bye bye sailor'}


def log(fun):
    def wrapper(*args, **kwargs):
        print(fun.__name__, str(shack))
        return fun(*args, **kwargs)
    return wrapper


def info(text: str):
    console.print(Text.assemble(("INFO     ", "bold dark_green"), text))

def warning(text: str):
    console.print(Text.assemble(("WARNING  ", "bold dark_orange"), text))

def error(text: str):
    console.print(Text.assemble(("ERROR    ", "bold dark_red"), text))


def timestamp() -> str:
    now = datetime.datetime.now()
    return now.strftime('%Y-%m-%dT%H:%M:%S')



class ClamShack:

    """
    Instances of this class keep track of all information like location, current
    batch, current path in the shack and others. It is also the entry point to
    all batch processing.

    TODO: this maybe should be defined somewhere in the api.model package.
    """

    def __init__(self, directory: str):
        self.location = Path(directory)
        self._apps = api.run.APPS
        self._assets = set()
        self._sources = {}
        self.create_directory_structure()
        self.load_assets()
        # set the storage dir to match the mmif directory of the shack
        api.STORAGE_DIR = self.loc_mmif
        self.path = '.'
        self.batch = 'default'
        # Dictionary of batches. The value is a list of identifiers or None, in
        # which case all assets are used.
        # TODO: should load additional batches from the disk
        # TODO: maybe we do not need the default in the dictionary
        self.batches = {'default': None}
        self.app = None      # selected app for a batch job
        #self.workflow = []   # selected pipeline for a batch job

    def create_directory_structure(self):
        self.loc_assets_list = self.location / 'assets' / 'list.txt'
        self.loc_assets = self.location / 'assets'
        self.loc_mmif = self.location / 'mmif'
        self.loc_batches = self.location / 'batches'
        self.loc_sources = self.location / 'sources'
        self.loc_jobs = self.location / 'jobs'
        if not self.loc_assets_list.exists():
            for p in (self.location, self.loc_assets, self.loc_mmif,
                      self.loc_sources, self.loc_jobs):
                p.mkdir(exist_ok=True)
            self.loc_assets_list.touch()

    def load_assets(self):
        """Load the asset paths into memory and do the same with the MMIF
        sources."""
        with open(self.loc_assets_list) as fh:
            for line in fh:
                path = Path(line.strip())
                if path.is_file():
                    self._assets.add(path)
        for subpath in self.loc_sources.iterdir():
            self._sources[subpath.stem] = subpath

    @property
    def assets(self) -> list[Path]:
        return list(sorted(self._assets))

    @property
    def sources(self) -> list[str]:
        return list(sorted(self._sources.values()))

    @property
    def apps(self):
        return self._apps
    
    @property
    def app_names(self) -> list:
        return list(sorted(self._apps.keys()))

    def __str__(self):
        return f'<ClamShack "{self.location}" assets={len(self.assets)}>'

    def search(self, term: str = ''):
        """Search assets, including just the ones that match the search term if
        one was handed in."""
        # TODO: perhaps expand to include MMIF files
        if not term:
            return self.assets
        else:
            return [a for a in self.assets if term in str(a.name)]

    def populate(self, assets_list: str) -> list[str]:
        assets = Path(assets_list)
        added = []
        with open(assets) as fh:
            for line in fh:
                path = line.strip()
                if Path(path).is_file():
                    added.append(path)
                    self.add_asset(path)
        return added

    def add_asset(self, asset: str):
        with open(self.loc_assets_list, 'a') as fh:
            fh.write(f'{asset.strip()}\n')
            asset_path = Path(asset.strip())
            source_path = self.loc_sources / f'{asset_path.stem}.mmif'
            self._assets.add(asset_path)
            if source_path.exists():
                source_mmif = api.run.app.update_source(source_path, asset_path)
                with open(source_path, 'w') as fh:
                    fh.write(source_mmif.serialize(pretty=True))
            else:
                self._sources[source_path.stem] = source_path
                mmif = api.run.app.create_source([asset_path])
                with open(source_path, 'w') as fh:
                    fh.write(mmif.serialize(pretty=True))

    def get_source(self, guid: str):
        pass

    def get_app(self, name: str):
        return self.apps.get(name)

    def add_app(self, name: str, app):
        self.apps[name] = app

    def run_job(self, name: str):
        # TODO: also need to add the input, default is going to be the source
        with open(self.loc_jobs / name, 'w') as fh:
            fh.write(f'STARTED\t{timestamp()}\n')
        job_file = self.loc_jobs / name
        api.run.run_job(name, self.location, self.batch, self.app[0])

    def show_settings(self):
        assets_count = 0 if self.assets is None else len(self.assets)
        console.print(Panel('Current settings'))
        console.print(f' shack     =  {self.location}')
        console.print(f' assets    =  {assets_count}')
        console.print(f' sources   =  {len(self.sources)}')
        console.print(f' batch     =  {shack.batch}')
        console.print(f' path      =  {shack.path}')
        if shack.app is not None:
            console.print(f' selected  =  {shack.app[0]}')
        print()


def print_help(command: str, description: str):
    sep = '  ' if len(command) < 20 else '\n    '
    command = f'{command:20s}'
    text = Text.assemble((command, "bold dark_blue"), sep, description)
    console.print(text)


class ClamsShell(Cmd):

    """The main shell for the CLAM Shack."""

    intro = (
        '\nThis is the CLAM Shack. Type ? for a list of commands.\n'
        '\nCommon commands:\n')
    prompt = 'ClamShack> '

    @classmethod
    def set_prompt(cls, shackname: str):
        cls.prompt = f'ClamShack {shackname}> '

    def __init__(self, shack_location: str | None):
        super().__init__()
        if shack_location:
            path = Path(shack_location)
            if path.is_dir():
                global shack
                shack = ClamShack(shack_location)
                self.set_prompt(path.name)

    def default(self, line):
        """This will apply if no command was recognized."""
        if line == "q" or line == "EOF":
            self.do_quit(line)
            return True
        elif line == 's':
            self.do_show(line)
        elif line.startswith('p '):
            self.do_populate(line[2:])
        elif line.startswith('shack'):
            try:
                console.print(eval(line))
            except Exception as e:
                console.print(e)
        else:
            print(f'... unknown command: {line.strip().split()[0]}')

    def preloop(self):
        """Just adds printing the most salient commands to the queue."""
        self.cmdqueue.append('help init')
        self.cmdqueue.append('help use')
        self.cmdqueue.append('help populate')
        self.cmdqueue.append('help show')
        self.cmdqueue.append('help quit')
        self.cmdqueue.append('help search')
        self.cmdqueue.append('help apps')
        self.cmdqueue.append('help run')
        self.cmdqueue.append('nl')
        if shack is not None:
            self.cmdqueue.append('prep')

    def do_nl(self, arg):
        """Print a white line."""
        print()

    def do_quit(self, arg):
        """Exit the CLAM Shack"""
        print(messages['bye'])
        return True

    def do_show(self, arg):
        """Show current settings"""
        if shack is None:
            print('... Cannot show settings since no CLAM Shack is loaded')
        else:
            shack.show_settings()

    def do_search(self, arg):
        assets = shack.search(arg)
        console.print([str(a) for a in assets])

    def do_init(self, arg):
        """Initialize a CLAM Shack at the locations specified."""
        info(f'Initializing a CLAM Shack at "{arg}"')
        path = Path(arg)
        if path.exists():
            print('... Cannot initialize, path already exists')
        else:
            global shack
            shack = ClamShack(arg)
            self.set_prompt(path.stem)
            print('... Done')

    def do_use(self, arg):
        """Use the specified CLAM Shack"""
        path = Path(arg)
        if not path.is_dir():
            # TODO: should test whether this directory is a shack
            warning('There is no CLAM Shack at that path')
        else:
            global shack
            shack = ClamShack(path)
            self.set_prompt(path.name)
            info(f'Now using the CLAM Shack at {arg}')

    def do_populate(self, arg):
        """Import a list of assets."""
        info('Adding paths to the shack')
        assets_list = Path(arg)
        if shack.location is None:
            warning(f'Need to select (use) or initialize (init) a shack first')
        elif assets_list.is_file():
            added = shack.populate(assets_list)
            info(f'Done, added {len(added)} paths')
        else:
            warning(f'The file provided does not exist')

    def do_apps(self, arg):
        if not arg:
            console.print(shack.app_names)
        else:
            args = arg.split()
            if args[0] == 'select':
                apps = list(sorted(shack.apps.keys()))
                if len(args) >= 2:
                    if args[1] in apps:
                        selection = args[1]
                else:
                    selection = Prompt.ask('Select an app', choices=apps, default=None)
                if selection is None:
                    warning(f'No CLAMS app was selected')
                else:
                    shack.app = (selection, shack.apps[selection])
                    info(f'Selected {selection}')
                    #shack.workflow.append((selection, APPS[selection]))
                    #console.print(f'... Added {selection} to workflow')

    def do_run(self, arg):
        info('Starting job')
        info(f'  name  = {arg}')
        info(f'  batch = {shack.batch}')
        info(f'  app   = {shack.app[0]}')
        shack.run_job(arg)

    def do_new(self, arg):
        """Staging method for new functionality."""
        t = Table()
        t.add_column('property')
        t.add_column('value')
        t.add_row('location', str(shack.location))
        t.add_row('assets', str(len(shack.assets)))
        console.print(t,'<ole>', 23, '\n')
        guid = 'aapb-cneiustLEBiC'
        p = shack.loc_sources / f'{guid}.mmif'
        with open(p) as fh:
            console.print(str(p), Syntax(p.read_text(), 'json'))
        print()
        print('>>>', api.STORAGE_DIR)

    def do_prep(self, arg):
        """Convenience method to set up some things for current development."""
        self.cmdqueue.append('apps select spacy-v3')
        self.cmdqueue.append('run test')

    def help_quit(self):
        print_help('quit', 'Exit the CLAM Shack')

    def help_show(self):
        print_help('show', 'Show current settings')

    def help_init(self):
        print_help('init DIRECTORY', 'Initialize a CLAM Shack in DIRECTORY.')

    def help_use(self):
        print_help('use DIRECTORY', 'Use the CLAM Shack in DIRECTORY')

    def help_populate(self):
        print_help('populate FILENAME', 'Add paths from the file as assets to the Shack ')

    def help_search(self):
        print_help('search TERM', 'Search assets that match TERM')

    def help_apps(self):
        print_help('apps select?', 'List available CLAM apps or select an app')

    def help_run(self):
        print_help(
            'run NAME',
            'Run a job under a unique name, assumes you selected an app')


def parse_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument('-s', '--shack', default=None)
    parser.add_argument('-d', '--debug', action='store_true')
    return parser.parse_args()


if __name__ == '__main__':

    args = parse_arguments()
    if args.debug:
        DEBUG = True
    ClamsShell(args.shack).cmdloop()
