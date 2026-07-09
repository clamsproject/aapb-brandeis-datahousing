import sys
import time
import datetime
import textwrap
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

from mmif.utils.cli import describe
from mmif.utils.workflow_helper import describe_single_mmif, generate_param_hash

import api.run

from api.utils import load_json
from api.cli_utils import Job, console, messages, COMMANDS, timestamp
from api.cli_utils import info, warning, error, dribble, get_tree
from api.cli_utils import path_as_triples, path_as_string


shack = None

DEBUG = False


class ClamShack:

    """
    Instances of this class keep track of all information like location, current
    path in the shack and others. They are also the entry point for any changes
    made to the shack, like registering CLAMS apps and running jobs.

    TODO: this maybe should be defined somewhere in the api.model package.
    TODO: a shack should not print to the console, leave that to the shell
    """

    def __init__(self, directory: str, assets: str | None):
        self.location = Path(directory)
        self.assets_file = self.location / 'assets' / 'list.txt'
        self.assets_dir = self.location / 'assets'
        self.mmif_dir = self.location / 'mmif'
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
        self._jobs = [p for p in self.jobs_dir.iterdir() if p.suffix == '.txt']
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
    def name(self):
        return self.location.name

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
        """Recreate jobs from the list of paths each time you access this property,
        this makes sure updates from long running jobs are included."""
        jobs = {}
        for path in self._jobs:
            job = Job(path)
            jobs[job.name] = job
        return jobs

    def __str__(self):
        return f'<ClamShack "{self.location}" assets={len(self.assets)}>'

    def job_file(self, job_name: str):
        return self.jobs_dir / f'{job_name}.txt'

    def search(self, term: str, assets=False, mmif=False, app=False) -> list | dict:
        """Search assets and MMIF files given a partial guid or a partial app name."""
        # TODO: decide on return values
        #    - assets: list of assets and sources used in them
        #    - mmif: dictionary of sources and the directories they occur in
        #    - app: list of directories
        if assets:
            return self.mmif_index.search_assets(term)
        elif mmif:
            return self.mmif_index.search_mmif(term)
        elif app:
            return self.mmif_index.search_app(term)
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

    def parameter_file(self) -> Path | None:
        """Return the parameter file that goes with the current directory,
        of None if there is no such file."""
        #if len(self._path.parts) in (3, 6, 9, 12, 15, 18, 21):
        path_lenght = len(self._path.parts)
        if path_lenght > 0 and path_lenght % 3 ==0:
            return self.mmif_dir / self._path.parent / (self._path.name + '.json')
        else:
            return None

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

    def register(self, url: str):
        api.run.register_app(url)

    def select_app(self, selection: str) -> bool:
        """Select an application if it is amongst the registered apps,
        return True or False depending on whether selection succeeded."""
        if selection in shack.apps:
            shack.app = api.run.ClamsApp(selection, shack.apps[selection])
            return True
        return False

    def run_job(self, name: str):
        with open(self.job_file(name), 'w') as fh:
            fh.write(f'STARTED\t{timestamp()}\n')
        job_file = self.jobs_dir / name
        process_id = api.run.run_job(
            name, self.location, self.cwd(), self.app, self.params)
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
    lines = textwrap.wrap(
        description, width=80, initial_indent='     ', subsequent_indent='     ')
    text = Text.assemble('\n ', (command, "bold dark_blue"))
    console.print(text)
    for l in lines:
        console.print(l)


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

    """Index of MMIF files in the Shack to support searching the MMIF storage. For
    now it is not much of an index but at least there is a dictionary of filenames
    mapped to path and a set of all directories with MMIF files.

    data: dict  -  { filename -> list of paths }
    dirs: set   -  directories inside of the mmif storage

    """

    # TODO: the index is not updated after new files were added

    def __init__(self, shack: ClamShack):
        self.sources = shack.sources
        self.data = defaultdict(list)
        self.dirs = set()
        prefix = shack.mmif_dir.parts
        for f in shack.mmif_dir.rglob('*'):
            f_rel = Path(*f.parts[len(prefix):])
            self.dirs.add(f_rel.parent)
            if f.is_file() and f.suffix == '.mmif':
                self.data[f.stem].append(f_rel)

    def __str__(self):
        return f'<MiffIndex with {len(self.data)} MMIF files in {len(self.dirs)} directories>'

    def search_assets(self, term: str) -> list:
        return [a for a in self.sources if term in str(a.name)]

    def search_mmif(self, term: str) -> dict:
        results = {}
        for name in self.data.keys():
            if term in name:
                results[name] = self.data[name]
        return results

    def search_app(self, term: str) -> list:
        results = []
        dirs = [d for d in self.dirs if len(d.parts) % 3 == 0]
        for directory in dirs:
            triples = path_as_triples(directory)
            if triples and term in triples[-1][0]:
                results.append(directory)
        return results


