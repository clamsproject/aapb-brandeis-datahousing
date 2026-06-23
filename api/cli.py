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

from api.cli_utils import Job, console, messages, COMMANDS, timestamp
from api.cli_utils import info, warning, error, dribble, get_tree


from mmif.utils.cli import describe
from mmif.utils.workflow_helper import describe_single_mmif, generate_param_hash


shack = None

DEBUG = False


class ClamShack:

    """
    Instances of this class keep track of all information like location, current
    batch, current path in the shack and others. It is also the entry point to
    all batch processing.

    TODO: this maybe should be defined somewhere in the api.model package.
    """

    def __init__(self, directory: str, assets: str | None):
        self.location = Path(directory)
        self.assets_file = self.location / 'assets' / 'list.txt'
        self.assets_dir = self.location / 'assets'
        self.mmif_dir = self.location / 'mmif'
        self.batches_dir = self.location / 'batches'
        self.sources_dir = self.location / 'sources'
        self.jobs_dir = self.location / 'jobs'
        self._apps = api.run.APPS
        if assets is not None:
            if self.location.exists():
                exit(f'Cannot create a ClamShack because "{self.location}" already exists')
            self.create_directory_structure()
            self.add_assets(assets)
        else:
            if not self.is_clams_directory():
                exit(f'Cannot open "{self.location}" since it is not a ClamShack directory')
        self._assets = Assets(self)
        self.mmif_index = MmifIndex(self)
        self._path = Path('.')  # the current working path inside the mmif directory
        self.batch = 'default'
        # Dictionary of batches. The value is a list of identifiers or None, in
        # which case all assets are used.
        self.batches = {'default': None}
        self._jobs = [p for p in self.jobs_dir.iterdir()]
        self.app = None      # selected app for a batch job
        self.params = {}     # run-time parameters

    def create_directory_structure(self):
        """Create the directory scaffolding, assumes the Shack direcotry does not
        exist yet."""
        for p in (self.location, self.assets_dir, self.mmif_dir,
                  self.sources_dir, self.jobs_dir):
            p.mkdir()
        self.assets_file.touch()

    def is_clams_directory(self) -> bool:
        """Return True if the directory appears to contain a ClamShack, return False
        otherwise."""
        for p in (self.location, self.assets_dir, self.mmif_dir,
                  self.sources_dir, self.jobs_dir):
            if not Path(p).is_dir():
                return False
        if not Path(self.assets_file).is_file():
            return False
        return True

    @property
    def assets(self) -> list[Path]:
        return list(sorted(self._assets.files))

    @property
    def sources(self) -> list[str]:
        return list(sorted(self._assets.sources.values()))

    @property
    def apps(self):
        return self._apps

    @property
    def app_names(self) -> list:
        return list(sorted(self._apps.keys()))

    @property
    def job_names(self):
        return [p.name for p in self._jobs]

    @property
    def jobs(self):
        """Recreate jobs from the list of paths each time you access this propery,
        this makes sure updates from long running jobs are included."""
        jobs = {}
        for path in self._jobs:
            job = Job(path)
            jobs[job.name] = job
        return jobs

    def __str__(self):
        return f'<ClamShack "{self.location}" assets={len(self.assets)}>'

    def search(self, guid: str = '', app: str = '') -> list:
        """Search assets and MMIF files given a partial guid or a partial app name."""
        if guid:
            result = [a for a in self.assets if guid in str(a.name)]
            for mf in self.mmif_index.data:
                if guid in mf:
                    result.extend(self.mmif_index.data[mf])
            return result
        elif app:
            # TODO: this is very ugly and broken, at least properly parse the path to
            # avoid matching on any part of the path. We could improve MmifIndex and 
            # create an index on CLAMS apps. This would improve performance but that is
            # a secondary motivation because performance is fine on a small Shack.
            paths = set()
            for guid in self.mmif_index.data:
                for path in self.mmif_index.data[guid]:
                    for part in path.parts:
                        if app in part:
                            paths.add(path.parent)
                            break
            return list(sorted(paths))
        else:
            return []

    def add_assets(self, assets_list: str) -> None:
        """Add assets from the external assets list to the Shack. Only do this if
        assets weren't added before. Copy the assets list and then make sure all
        MMIF sources are initialized. Alslso reloads the assets into the ClamShack
        instance."""
        assets_path = Path(self.assets_file)
        current_content = assets_path.read_text().strip()
        if current_content != '':
            print('Assets were already added')
            return
        assets_path.write_text(Path(assets_list).read_text())
        added = []
        with open(assets_path) as fh:
            directory = fh.readline().strip()
            for line in fh:
                path = line.strip()
                if not path:
                    continue  ## skipping empty lines
                full_path = Path(directory) / path
                container_path = Path('/data') / path
                if full_path.is_file():
                    #self._assets.add(full_path)
                    self.add_mmif_source(container_path)
                    added.append(container_path)
                else:
                    print(f'WARNING: not a file {str(full_path)}')

    def add_mmif_source(self, container_path: Path):
        source_path = self.sources_dir / f'{container_path.stem}.mmif'
        if source_path.exists():
            source_mmif = api.run.app.update_source(source_path, container_path)
        else:
            #self._assets.sources[source_path.stem] = source_path
            source_mmif = api.run.app.create_source([container_path])
        with open(source_path, 'w') as fh:
            fh.write(source_mmif.serialize(pretty=True))

    def add_parameter(self, param: str, value):
        self.params[param] = str(value)

    def get_source(self, guid: str):
        pass

    def cwd(self) -> str:
        return self._path

    def subdirs(self) -> list[Path]:
        """Return the sorted subdirectories in the current path."""
        path = self.mmif_dir / self._path
        subdirs = [Path(d.name) for d in [d for d in path.iterdir() if d.is_dir()]]
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
        if path == '~':
            self._path = Path('.')
        elif path == '..':
            # TODO: also allow for ../.. and then do the right thing
            self._path = self._path.parent
        else:
            self._path = self._path / path

    def run_job(self, name: str):
        with open(self.jobs_dir / name, 'w') as fh:
            fh.write(f'STARTED\t{timestamp()}\n')
        job_file = self.jobs_dir / name
        process_id = api.run.run_job(
            name, self.location, self.cwd(), self.batch, self.app, self.params)
        self._jobs.append(Path(self.jobs_dir / name))
        return process_id

    def get_settings(self):
        app = None if self.app is None else self.app.name
        assets_count = 0 if self.assets is None else len(self.assets)
        return [
            ('shack', self.location),
            ('assets', assets_count),
            ('sources', len(self.sources)),
            ('jobs', len(self._jobs)),
            ('path', str(self._path)),
            ('clams_app', app),
            ('parameters', self.params)]

    def show_settings(self):
        table = Table(show_header=False)
        for name, value in self.get_settings():
            #console.print(f' {name:10}  =  {value}')
            table.add_row(name, str(value))
        console.print(Panel("Shack settings and information"))
        console.print(table)


