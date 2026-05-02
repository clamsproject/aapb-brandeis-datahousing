import sys
import time
import datetime
from cmd import Cmd
from pathlib import Path
import argparse
import inspect
from collections import defaultdict

from rich import box, prompt
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.markdown import Markdown
from rich.syntax import Syntax

import api.run

from api.cli_utils import console, messages, COMMANDS, timestamp
from api.cli_utils import info, warning, error, dribble, bold


shack = None


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
        self._mmif_files = defaultdict(list)
        self.create_directory_structure()
        self.load_assets()
        self.path = self.mmif_dir
        self._path = Path('.')  # the current working path inside the mmif directory
        self.batch = 'default'
        # Dictionary of batches. The value is a list of identifiers or None, in
        # which case all assets are used.
        self.batches = {'default': None}
        self.jobs = [p for p in self.jobs_dir.iterdir()]
        self.app = None      # selected app for a batch job
        self.params = {}     # run-time parameters

    def create_directory_structure(self):
        self.assets_file = self.location / 'assets' / 'list.txt'
        self.assets_dir = self.location / 'assets'
        self.mmif_dir = self.location / 'mmif'
        self.batches_dir = self.location / 'batches'
        self.sources_dir = self.location / 'sources'
        self.jobs_dir = self.location / 'jobs'
        if not self.assets_file.exists():
            for p in (self.location, self.assets_dir, self.mmif_dir,
                      self.sources_dir, self.jobs_dir):
                p.mkdir(exist_ok=True)
            self.assets_file.touch()

    def load_assets(self):
        """Load the asset paths into memory and do the same with the MMIF
        sources."""
        with open(self.assets_file) as fh:
            for line in fh:
                path = Path(line.strip())
                if path.is_file():
                    self._assets.add(path)
        for subpath in self.sources_dir.iterdir():
            self._sources[subpath.stem] = subpath
        for f in self.mmif_dir.rglob('*'):
            if f.is_file() and f.suffix == '.mmif':
                self._mmif_files[f.stem].append(f)

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
        if not term:
            return self.assets
        else:
            assets = [a for a in self.assets if term in str(a.name)]
            mmif_files = []
            for mf in self._mmif_files:
                if term in mf:
                    mmif_files.extend(self._mmif_files[mf])
            return assets + mmif_files

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
        with open(self.assets_file, 'a') as fh:
            fh.write(f'{asset.strip()}\n')
            asset_path = Path(asset.strip())
            source_path = self.sources_dir / f'{asset_path.stem}.mmif'
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

    def add_parameter(self, param: str, value):
        self.params[param] = str(value)

    def get_source(self, guid: str):
        pass

    def cwd(self) -> str:
        return self._path

    def subdirs(self) -> list[Path]:
        """Return the sorted subdirectories in the current path."""
        path = self.mmif_dir / self._path
        subdirs = [d for d in path.iterdir() if d.is_dir()]
        #prefix_length = len(self.mmif_dir.parts)
        #subdirs = [Path(*sd.parts[prefix_length:]) for sd in subdirs]
        # TODO: actually, no, just take the name, think this through
        subdirs = [Path(sd.name) for sd in subdirs]
        return list(sorted(subdirs))

    def files(self) -> list[Path]:
        """Return the sorted files in the current path."""
        path = self.mmif_dir / self._path
        files = [p for p in path.iterdir() if p.is_file()]
        files = [Path(f.name) for f in files]
        return list(sorted(files))

    def cd(self, path: str):
        """Change the current MMIF path. Assumes that the input was vetted by
        the Shell."""
        if path == '..':
            self._path = self._path.parent
        else:
            self._path = self._path / path

    def run_job(self, name: str):
        with open(self.jobs_dir / name, 'w') as fh:
            fh.write(f'STARTED\t{timestamp()}\n')
        job_file = self.jobs_dir / name
        process_id = api.run.run_job(
            name, self.location, self.cwd(), self.batch, self.app[0], self.params)
        self.jobs.append(Path(self.jobs_dir / name))
        return process_id

    def show_settings(self):
        # TODO: should make this return a list of settings
        app = None if self.app is None else self.app[0]
        assets_count = 0 if self.assets is None else len(self.assets)
        console.print(Panel('Current State'))
        console.print(f' shack       =  {self.location}')
        console.print(f' assets      =  {assets_count}')
        console.print(f' sources     =  {len(self.sources)}')
        console.print(f' jobs        =  {len(self.jobs)}')
        console.print(f' batch       =  {self.batch}')
        console.print(f' path        =  {self._path}')
        console.print(f' clams_app   =  {app}')
        console.print(f' parameters  =  {self.params}')
        print()