class Shell(Cmd):

    """Shell for command-line access to the ClamShack."""

    intro = (
        '\nThis is the CLAM Shack. Type "?" for a list of commands.\n')
    prompt = 'ClamShell> '
    _history = []

    # Hidden commands are not advertized to the user when they type 'help'
    hidden_commands = {'t', 'x', 'y', 'z', 'nl', 'new', 'echo'}

    @classmethod
    def set_prompt(cls, shack: ClamShack):
        cls.prompt = f'ClamShell {shack.name}> '

    def __init__(self, clamshack: ClamShack | None):
        super().__init__()
        if clamshack:
            global shack
            shack = clamshack
            self.set_prompt(shack)

    @property
    def history(self):
        return self.__class__._history

    def default(self, line):
        """This applies if no command was recognized."""
        if line.strip() == 'c':
            pass
        elif line in ("q", "EOF"):
            self.do_quit(line)
            return True
        elif line == 's':
            self.do_show(line)
        elif line.startswith('shack'):
            try:
                console.print(eval(line))
            except Exception as e:
                console.print(e)
        elif line.startswith('p '):
            # This is not advertized but it is here to sneak in the 
            # possibility to evaluate Python expressions.
            command = ' '.join(line.split()[1:])
            if command:
                try:
                    console.print(eval(command))
                except Exception as e:
                    console.print(e)
        else:
            warning(f'Unknown command: {line.strip().split()[0]}')

    def postcmd(self, stop, line):
        """Print an empty line after a command is executed and put the command
        on the history list."""
        print()
        if not line.split()[0] in self.__class__.hidden_commands:
            self.history.append(line)
        return stop

    ## Core actions

    def do_quit(self, arg):
        """Exit the CLAM Shack"""
        print(messages['bye'])
        return True

    def do_show(self, arg):
        """Show current settings"""
        shack.show_settings()

    def do_history(self, arg):
        if arg == 'save':
            with open('history.txt', 'w') as fh:
                for line in self.history:
                    fh.write(f'{line}\n')
            console.print('History was saved to "history.txt"')
        else:
            console.print(self.history)

    def do_search(self, arg):
        if not arg:
            warning('No search parameters given')
            return
        search_type, *args = arg.split()
        if search_type == 'assets':
            results = shack.search(term=args[0], assets=True)
            console.print(Panel(f'Assets matching "{args[0]}"'))
            for r in results:
                print(f' {r.name}')
        elif search_type == 'mmif':
            results = shack.search(term=args[0], mmif=True)
            console.print(Panel(f'MMIF files matching "{args[0]}"'
                                 ' and the directories where they occur'))
            for name in results:
                print(' ' + name)
                for p in results[name]:
                    print('    ', path_as_string(p.parent))
        elif search_type == 'app':
            results = shack.search(term=args[0], app=True)
            console.print(Panel(f'Directories created by app matching "{args[0]}"'))
            for p in results:
                print(f' {path_as_string(p)}')
        else:
            warning(f'Cannot search for "{arg}", use "assets", "mmif" or "app"')
            return

    def do_apps(self, arg):
        app_dict = dict(enumerate(shack.app_names))
        if not arg:
            console.print(Panel('Registered CLAMS Apps'))
            for key in sorted(app_dict):
                console.print(f' {key}: {app_dict[key]}')
        else:
            selection = arg
            if selection.isnumeric():
                selection = app_dict.get(int(selection))
            succeeded = shack.select_app(selection)
            if succeeded:
                dribble(f'Selected {selection}')
            else:
                warning(f'Selection does not exist')

    def do_register(self, arg):
        shack.register(arg)

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
        elif len(args) == 1:
            try:
                params = load_json(args[0])
                shack.params = params
            except Exception:
                print(f'There is no file "{args[0]}"')
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
        process_id = shack.run_job(arg)
        console.print(Panel('Started job'))
        dribble(f'  name   = {arg}')
        dribble(f'  path   = {shack.cwd()}')
        dribble(f'  app    = {shack.app}')
        dribble(f'  params = {shack.params}')
        dribble(f'  pid    = {process_id}')

    def do_script(self, arg):
        """Loads a file of commands and then run them. The file of commands has to
        be in the same format as the file that is created by the "history save"
        command."""
        # TODO: check the script file so that it only has one run command
        if arg:
            script_path = Path(arg)
            if script_path.is_file():
                commands = []
                for line in script_path.read_text().split('\n'):
                    if line.strip():
                        commands.append(line.strip())
                for c in commands:
                    self.cmdqueue.append(f'echo {c}')
                    self.cmdqueue.append(c)

    def do_pwd(self, arg):
        print(shack.cwd())

    def do_dir(self, arg):
        console.print(Panel(f'Sub directories at "{shack.cwd()}"'))
        for n, d in enumerate(shack.subdirs()):
            console.print(f' {n}: {str(d)}')

    def do_files(self, arg):
        console.print(Panel(f'MMIF files at "{shack.cwd()}"'))
        for n, f in enumerate(shack.files()):
            console.print(f' {n}: {str(f)}')

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
            parameter_file = shack.parameter_file()
            if parameter_file is not None:
                print()
                console.print(Panel(str(parameter_file)))
                console.print(parameter_file.read_text())

    def do_describe(self, arg):
        if not arg.isdigit():
            warning('The argument must be an integer')
            return
        full_path = shack.mmif_dir / shack._path
        for n, f in enumerate(shack.files()):
            if n == int(arg):
                if not (full_path / f).suffix == '.mmif':
                    warning('The file at that index is not a MMIF file')
                    return
                console.print(Panel(f'describe {str(f)}'))
                desc = describe_single_mmif(full_path / f)
                console.print(desc)
                return
        warning('No MMIF file at that index')

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

    def do_echo(self, arg):
        print(f'>>> {arg}')

    def do_nl(self, arg):
        # Useful when adding mulitple commands to the queue.
        print()

    ## Undocumented actions for debugging and development

    def do_new(self, arg):
        """Staging method for new functionality."""
        pass

    def do_t(self, arg):
        self.cmdqueue.append('script s.txt')

    def do_x(self, arg):
        self.cmdqueue.append('register http://127.0.0.1:5001')
        self.cmdqueue.append('apps 0')
        self.cmdqueue.append('cd 0')
        self.cmdqueue.append('cd 0')
        self.cmdqueue.append('cd 0')
        self.cmdqueue.append('cd 0')
        self.cmdqueue.append('cd 0')
        self.cmdqueue.append('cd 0')
        self.cmdqueue.append('params pretty True')
        self.cmdqueue.append('params params.json')
        self.cmdqueue.append('jobs')
        self.cmdqueue.append('s')

    def do_y(self, arg):
        self.cmdqueue.append('register 127.0.0.1:5001')
        self.cmdqueue.append('apps')

    def do_z(self, arg):
        self.cmdqueue.append('search assets f55')
        self.cmdqueue.append('search mmif f55')
        self.cmdqueue.append('search app captioner')
        #self.cmdqueue.append('')


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
