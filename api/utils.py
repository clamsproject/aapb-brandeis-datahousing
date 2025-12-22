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

from summarizer import Summary


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


def hash_from_dictionary(parameters: dict):
    param_list = ['='.join(pair) for pair in parameters.items()]
    param_list.sort()
    param_string = ','.join(param_list)
    param_hash = hashlib.md5(param_string.encode('utf-8')).hexdigest()
    #print('...', param_string)
    #print('...', param_hash)
    return param_hash


def strip_prefix(prefix: str, path: Path):
    return Path(*path.parts[len(Path(prefix).parts):])


class StorageUnit:

    """Keeps track of all information for a MMIF file on the storage server. This
    includes summary and description files, as well as various information from
    higher up the path including app parameter files."""

    def __init__(self, storage_dir: str, path: Path):
        self.storage = Path(storage_dir)
        self.path = path
        self.summary = path.parent / f'{path.stem}.summ.json'
        self.summary_error = False
        self.description = path.parent / f'{path.stem}.desc.json'

    def summary_exists(self):
        return self.summary.exists()

    def description_exists(self):
        return self.description.exists()

    def relative_path(self):
        """The relative path to the parent of the MMIF file."""
        return strip_prefix(self.storage, self.path.parent)

    def parameters(self) -> list:
        """A list of app-parameter pairs taken from all the apps involved in
        creating the MMIF file."""
        parameters = []
        for p in reversed(self.path.parents):
            if re.match("[0-9a-z]{32}", p.stem):
                param_file = Path(p.parent) / f'{p.stem}.json'
                app_path = Path(*p.parts[-3:-1])
                param_content = param_file.read_text()
                parameters.append((app_path, param_content))
        return parameters

    def mmif_content(self) -> str:
        """The content of the MMIF file as a prettified string."""
        with open(self.path, 'r') as fh:
            mmif_content = json.dumps(json.loads(fh.read()), indent=2)
            return mmif_content

    def mmif_size(self):
        return self.path.stat().st_size

    def mmif_size_as_string(self):
        return f'{self.mmif_size():,d}'

    def summary_size(self):
        return self.summary.stat().st_size

    def summary_size_as_string(self):
        return f'{self.summary.stat().st_size:,d}'
        # The weird thing is that using the following instead gives errors
        #    size = self.summary_size()
        #    return f'{size:,d}'
        # It looks like self is not an instance of StorageUnit but None. I am
        # totally at a loss to why that would be.

    def summary_content(self) -> str:
        """Get the summary of the MMIF file. In case there is no summary, create
        it first."""
        if not self.summary_exists():
            try:
                summary_obj = Summary(self.path)
                summary_obj.report(outfile=self.summary, full=True)
            except Exception as e:
                self.summary_error = True
        if self.summary_error:
            return '{ "message": "error when creating summary"}'
        else:
            return self.summary.read_text()

    def description_content(self) -> str:
        """Get the description of the MMIF file. In case there is no description,
        create it first."""
        if not self.description_exists():
            desc = describe_single_mmif(self.path)
            with open(str(self.description), 'w') as fh:
                fh.write(json.dumps(desc, indent=2))
        return self.description.read_text()

    def pp(self):
        print(f'\n<{self.path.name}>')
        print(f'    stor = {self.storage}')
        print(f'    mmif = {strip_prefix(self.storage, self.path)}')
        print(f'    summ = {strip_prefix(self.storage, self.summary)}')
        print(f'    desc = {strip_prefix(self.storage, self.description)}\n')
