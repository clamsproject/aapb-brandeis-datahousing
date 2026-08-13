import sys
import time
import json
import shutil
import datetime
import textwrap
import traceback
import subprocess
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
from api.cli_utils import path_as_string, path_as_tuples


DEBUG = False


class ShackError(Exception): pass


class ClamShack:

    """
    Instances of this class keep track of all information like location, current
    path in the shack and others. They are also the entry point for any changes
    made to the shack, like registering CLAMS apps and running jobs.

    TODO: this maybe should be defined somewhere in the api.model package.
    TODO: get rid of the shack global variable
    """

    def __init__(self, directory: str, assets: str | None):
        self.location = Path(directory)
        self.assets_dir = self.location / 'assets'
        self.mmif_dir = self.location / 'mmif'
        self.sources_dir = self.location / 'sources'
        self.jobs_dir = self.location / 'jobs'
        self.assets_file = self.assets_dir / 'list.txt'
        self.history_file = self.location / '.history'
        self.queue_file = self.location / '.queue'
        self.error_file = self.location / '.errors'
        if assets is not None:
            if self.location.exists():
                exit(f'Cannot create a ClamShack: "{self.location}" already exists')
        elif not self.is_clams_directory():
              exit(f'Cannot open "{self.location}": it is not a ClamShack directory')
        self.create_directory_structure()
        self.add_assets(assets)
        self._assets = Assets(self)
        self.mmif_index = MmifIndex(self)
        self.path = Path('.')    # the current working path inside the mmif directory
        self._jobs = [p for p in self.jobs_dir.iterdir() if p.suffix == '.txt']
        self.history = History(self.history_file)
        self.apps = api.run.APPS
        self.app = None          # selected app for a batch job
        self.params_file = None  # input file used to set parameters
        self.params = {}         # run-time parameters

    def create_directory_structure(self):
        """Create the directory scaffolding. The files are just touched so that we
        are certain they exist, the exception is the queue file which we make sure
        is empty when we start a shack."""
        for p in (self.location, self.assets_dir, self.mmif_dir,
                  self.sources_dir, self.jobs_dir):
            p.mkdir(exist_ok=True)
        self.assets_file.touch()
        self.history_file.touch()
        self.error_file.touch()
        self.queue_file.write_text('')

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
    def app_names(self) -> list:
        return list(sorted(self.apps.keys()))

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

    @property
    def index(self):
        return self.mmif_index

    def __str__(self):
        return f'<ClamShack "{self.location}" assets={len(self.assets)}>'

    def job_file(self, job_name: str):
        return self.jobs_dir / f'{job_name}.txt'

    def search(self, term: str, mode: str) -> list | dict:
        """Search assets, MMIF files and parameter definition given a search term
        that is a partial guid or a partial app name."""
        self.mmif_index.dequeue()
        if mode == 'assets':
            return self.mmif_index.search_assets(term)
        elif mode == 'mmif':
            return self.mmif_index.search_mmif(term)
        elif mode == 'app':
            return self.mmif_index.search_app(term)
        elif mode == 'params':
            return self.mmif_index.search_params(term)
        else:
            return []

    def add_assets(self, assets_list: str | None) -> None:
        """Add assets from the external assets list to the Shack. Only do this if
        assets weren't added before. Copy the assets list and then make sure all
        MMIF sources are initialized. Alslso reloads the assets into the ClamShack
        instance."""
        if assets_list is None:
            return
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
        return self.path

    def subdirs(self) -> list[Path]:
        """Return the sorted subdirectories in the current path."""
        path = self.mmif_dir / self.path
        subdirs = [Path(d.name) for d in [d for d in path.iterdir() if d.is_dir()]]
        return list(sorted(subdirs))

    def files(self) -> list[Path]:
        """Return the sorted files in the current path."""
        path = self.mmif_dir / self.path
        files = [p for p in path.iterdir() if p.is_file()]
        files = [Path(f.name) for f in files]
        return list(sorted(files))

    def parameter_file(self) -> Path | None:
        """Return the parameter file that goes with the current directory,
        of None if there is no such file."""
        #if len(self.path.parts) in (3, 6, 9, 12, 15, 18, 21):
        path_lenght = len(self.path.parts)
        if path_lenght > 0 and path_lenght % 3 ==0:
            return self.mmif_dir / self.path.parent / (self.path.name + '.json')
        else:
            return None

    def cd(self, path: str) -> str:
        """Change the current MMIF path. Assumes that the input was vetted by
        the Shell."""
        if path == '~':
            self.path = Path('.')
            return '~'
        elif path == '..':
            # TODO: also allow for ../.. and then do the right thing
            self.path = self.path.parent
            return str(self.path)
        else:
            rel_path = Path(self.cwd()) / path
            full_path = self.mmif_dir / rel_path
            if full_path.is_dir():
                self.path = rel_path
                return str(self.path)
            else:
                raise ShackError(f'Directory "{path}" does not exist')

    def register(self, url: str):
        api.run.register_app(url)

    def select_app(self, selection: str) -> bool:
        """Select an application if it is amongst the registered apps,
        return True or False depending on whether selection succeeded."""
        if selection in self.apps:
            self.app = api.run.ClamsApp(selection, self.apps[selection])
            return True
        return False

    def run_job(self, name: str):
        process_id = api.run.run_job(timestamp(), name, self)
        return process_id

    def reindex(self):
        """Recreate the MmifIndex. Should run this after jobs are completed."""
        self.mmif_index = MmifIndex(self)

    def prune(self):
        if str(self.path) in ('.', '~', ''):
            raise ShackError('Cannot delete the MMIF root directory')
        spath = StoragePath(self, str(self.cwd()))
        spath.rmtree()
        self.reindex()
        self.cd('..')

    def get_history(self):
        return [(n+1, command) for n, command in enumerate(self.history.data)]

    def get_settings(self):
        app = None if self.app is None else self.app.name
        assets_count = 0 if self.assets is None else len(self.assets)
        return [
            ('shack', self.location),
            ('assets', assets_count),
            ('sources', len(self.sources)),
            ('jobs', len(self._jobs)),
            ('path', str(self.path)),
            ('clams_app', app),
            ('parameters', self.params)]


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


