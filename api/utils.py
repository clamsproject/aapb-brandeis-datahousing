import re
import sys
import json
import hashlib
import tempfile
from pathlib import Path
from types import ModuleType, FunctionType
from gc import get_referents

from mmif.utils.cli import describe
from mmif.utils.workflow_helper import describe_single_mmif

from mmif.utils.summarizer import Summary


def getsize(obj):
    # Based on an answer from Aaron Hall in
    # https://stackoverflow.com/questions/449560/how-do-i-determine-the-size-of-an-object-in-python
    BLACKLIST = type, ModuleType, FunctionType
    if isinstance(obj, BLACKLIST):
        raise TypeError('getsize() does not take argument of type: '+ str(type(obj)))
    seen_ids = set()
    size = 0
    objects = [obj]
    while objects:
        need_referents = []
        for obj in objects:
            if not isinstance(obj, BLACKLIST) and id(obj) not in seen_ids:
                seen_ids.add(id(obj))
                size += sys.getsizeof(obj)
                need_referents.append(obj)
        objects = get_referents(*need_referents)
    return size


def hash_from_dictionary(parameters: dict) -> str:
    param_list = ['='.join(pair) for pair in parameters.items()]
    param_list.sort()
    param_string = ','.join(param_list)
    param_hash = hashlib.md5(param_string.encode('utf-8')).hexdigest()
    #print('...', param_string)
    #print('...', param_hash)
    return param_hash


def strip_prefix(prefix: str, path: Path) -> Path:
    return Path(*path.parts[len(Path(prefix).parts):])


class ServerDirectory:

    """Class for a directory on the storage server. Includes functionality to
    navigate down the storage server."""

    def __init__(self, storage_dir: str, path: str):
        self.base = Path(storage_dir)
        # path is the relative path from the storage directory
        # fullpath is the absolute path on the storage server
        if path is None:
            self.path = Path('.')
            self.fullpath = Path(storage_dir)
        else:
            self.path = Path(path)
            self.fullpath = Path(storage_dir) / path

    def __str__(self):
        return f'<ServerDirectory "{self.path}">'

    def path_for_display(self) -> str:
        return ' > '.join(self.path.parts)

    def strip_prefix(self, path: Path) -> Path:
        return Path(*path.parts[len(self.base.parts):])

    def directories(self) -> list:
        """Return a list of Paths, one for each subdirectory."""
        dirs = [sub for sub in self.fullpath.iterdir() if sub.is_dir()]
        return list(sorted([self.strip_prefix(d) for d in dirs]))

    def files(self):
        # At the moment the template distinguishes between property files and MMIF 
        # simply by using the extension. There may be a use case for doing it here
        # and use somehwhat more sophisticated code like using a regular expression
        # to get the property file: re.match("[0-9a-z]{32}\.json", path.name"
        def is_derived(path: Path):
            return path.name.endswith('.summ.json') or path.name.endswith('.desc.json')
        files = [sub for sub in self.fullpath.iterdir() if sub.is_file()]
        files = [f for f in files if not is_derived(f)]
        return list(sorted([self.strip_prefix(f) for f in files]))

    def pp(self):
        print(self)
        print(f'    fullpath = {self.fullpath}')
        print(f'    parts    = {self.path_for_display()}')


class ParameterFile:

    def __init__(self, storage_dir: str, path: str):
        self.base = Path(storage_dir)
        # path is the relative path from the storage directory
        # fullpath is the absolute path on the storage server
        self.path = Path(path)
        self.fullpath = Path(storage_dir) / path
        self.parameters = json.dumps(json.loads(self.fullpath.read_text()), indent=2)
        self.size = self.fullpath.stat().st_size

    def __str__(self):
        return f'<ParameterFile size={self.size} "{self.path}">'


class MmifFile:

    """Keeps track of all information for a MMIF file on the storage server. This
    includes summary and description files, as well as various information from
    higher up the path including app parameter files."""

    def __init__(self, storage_dir: str, path: Path):
        #print('>>>', storage_dir)
        #print('>>>', path)
        self.storage = Path(storage_dir)
        self.path = path
        self.fullpath = Path(storage_dir) / path
        #print('>>>', self.fullpath)
        self.summary = self.fullpath.parent / f'{self.fullpath.stem}.summ.json'
        self.summary_error = False
        self.description = self.fullpath.parent / f'{self.fullpath.stem}.desc.json'
        self.pp()

    def summary_exists(self):
        return self.summary.exists()

    def description_exists(self):
        return self.description.exists()

    def relative_path(self) -> Path:
        """The relative path to the parent of the MMIF file."""
        return strip_prefix(self.storage, self.path.parent)

    def parameters(self) -> list:
        """A list of app-parameter pairs taken from all the apps involved in
        creating the MMIF file."""
        parameters = []
        for p in reversed(self.path.parents):
            if re.match("[0-9a-z]{32}", p.stem):
                param_file = self.storage / p.parent / f'{p.stem}.json'
                app_path = Path(*p.parts[-3:-1])
                param_content = param_file.read_text()
                parameters.append((app_path, param_content))
        return parameters

    def mmif_content(self) -> str:
        """The content of the MMIF file as a prettified string."""
        with open(self.fullpath, 'r') as fh:
            mmif_content = json.dumps(json.loads(fh.read()), indent=2)
            return mmif_content

    def mmif_size(self):
        return self.fullpath.stat().st_size

    def summary_size(self):
        return self.summary.stat().st_size

    def summary_size_as_string(self):
        return f'{self.summary.stat().st_size:,d}'
        # The weird thing is that using the following instead gives errors
        #    size = self.summary_size()
        #    return f'{size:,d}'
        # It looks like self is not an instance of MmifFile but None. I am
        # totally at a loss to why that would be, but this may not be the case
        # anymore now that summaries are generated earlier.

    def summary_content(self) -> str:
        """Get the summary of the MMIF file."""
        if self.summary_error:
            return '{ "message": "error when creating summary"}'
        else:
            return self.summary.read_text()

    def create_summary(self):
        if self.summary.exists():
            # TODO: maybe add functionality somewhere to recreate a summary
            return
        try:
            summary_obj = Summary(self.fullpath)
            summary_obj.report(outfile=self.summary)
        except Exception as e:
            self.summary_error = True

    def description_content(self) -> str:
        """Get the description of the MMIF file. In case there is no description,
        create it first."""
        if not self.description_exists():
            desc = describe_single_mmif(self.fullpath)
            with open(str(self.description), 'w') as fh:
                fh.write(json.dumps(desc, indent=2))
        return self.description.read_text()

    def pp(self):
        print(f'\n<{self.path.name}>')
        print(f'    base = {self.storage}')
        print(f'    mmif = {strip_prefix(self.storage, self.fullpath)}')
        print(f'    summ = {strip_prefix(self.storage, self.summary)}')
        print(f'    desc = {strip_prefix(self.storage, self.description)}\n')
