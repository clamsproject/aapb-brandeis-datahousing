import json
import shutil
from datetime import datetime
from pathlib import Path
from collections import defaultdict

import api.run

from api.cli_utils import timestamp, path_as_string, path_as_tuples


class ClamShack:

    """
    Instances of this class keep track of all information like location, current
    path in the shack and others. They are also the entry point for any changes
    made to the shack, like registering CLAMS apps and running jobs.
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
    def storage_path(self):
        return StoragePath(self, self.path)

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



class ShackError(Exception): pass


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



class Assets:

    """Keeps track of the asset files and the MMIF source files created for those
    assets. Includes the root instance variable which is the lowest directory that
    contains all assets."""

    #def __init__(self, shack: ClamShack):
    def __init__(self, shack: 'ClamShack'):
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

    def __init__(self, shack: 'ClamShack', path: str = ''):
        """Initialize an instance that has access to the ClamShack Path and add
        some extra information to it. The path parameter contains the relative
        path from the mmif root directory or the full path including the Shack's
        mmif directory."""
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
        return f'<StoragePath "{self.shortname}">'

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

    #def __init__(self, shack: ClamShack):
    def __init__(self, shack: 'ClamShack'):
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




class Job:

    # TODO: 
    # - a job should know what directory it is writing too
    #   (you can use the new peek functionality for that)
    # - add a variable named status with the following possible values:
    #   running, aborted, failed, finished and maybe some more
    #   (for running a check whether there is a process id that seems to 
    #   be a clamshell job, if not you have failed, aborted is for when the
    #   user aborts the job; i fpossible update the finished value)
    # - allow deleting a job (with option to remove associated files?)

    def __init__(self, path: Path):
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

    def info(self) -> list:
        return [
            ('app', self.app),
            ('command', ' '.join(self.command)),
            ('pid', self.pid),
            ('guids', str(len(self.guids))),
            ('started', str(self.started)),
            ('time elapsed', str(self.time_elapsed()))]

    def info_guids(self) -> list:
        info = []
        for guid, t, result in self.guids:
            info.append((guid, t, result))
        return info