class StoragePath():

    """Embeds a regular Path and provides some extra data and functionality relevant
    to the MMIF storage that the path is in."""

    def __init__(self, shack: ClamShack, path: str = ''):
        """Initialize an instance that has access to the ClamShacka Path and add some extra information to it. The path
        parameter contains the relative path from the mmif root directory or the
        full path including the Shack's mmif directory."""
        if str(path).startswith(str(shack.mmif_dir)):
            full_path = Path(path)
            rel_path = Path(*full_path.parts[len(shack.mmif_dir.parts):])
        else:
            full_path = Path(shack.mmif_dir) / path
            rel_path = Path(path)
        self.shack = shack
        self.mmif_dir = shack.mmif_dir
        self.full_path = full_path
        self.rel_path = rel_path
        self._name = self.rel_path.name

    def __str__(self):
        """String representation using the relative path."""
        return f'<StoragePath {self.shortname}>'

    def __len__(self):
        """Length of the full path."""
        return len(self.full_path.parts)

    @property
    def name(self):
        """The final component of the relative path, if any."""
        return self._name

    @property
    def stem(self):
        """The stem of the relative path, if any."""
        return self.rel_path.stem

    @property
    def shortname(self):
        """Shortened name of the full path."""
        return path_as_string(self.full_path)
    
    @property
    def shortrelname(self):
        """Shortened name of the relative path."""
        return path_as_string(self.rel_path)

    @property
    def parts(self):
        return self.full_path.parts

    def is_dir(self):
        return self.full_path.is_dir()

    def is_file(self):
        return self.full_path.is_file()

    def iterdir(self):
        return self.full_path.iterdir()

    def pp(self):
        print(f'\n{self}')
        print(f'  mmif_dir  = {self.mmif_dir}')
        print(f'  rel_path  = {self.rel_path}')
        print(f'  full_path = {self.full_path}\n')

    def ddir(self):
        paths = []
        depth = len(self) + 3
        prefix_length = len(self.mmif_dir.parts)
        for root, _, _ in self.full_path.walk():
            if len(root.parts) == depth:
                paths.append(
                    (Path(*root.parts[prefix_length:]), Path(*root.parts[-3:]) ))
        return paths

    def rmtree(self, indent=''):
        """Delete the path from the storage, if there is a sister path with the
        same name with a .json suffix, then delete that file as well."""
        shutil.rmtree(str(self.full_path))
        properties_file = StoragePath(
            self.shack, f'{str(self.full_path.parent)}/{self.name}.json')
        if properties_file.is_file():
            properties_file.unlink()

    def unlink(self):
        """Remove the file from the storage and from the index."""
        self.full_path.unlink()