def print_command(cmd: str):
    console.print(Text(cmd, "bold dark_blue"))


def print_help(command: str, description: str):
    sep = '  ' if len(command) < 20 else '\n    '
    text = Text.assemble((command, "bold dark_blue"), sep, description)
    console.print('\n', text, '\n')


class Shell(Cmd):

    """The main shell for the CLAM Shack."""

    intro = (
        '\nThis is the CLAM Shack. Type "commands" for a list of commands.\n')
    prompt = bold('ClamShack> ')

    # Hidden commands are not advertized to the user when they type 'help',
    # and there is no help available for them.
    hidden_commands = {'t', 'tswt', 'tspacy', 'nl', 'new'}

    @classmethod
    def set_prompt(cls, shackname: str):
        cls.prompt = bold(f'ClamShack {shackname}> ')

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
        if line.strip() == 'c':
            pass
        elif line == "q" or line == "EOF":
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
            warning(f'Unknown command: {line.strip().split()[0]}')

    ## Core actions

    def do_quit(self, arg):
        """Exit the CLAM Shack"""
        print(messages['bye'])
        return True

    def do_show(self, arg):
        """Show current settings"""
        if shack is None:
            warning('Cannot show state since no ClamShack is loaded')
        else:
            shack.show_settings()

    def do_search(self, arg):
        assets = shack.search(arg)
        console.print([str(a) for a in assets])

    def do_init(self, arg):
        """Initialize a CLAM Shack at the locations specified."""
        path = Path(arg)
        if path.exists():
            warning('Cannot initialize, path already exists')
        else:
            global shack
            shack = ClamShack(arg)
            self.set_prompt(path.stem)
            info(f'Initialized a CLAM Shack at "{arg}"')

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
            print()

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
        if shack is None:
            warning("Cannot print or select apps when no Shack is loaded.")
            return
        app_dict = dict(enumerate(shack.app_names))
        if not arg:
            console.print(Panel('Registered CLAMS Apps'))
            for key in sorted(app_dict):
                console.print(f' {key}: {app_dict[key]}')
            print()
        else:
            selection = arg
            if selection.isnumeric():
                selection = app_dict.get(int(selection))
            if selection in shack.apps:
                shack.app = (selection, shack.apps[selection])
                dribble(f'Selected {selection}\n')
            else:
                warning(f'Selection does not exist\n')

    def do_jobs(self, arg):
        console.print(Panel('List of jobs associated with this Shack'))
        table = Table('name', 'started', 'app', 'batch', box=box.ROUNDED)
        for job in sorted(shack.jobs):
            lines = job.read_text().split('\n')
            started = lines[0].split('\t')[1]
            command = lines[1].split('\t')[1].split()
            # not including 'python', 'run_batch.py' and the name of the job
            command = command[3:]
            n = 2
            pairs = [command[i : i + n] for i in range(0, len(command), n)]
            # the parameters at the end do funky stuff
            pairs = [p for p in pairs if len(p) == 2]
            for pair in pairs:
                param, value = pair
                if param == '--app':
                    app = value
                if param == '--batch':
                    batch = value
            table.add_row(job.name, started, app, batch)
        console.print(table)

    def do_params(self, arg):
        args = arg.split()
        if len(args) == 1 and args[0] == 'reset':
            shack.params = {}
        elif len(args) == 2:
            param, value = args
            shack.add_parameter(param, value)
        console.print(shack.params)
        print()

    def do_run(self, arg):
        if not arg:
            warning('You must provide a name for the job.')
            return
        job_file = shack.jobs_dir / arg
        if job_file.is_file():
            warning('A job with that name already exists.')
            return
        if shack.cwd() != Path('.'):
            files = [Path(f.name) for f in shack.files() if f.suffix == '.mmif']
            if not files:
                print('Nothing to do, there are no MMIF files in the current path\n')
                return
        console.print(Panel('Starting job'))
        dribble(f'  name   = {arg}')
        dribble(f'  path   = {shack.cwd()}')
        dribble(f'  batch  = {shack.batch}')
        dribble(f'  app    = {shack.app[0]}')
        dribble(f'  params = {shack.params}')
        process_id = shack.run_job(arg)
        dribble(f'  pid    = {process_id}')

    def do_pwd(self, arg):
        console.print(shack.cwd())
        print()

    def do_dir(self, arg):
        console.print(Panel(f'Sub directories at "{shack.cwd()}"'))
        for n, d in enumerate(shack.subdirs()):
            console.print(f' {n}: {str(d)}')
        print()

    def do_files(self, arg):
        console.print(Panel(f'MMIF files at "{shack.cwd()}"'))
        for n, f in enumerate(shack.files()):
            console.print(f' {n}: {str(f)}')
        print()

    def do_cd(self, arg):
        subdirs = { n: str(p) for n, p in enumerate(shack.subdirs()) }
        if arg.isnumeric() and int(arg) in subdirs:
            arg = subdirs[int(arg)]
        p = Path(shack.mmif_dir / shack.cwd() / arg)
        if p.exists():
            shack.cd(arg)
            console.print(f'New path: {shack.cwd()}\n')
        else:
            print('No such directory\n')

    def do_help(self, arg):
        if not arg:
            funs = inspect.getmembers(self.__class__, predicate=inspect.isfunction)
            names = [name[3:] for name, method in funs if name .startswith('do_')]
            names = [n for n in names if not n in self.hidden_commands]
            console.print(Panel('Available commands'))
            for cmd in names:
                print_command(' ' + cmd)
            console.print('\n Type "help <command>" for help on a command\n')
        elif arg in COMMANDS:
            print_help(*COMMANDS.get(arg))
        else:
            print(f'No help available for {arg}\n') 

    ## Undocumented actions for debugging and development

    def do_new(self, arg):
        """Staging method for new functionality."""
        t = Table()
        t.add_column('property')
        t.add_column('value')
        t.add_row('location', str(shack.location))
        t.add_row('assets', str(len(shack.assets)))
        console.print(t,'<ole>', 23, '\n')
        guid = 'aapb-cneiustLEBiC'
        p = shack.sources_dir / f'{guid}.mmif'
        with open(p) as fh:
            console.print(str(p), Syntax(p.read_text(), 'json'))
        print()

    def do_tspacy(self, arg):
        """Command to run commands that I am testing, for development only."""
        self.cmdqueue.append('use data/test')
        self.cmdqueue.append('apps select http://apps.clams.ai/spacy/v3')
        self.cmdqueue.append(f'run {arg}')

    def do_tswt(self, arg):
        """Command to run commands that I am testing, for development only."""
        self.cmdqueue.append('use data/test')
        self.cmdqueue.append('apps select http://apps.clams.ai/swt/v7.0')
        self.cmdqueue.append('params pretty True')
        self.cmdqueue.append('params sticther True')
        self.cmdqueue.append(f'run {arg}')

    def do_t(self, arg):
        self.cmdqueue.append('p spacy/v3')
        self.cmdqueue.append('p spacy/v3/5fe49d06725497b274b6eaaf0fe0c5d2')
        self.cmdqueue.append('p spacy/v3/5fe49d06725497b274b6eaaf0fe0c5d2.json')
        self.cmdqueue.append('p spacy/v3/d41d8cd98f00b204e9800998ecf8427e') 
        self.cmdqueue.append('p spacy/v3/d41d8cd98f00b204e9800998ecf8427e.json') 

    def do_nl(self, arg):
        """Print a white line."""
        print()


def parse_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument('-s', '--shack', default=None)
    parser.add_argument('-d', '--debug', action='store_true')
    return parser.parse_args()


if __name__ == '__main__':

    args = parse_arguments()
    if args.debug:
        DEBUG = True
    Shell(args.shack).cmdloop()