def print_command(cmd: str):
    console.print(Text(cmd, "bold dark_blue"))


def print_help(command: str, description: str):
    # TODO: update this to use textwrap 
    sep = '  ' if len(command) < 20 else '\n    '
    text = Text.assemble((command, "bold dark_blue"), sep, description)
    console.print('\n', text, '\n')



class Assets:

    """Keeps track of the asset files and the MMIF source files created for those
    assets. Includes the root instance variable which is the lowest directory that
    contains all assets."""

    def __init__(self, shack: ClamShack):
        self.root = None
        self.files = set()
        self.sources = {}
        with open(shack.assets_file) as fh:
            self.root = fh.readline().strip()
            for line in fh:
                path = Path(self.root) / line.strip()
                if path.is_file():
                    self.files.add(path)
        for subpath in shack.sources_dir.iterdir():
            self.sources[subpath.stem] = subpath

    def __str__(self):
        return (f'<Assets root="{self.root}"'
                + f' assets={len(self.assets)} sources={len(self.sources)}>')

    def pp_sources(self):
        if self.sources:
            print('\nMMIF source files in the Shack:')
            for k in self.sources:
                print(f'  {k}  -->  {self.sources[k]}')


class MmifIndex:

    """Index of MMIF files in the Shack. For now it is not much of an index but
    in the data instance variable there is a dictionary that maps GUIDs to lists
    of MMIF file locations."""

    def __init__(self, shack: ClamShack):
        # TODO: this is done for the search but is never updated after a new job
        # finished running, need to rethink this.
        self.data = defaultdict(list)
        for f in shack.mmif_dir.rglob('*'):
            if f.is_file() and f.suffix == '.mmif':
                self.data[f.stem].append(f)

    def __str__(self):
        return f'<MiffIndex with {len(self.data)} GUIDs>'