class History:

    """Keep track of the command history for a ClamShack. Maintains an in-memory
    dictionary in addition to the history file."""
    
    # TODO: maybe put a cap on the size or only print the last 50 (unless a number
    # was given) or give warnings when the history becomes huge.
    
    def __init__(self, history_file: Path):
        """Initialize the history from a file."""
        self.path = history_file
        self.data = []
        self.index = {}
        self.size = 0
        with open(history_file) as fh:
            for line in fh:
                command = line.strip()
                self.size += 1
                self.data.append(command)
                self.index[self.size] = command

    def __len__(self):
        return self.size

    def __str__(self):
        return f'<History with {len(self)} elements>'

    def add(self, command: str):
        """Add a command to the history. This is called by the ClamShell which
        does some filtering of commands."""
        with open(self.path, 'a') as fh:
            fh.write(command + '\n')
        self.size += 1
        self.data.append(command)
        self.index[self.size] = command

    def reset(self):
        """Empty the history, both in-memory and on the disk."""
        self.data = []
        self.index ={}
        self.size = 0
        with open(self.path, 'w') as fh:
            fh.write('')


class MmifIndex:

    """Index of MMIF files in the Shack to support searching the MMIF storage. For
    now it is not much of an index but at least there is a dictionary of filenames
    mapped to path and a set of all directories with MMIF files.

    data: dict  -  { filename -> list of paths }
    dirs: set   -  directories inside of the mmif storage

    This index is not updated after new files are added. It should be recreated
    after a job has finished.

    On the wishlist is to use a database instead of an in-memory object. When that's
    the case it would be easy to let jobs updated the database. However, this is of
    low priority since we do not have to be too worried about scale.
    """

    def __init__(self, shack: ClamShack):
        self.shack = shack
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

    def enqueue(self, path):
        with open(self.shack.queue_file, 'a') as fh:
            fh.write(f'{str(path)}\n')

    def dequeue(self):
        """Check whether there is a queue (tested by checking the file size). If
        there is reset the queue and upate the index."""
        filesize = self.shack.queue_file.stat().st_size
        if filesize > 0:
            self.shack.queue_file.write_text('')
            self.shack.reindex()
        # Note: this was a more complicated and potentially more efficient way of
        # doing it but it was not quite right, perhaps revisit
        #     content = self.shack.queue_file.read_text()
        #     for line in content.split('\n'):
        #         if not line:
        #             continue
        #         p = Path(line)
        #         d1 = p.parent
        #         d2 = d1.parent
        #         d3 = d2.parent
        #         guid = p.stem
        #         for d in (d1, d2, d3):
        #             if d not in self.dirs:
        #                 #print(f'adding {path_as_string(d)}')
        #                 self.dirs.add(d)
        #         self.data.setdefault(guid, [])
        #         if d1 not in self.data[guid]:
        #             self.data.setdefault(guid, []).append(d1)
        #             #print(f'adding {guid}\n       {path_as_string(d1)}')
        #     self.shack.queue_file.write_text('')

    def search_assets(self, term: str) -> list:
        """Return a list of assets whose identifiers contain the term."""
        return [a for a in self.sources if term in str(a.name)]

    def search_mmif(self, term: str) -> dict:
        """Return dictionary of sources and the directories they occur in,
        where the sources contain the search term."""
        # TODO. Is this actually useful? If a MMIF file is in there as a source
        # it will also appear in every directory except for those cases when no
        # output was created.
        results = {}
        for name in sorted(self.data.keys()):
            if term in name:
                results[name] = self.data[name]
        return results

    def search_app(self, term: str) -> list:
        """Return a list of directories created by an app whose identifier
        contains the term."""
        results = []
        dirs = [d for d in self.dirs if len(d.parts) % 3 == 0]
        print(dirs)
        for directory in dirs:
            triples = path_as_tuples(directory)
            # try to match on the app part of the last triple in the path
            if triples and term in triples[-1][0]:
                results.append(directory)
        return results

    def search_params(self, settings: list) -> list[Path]:
        """Return a list of directories created with parameters that match the
        parameters in the settings list."""
        def match_parameters(params: list, params_file: Path) -> bool:
            with open(param_file) as fh:
                json_obj = json.load(fh)
                return all([match_parameter(p,v, json_obj) for p, v in params])
        def match_parameter(param: str, val: str, parameters: dict) -> bool:
            return param in parameters and parameters[param] == val
        params = [t.split('=') for t in settings]
        dirs = [d for d in self.dirs if len(d.parts) and len(d.parts) % 3 == 0]
        results = []
        for d in dirs:
            param_file = self.shack.mmif_dir / d.parent / f'{d.name}.json'
            if match_parameters(params, param_file):
                results.append(d)
        return results

    def remove_dir(self, path: StoragePath):
        """Remove the directory path from the self.dirs set."""
        #print('-D-', path_as_string(path.rel_path))
        self.dirs.remove(path.rel_path)

    def remove_file(self, path: StoragePath):
        """Remove the file path from all lists in the self.data dictionary."""
        #print('-F-', path.name)
        for fname in self.data:
            if fname == path.stem:
                paths = self.data[fname]
                new_paths = [p for p in paths if not path.rel_path == p]
                self.data[fname] = new_paths
        self.data = {k:v for k,v in self.data.items() if v}

    def pp(self):
        print(self)
        print('>>> dirs')
        for d in sorted(self.dirs):
            print(path_as_string(d))


class Shell(Cmd):

    """Shell for command-line access to the ClamShack."""

    intro = ('\nYou entered the CLAMS shell. Type "?" for a list of commands.\n')
    prompt = None

    # Hidden commands are not advertized to the user when they type 'help'
    hidden_commands = {'s', 't', 'u', 'v', 'w', 'x', 'y', 'z', 'nl', 'echo'}

    @classmethod
    def set_prompt(cls, shack: ClamShack):
        cls.prompt = f'🐚 ({shack.name}) '

    def __init__(self, clamshack: ClamShack):
        # TODO: this may be needed for some Pythn versions
        # TODO: sometimes this works and sometimes it does not, not sure why
        # completekey = '^I' if sys.platform == 'darwin' else 'tab'
        # super().__init__(completekey=completekey)
        super().__init__()
        self.shack = clamshack
        self.set_prompt(self.shack)
        # Each time we got a couple of directories from a search we save it so we can
        # use it in the goto command.
        self.saved_directories = {}
        # The session log stores commands used and indicates when errors occurred,
        # the errors list is for errors encountered during the current session.
        self.log = []
        self.errors = []

    def __str__(self):
        return f'<Shell on "{self.shack.name}">'

    def default(self, line):
        """This applies if no command was recognized."""
        if line == 'c':
            pass
        elif line in ("q", "EOF"):
            self.do_quit(line)
            return True
        elif line == 'h' or line.startswith('h '):
            self.do_history(f'{line[1:].strip()}')
        elif line.startswith('!'):
            # Mimicking the linux way to execute a previous command.
            n = line[1:]
            if n.isdigit():
                command = self.shack.history.index[int(n)]
                #console.print(Panel(f'{line} --> {command}'))
                print(command)
                self.cmdqueue.append(command)
        elif line == 'shack' or line.startswith('shack.'):
            # NOTE: why does this work now that the global variable is history?
            try:
                console.print(eval(f'self.{line}'))
            except Exception as e:
                console.print(e)
        elif line == 'shell' or line.startswith('shell.'):
            try:
                line = f'self{line[5:]}'
                console.print(eval(line))
            except Exception as e:
                console.print(e)
        elif line.startswith('p '):
            # This is not advertized but it is here to sneak in the possibility
            # to evaluate Python expressions.
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
        try:
            if not line.split()[0] in self.__class__.hidden_commands:
                if not line.startswith('!'):
                    self.shack.history.add(line)
                    self.log.append(f'COMMAND: {line}')
        except IndexError:
            pass
        return stop

    def onecmd(self, line):
        """Wrapping all single commands in some error handling that deals with any
        unexpected errors. Known errors and warnings should be dealt with directly
        in the do_x() methods themselves."""
        try:
            return super().onecmd(line)
        except Exception as e:
            warning(
                'An unexpected error occured, type "show error" to see the last'
                ' error that occurred')
            current_error = {'command': line, 'stacktrace': []}
            self.log.append(f'ERROR: {line}')
            for l in traceback.format_exception(e):
                current_error['stacktrace'].append(l)
            self.errors.append(current_error)
            with open(self.shack.error_file, 'a') as fh:
                fh.write(f'\n>>> ERROR: {line}\n\n')
                for l in traceback.format_exception(e):
                    fh.write(l)

    def emptyline(self):
        """Override repeating the last command."""
        pass

    def get_commands(self) -> list:
        funs = inspect.getmembers(self.__class__, predicate=inspect.isfunction)
        names = [name[3:] for name, method in funs if name .startswith('do_')]
        names = [n for n in names if not n in self.hidden_commands]
        return names

    ## Core actions

    def do_quit(self, arg):
        """Exit the CLAM Shack"""
        print(messages['bye'])
        return True

    def do_show(self, arg):
        if arg == 'error':
            if self.errors:
                console.print(f'\n ERROR ON COMMAND: {self.errors[-1]["command"]}\n')
                for line in self.errors[-1]['stacktrace']:
                    console.print(f' {line}', end='')
        elif arg == 'errors':
            for error in self.errors:
                console.print(f'\n ERROR ON COMMAND: {error["command"]}\n')
                for line in error['stacktrace']:
                    console.print(f' {line}', end='')
        else:
            table = Table(show_header=False)
            for name, value in self.shack.get_settings():
                #console.print(f' {name:10}  =  {value}')
                if name == 'path':
                    table.add_row(name, path_as_string(Path(value)))
                else:
                    table.add_row(name, str(value))
            console.print(Panel("Shack settings and information"))
            console.print(table)

    def do_history(self, arg):
        if arg == 'reset':
            self.shack.history.reset()
            console.print('Command history was reset')
        else:
            console.print(Panel(
                'Command history for this shack, use !INT to rerun a command'))
            for n, command in self.shack.get_history():
                 print(f' {n:2d}  {command}')

    def do_search(self, arg):
        if not arg:
            warning('No search parameters given')
            return
        search_type, *args = arg.split()
        if search_type == 'assets':
            results = self.shack.search(term=args[0], mode='assets')
            console.print(Panel(f'Assets matching "{args[0]}"'))
            for r in results:
                print(f' {r.name}')
        elif search_type == 'mmif':
            results = self.shack.search(term=args[0], mode='mmif')
            console.print(Panel(f'MMIF files matching "{args[0]}"'
                                 ' and the directories where they occur'))
            for name in results:
                print(' ' + name)
                for p in results[name]:
                    print('    ', path_as_string(p.parent))
        elif search_type == 'app':
            results = self.shack.search(term=args[0], mode='app')
            console.print(Panel(f'Directories created by app matching "{args[0]}"'))
            self.saved_directories = {}
            for n, result in enumerate(results):
                self.saved_directories[n] = result
                print(f' {n:2d}: {path_as_string(result)}')
        elif search_type == 'params':
            try:
                results = self.shack.search(term=args, mode='params')
                search_params = ' & '.join(args)
                console.print(Panel(f'Directories created with parameter {search_params}'))
                self.saved_directories = {}
                for n, result in enumerate(results):
                    self.saved_directories[n] = result
                    print(f' {n:2d}: {path_as_string(result)}')
            except Exception as e:
                warning(e)
        else:
            warning(f'Cannot search for "{arg}", use "assets", "mmif" or "app"')
            return

    def do_apps(self, arg):
        app_dict = dict(enumerate(self.shack.app_names))
        if not arg:
            console.print(Panel('Registered CLAMS Apps'))
            for key in sorted(app_dict):
                console.print(f' {key}: {app_dict[key]}')
        else:
            selection = arg
            if selection.isnumeric():
                selection = app_dict.get(int(selection))
            succeeded = self.shack.select_app(selection)
            if succeeded:
                dribble(f'Selected {selection}')
            else:
                warning(f'Selection does not exist')

    def do_register(self, arg):
        self.shack.register(arg)

    def do_jobs(self, arg):
        if arg:
            try:
                job = self.shack.jobs[arg]
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
            for job in sorted(self.shack.jobs.values(), key=lambda x: x.started, reverse=False):
                elapsed = job.time_elapsed()
                table.add_row(job.name, job.app, str(len(job.guids)), elapsed)
            console.print(table)

    def do_params(self, arg):
        args = arg.split()
        if len(args) >= 1:
            if args[0] == 'reset':
                self.shack.params_file = None
                self.shack.params = {}
            # loading a file with "params @FILENAME"
            elif args[0].startswith('@'):
                fname = args[0][1:].strip()
                try:
                    params = load_json(fname)
                    self.shack.params = params
                    self.shack.params_file = fname
                except FileNotFoundError:
                    print(f'There is no file "{fname}"')
                except json.decoder.JSONDecodeError:
                    print(f'No valid JSON in {fname}')
            # setting a parameter with "params PARAM=VALUE"
            elif '=' in args[0]:
                param, value = args[0].split('=', 1)
                self.shack.add_parameter(param, value)
        console.print(self.shack.params)

    def do_run(self, arg):
        if not arg:
            warning('You must provide a name for the job.')
            return
        if self.shack.app is None:
            warning('You must select a CLAMS app.')
            return
        if arg in self.shack.jobs:
            warning('A job with that name already exists.')
            return
        if self.shack.cwd() != Path('.'):
            files = [Path(f.name) for f in self.shack.files() if f.suffix == '.mmif']
            if not files:
                print('Nothing to do, there are no MMIF files in the current path')
                return
        process_id = self.shack.run_job(arg)
        console.print(Panel('Started job'))
        dribble(f'  name   = {arg}')
        dribble(f'  path   = {path_as_string(self.shack.cwd())}')
        dribble(f'  app    = {self.shack.app}')
        dribble(f'  params = {self.shack.params}')
        dribble(f'  pid    = {process_id}')

    def do_index(self, arg):
        self.shack.reindex()
        print('Recreated the MMIF Index')

    def do_source(self, arg):
        """Loads a file of commands and then run them. The file of commands has to
        be in the same format as the file that is created by the "history save"
        command."""
        # TODO: check the source file so that it only has one run command
        if arg:
            script_path = Path(arg)
            if script_path.is_file():
                commands = []
                for line in script_path.read_text().split('\n'):
                    if line.strip() and not line.strip().startswith('#'):
                        commands.append(line.strip())
                for c in commands:
                    self.cmdqueue.append(f'echo {c}')
                    self.cmdqueue.append(c)
            else:
                warning(f'Script file "{arg}" does not exist')
        else:
            warning("You need to specify a script to source.")

    def do_pwd(self, arg):
        path = self.shack.cwd()
        if str(path) in ('', '.'):
            print('.')
        else:
            print('', path_as_string(path))

    def do_dirs(self, arg):
        if arg == '-s':
            if self.saved_directories:
                console.print(Panel(f'Last directories saved (using full storage path)'))
                for n, path in self.saved_directories.items():
                    print(f' {n:2d}: {path_as_string(path)}')
            else:
                print('\n No directories were saved.')
        elif arg == '-d':
            spath = StoragePath(self.shack, self.shack.path)
            dirs = spath.ddir()
            p = path_as_string(self.shack.cwd())
            console.print(Panel(f'Expanded sub directories at "{p}"'))
            self.saved_directories = {}
            for n, (d1, d2) in enumerate(dirs):
                self.saved_directories[n] = d1
                print(f' {n:2d}: {path_as_string(d2)}')
        else:
            p = path_as_string(self.shack.cwd())
            console.print(Panel(f'Sub directories at "{p}"'))
            for n, d in enumerate(self.shack.subdirs()):
                print(f' {n:2d}: {str(d)}')

    def do_files(self, arg):
        console.print(Panel(f'MMIF files at "{path_as_string(self.shack.cwd())}"'))
        for n, f in enumerate(self.shack.files()):
            print(f' {n}: {str(f)}')

    def do_cd(self, arg):
        # first translate an index from the dir command into a sub directory
        subdirs = { n: str(p) for n, p in enumerate(self.shack.subdirs()) }
        if arg.isnumeric() and int(arg) in subdirs:
            arg = subdirs[int(arg)]
        try:
            new_path = self.shack.cd(arg)
            print(path_as_string(Path(new_path)))
        except ShackError as e:
            warning(e)

    def do_home(self, arg):
        self.do_cd('~')

    def do_up(self, arg):
        try:
            repetitions = int(arg) if arg else 1
            for i in range(repetitions):
                self.shack.cd('..')
            print(path_as_string(self.shack.path))
        except ValueError:
            warning('The argument can only be an integer')

    def do_tree(self, arg):
        args = arg.split()
        full = True if '-f' in args else False
        parameters = True if '-p' in args else False
        if '-v' in args:
            full = True
            parameters = True
        prefix = self.shack.mmif_dir
        t = get_tree(self.shack.mmif_dir / self.shack.path, prefix=prefix, full=full)
        console.print(Panel('MMIF File tree'))
        self.do_nl('')
        console.print(t)
        if parameters:
            parameter_file = self.shack.parameter_file()
            if parameter_file is not None:
                print()
                #console.print(Panel(path_as_string(parameter_file)))
                console.print(Panel('Parameters'))
                console.print(parameter_file.read_text())

    def do_goto(self, arg):
        try:
            self.shack.cd('~')
            directory = self.saved_directories.get(int(arg))
            if directory is None:
                warning('There is no saved directory at that index')
                return
            self.shack.cd(str(directory))
            #print(path_as_string(directory))
            self.do_tree('-p')
        except ValueError:
            warning('goto command requires an integer')

    def do_prune(self, arg):
        try:
            text = Text(f'\n Deleting {path_as_string(self.shack.cwd())}\n')
            text.stylize("bold red")
            console.print(text)
            answer = input(' Continue? (y/n) ')
            if answer == 'y':
                self.shack.prune()
            console.print(Panel(f' Deleted {path_as_string(self.shack.cwd())}'))
        except ShackError as e:
            warning(e)

    def do_view(self, arg):
        saved_path = self.shack.path
        if saved_path == '.':
            saved_path = '~'
        self.do_goto(arg)
        self.shack.cd('~')
        #self.do_view(arg)
        self.shack.cd(str(saved_path))
        
    def do_describe(self, arg):
        if not arg.isdigit():
            warning('The argument must be an integer')
            return
        full_path = self.shack.mmif_dir / self.shack.path
        for n, f in enumerate(self.shack.files()):
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
            names = self.get_commands()
            console.print(Panel('Available commands'))
            for cmd in names:
                print_command(' ' + cmd)
            console.print('\n Type "help <command>" for help on a command')
        elif arg in COMMANDS:
            print_help(*COMMANDS.get(arg))
        else:
            print(f'No help available for {arg}')

    def do_help_all(self, arg):
        names = self.get_commands()
        console.print(Panel('Available commands'))
        for cmd in names:
            print_help(*COMMANDS.get(cmd,('','')))

    def do_echo(self, arg):
        """Just a utility method to use in scripts, may be deprecated."""
        print(f'>>> {arg}')

    def do_nl(self, arg):
        # Utility command for when adding multiple commands to the queue, may be
        # deprecated.
        print()

    ## Undocumented actions for debugging and development

    def do_s(self, arg):
        self.cmdqueue.append('source example-script.txt')

    def do_t(self, arg):
        #self.cmdqueue.append('search assets f55')
        #self.cmdqueue.append('search mmif f55')
        #self.cmdqueue.append('search app captioner')
        self.cmdqueue.append('search app spac')
        #self.cmdqueue.append('view 0')
        self.cmdqueue.append('goto 0')
        #self.cmdqueue.append('search params pretty=True')
        #self.cmdqueue.append('search params pretty=True threshold=3')

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
        self.cmdqueue.append('show')

    def do_y(self, arg):
        self.cmdqueue.append('register 127.0.0.1:5001')
        self.cmdqueue.append('apps')

    def do_z(self, arg):
        #self.cmdqueue.append('ddirs')
        #self.cmdqueue.append('cd swt-detection/v8.6/d41d8cd98f00b204e9800998ecf8427e/smolvlm2-captioner/v1.0/d41d8cd98f00b204e9800998ecf8427e')
        self.cmdqueue.append('source s.txt')
        #self.cmdqueue.append('run t1')
        #self.cmdqueue.append('search app spacy')

    def do_w(self, arg):
        self.cmdqueue.append('source s2.txt')


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
    Shell(ClamShack(args.shack, args.assets)).cmdloop()