class Shell(Cmd):

    """The main shell for the ClamShack."""

    intro = (
        '\nThis is the CLAM Shack. Type "?" for a list of commands.\n')
    prompt = 'ClamShell> '

    # Hidden commands are not advertized to the user when they type 'help'
    # and there is no help available for them.
    hidden_commands = {'t', 'x', 'y', 'z', 'tswt', 'tspacy', 'pspacy', 'nl', 'new'}

    @classmethod
    def set_prompt(cls, shackname: str):
        cls.prompt = f'ClamShell {shackname}> '

    def __init__(self, clamshack: ClamShack | None):
        super().__init__()
        if clamshack:
            global shack
            shack = clamshack
            self.set_prompt(shack.location.name)

    def default(self, line):
        """This will apply if no command was recognized."""
        if line.strip() == 'c':
            pass
        elif line == "q" or line == "EOF":
            self.do_quit(line)
            return True
        elif line == 's':
            self.do_show(line)
        elif line.startswith('shack'):
            try:
                console.print(eval(line))
            except Exception as e:
                console.print(e)
        else:
            warning(f'Unknown command: {line.strip().split()[0]}')

    def postcmd(self, stop, line):
        print()
        return stop

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
        if not arg:
            warning('No search parameters given')
            return
        search_type, *args = arg.split()
        if search_type == 'guid':
            assets = shack.search(guid=args[0])
        elif search_type == 'app':
            assets = shack.search(app=args[0])
        else:
            warning(f'Cannot search for "{arg}", use "guid" or "app"')
            return
        console.print([str(a) for a in assets])

    def do_apps(self, arg):
        if shack is None:
            warning("Cannot print or select apps when no Shack is loaded.")
            return
        app_dict = dict(enumerate(shack.app_names))
        if not arg:
            console.print(Panel('Registered CLAMS Apps'))
            for key in sorted(app_dict):
                console.print(f' {key}: {app_dict[key]}')
        else:
            selection = arg
            if selection.isnumeric():
                selection = app_dict.get(int(selection))
            if selection in shack.apps:
                shack.app = api.run.ClamsApp(selection, shack.apps[selection])
                dribble(f'Selected {selection}')
            else:
                warning(f'Selection does not exist')

    def do_register(self, arg):
        api.run.register_app(arg)

    def do_jobs(self, arg):
        if arg:
            try:
                job = shack.jobs[arg]
                console.print(Panel(job.name))
                console.print(job.info())
                console.print(job.info_guids())
            except KeyError:
                warning('No such job.')
                return
        else:
            console.print(Panel(
                'Jobs associated with this Shack'
                ' (listed in order of when they were started)'))
            table = Table('name', 'app', 'guids', 'time', box=box.ROUNDED)
            for job in sorted(shack.jobs.values(), key=lambda x: x.started, reverse=False):
                elapsed = job.time_elapsed()
                table.add_row(job.name, job.app, str(len(job.guids)), elapsed)
            console.print(table)

    def do_params(self, arg):
        args = arg.split()
        if len(args) == 1 and args[0] == 'reset':
            shack.params = {}
        elif len(args) == 2:
            param, value = args
            shack.add_parameter(param, value)
        console.print(shack.params)

    def do_run(self, arg):
        if not arg:
            warning('You must provide a name for the job.')
            return
        if shack.app is None:
            warning('You must select a CLAMS app.')
            return
        job_file = shack.jobs_dir / arg
        if job_file.is_file():
            warning('A job with that name already exists.')
            return
        if shack.cwd() != Path('.'):
            files = [Path(f.name) for f in shack.files() if f.suffix == '.mmif']
            if not files:
                print('Nothing to do, there are no MMIF files in the current path')
                return
        console.print(Panel('Starting job'))
        dribble(f'  name   = {arg}')
        dribble(f'  path   = {shack.cwd()}')
        dribble(f'  batch  = {shack.batch}')
        dribble(f'  app    = {shack.app}')
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
        # first translate an index from the dir command into a sub directory
        subdirs = { n: str(p) for n, p in enumerate(shack.subdirs()) }
        if arg.isnumeric() and int(arg) in subdirs:
            arg = subdirs[int(arg)]
        # get the new path
        p = Path(shack.mmif_dir / shack.cwd() / arg)
        # now check for existence or whether we are going back home
        if p.exists() or arg == '~':
            shack.cd(arg)
            console.print(f'New path: {shack.cwd()}')
        else:
            print('No such directory')

    def do_home(self, arg):
        self.do_cd('~')

    def do_up(self, arg):
        self.do_cd('..')

    def do_tree(self, arg):
        args = arg.split()
        full = True if '-f' in args else False
        parameters = True if '-p' in args else False
        t = get_tree(shack.mmif_dir / shack._path, full=full)
        console.print(Panel('MMIF File tree'))
        self.do_nl('')
        console.print(t)
        if parameters:
            self.cmdqueue.append('properties')

    def do_properties(self, arg):
        # TODO: make this more general
        if len(shack._path.parts) in (3, 6, 9, 12, 15, 18, 21):
            props_path = shack._path.parent / (shack._path.name + '.json')
            full_props_path = shack.mmif_dir / props_path
            console.print(Panel(str(props_path)))
            console.print(full_props_path.read_text())

    def do_describe(self, arg):
        full_path = shack.mmif_dir / shack._path
        for n, f in enumerate(shack.files()):
            if n == int(arg):
                console.print(Panel(f'describe {str(f)}'))
                desc = describe_single_mmif(full_path / f)
                console.print(desc)

    def do_help(self, arg):
        if not arg:
            funs = inspect.getmembers(self.__class__, predicate=inspect.isfunction)
            names = [name[3:] for name, method in funs if name .startswith('do_')]
            names = [n for n in names if not n in self.hidden_commands]
            console.print(Panel('Available commands'))
            for cmd in names:
                print_command(' ' + cmd)
            console.print('\n Type "help <command>" for help on a command')
        elif arg in COMMANDS:
            print_help(*COMMANDS.get(arg))
        else:
            print(f'No help available for {arg}')

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
        self.cmdqueue.append('apps select http://apps.clams.ai/spacy/v3')
        self.cmdqueue.append(f'run {arg}')

    def do_tswt(self, arg):
        """Command to run commands that I am testing, for development only."""
        self.cmdqueue.append('apps select http://apps.clams.ai/swt/v7.0')
        self.cmdqueue.append('params pretty True')
        self.cmdqueue.append('params sticther True')
        self.cmdqueue.append(f'run {arg}')

    def do_pspacy(self, arg):
        self.cmdqueue.append('p spacy/v3')
        self.cmdqueue.append('p spacy/v3/d41d8cd98f00b204e9800998ecf8427e') 
        self.cmdqueue.append('p spacy/v3/d41d8cd98f00b204e9800998ecf8427e.json') 

    def do_t(self, arg):
        self.cmdqueue.append('search guid 512')
        self.cmdqueue.append('search app spacy')
        #self.cmdqueue.append('jobs')
        self.cmdqueue.append('tree')

    def do_x(self, arg):
        self.cmdqueue.append('register http://127.0.0.1:5001')
        self.cmdqueue.append('apps 0')
        self.cmdqueue.append('params pretty True')
        self.cmdqueue.append('s')
       
    def do_y(self, arg):
        self.cmdqueue.append('cd 0')
        self.cmdqueue.append('cd 0')
        self.cmdqueue.append('cd 0')
        self.cmdqueue.append('tree')
        self.cmdqueue.append('properties')
        self.cmdqueue.append('describe 0')

    def do_nl(self, arg):
        print()


def parse_arguments():
    parser = argparse.ArgumentParser()
    s_help = "Open the ClamShack in DIR or create it if the directory does not exist"
    a_help = "Add the assets in FILE to the ClamShack in DIR"
    parser.add_argument('--shack', metavar='DIR', required=True, help=s_help)
    parser.add_argument('--assets', metavar='FILE', default=None, help=a_help)
    parser.add_argument('--debug', action='store_true')
    return parser.parse_args()


if __name__ == '__main__':

    args = parse_arguments()
    if args.debug:
        DEBUG = True
    shack = ClamShack(args.shack, args.assets)
    Shell(shack).cmdloop()
