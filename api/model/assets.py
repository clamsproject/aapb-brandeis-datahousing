"""

This module manages the assets directory tree.

The top-level subdirectories in the directory tree indicate asset types, the 
structure below that level can have any shape. For AAPB data the current tree
looks like this (some subdirectories were deleted for readability):

.
├── text
│   ├── NJN_Network
│   ├── NewsHour
│   │   ├── WN0005
│   │   └── WN0020
│   ├── Peabody
│   ├── great_depression
│   ├── sonyids_connecticut_pb_20180423101623
│   └── sonyids_newjerseynetwork_20180423192048
└── video
    ├── NJN_Network
    ├── NewsHour
    │   ├── WN0005
    │   └── WN0020
    ├── Peabody
    ├── great_depression
    ├── sonyids_connecticut_pb_20180423101623
    └── sonyids_newjerseynetwork_20180423192048

The leave nodes are all files of the type indicated by the top-level element
of the path. Names of files are unique to the filetype.

File paths are stored in a database for quick retrieval.

At the moment, all this does is search the entire directory if a database
search was not succesful.

"""

# TODO: add upload and download functionality
# TODO: make sure that uploads update the database
# TODO: the database is now in the api directory perhaps move it to ASSET_DIR


from pathlib import Path

from api import ASSET_DIR
from api.model import database as db


# Asset file types
file_types = [
    ('text', ['.vtt', '.txt', '.srt', '.json']),
    ('markup', ['.xml']),
    ('image', ['.png', '.jpeg', '.jpg']),
    ('audio', ['.mp3', '.wav']),
    ('video', ['.mp4', '.mov', 'webm', 'mkv'])]


file_types_idx = {}
for file_type, extensions in file_types:
    for extension in extensions:
        file_types_idx[extension] = file_type


def check_symlink(fpath):
    """checks if a file is a symlink"""
    if not fpath.exists() or not fpath.is_file():
        return False
    if fpath.is_symlink():
        return True
    if any(p.is_symlink() for p in fpath.parents):
        return True
    return False


def check_asset_dir():
    """
    Validates ASSET_DIR and warns if it's a symlink or contains symlinks.
    Returns the resolved real path if ASSET_DIR is a symlink, otherwise returns the original path.
    """
    if not ASSET_DIR:
        raise RuntimeError("ASSET_DIR is not set in environment variables")
    
    sdir = Path(ASSET_DIR)
    if not sdir.exists():
        raise RuntimeError(f"ASSET_DIR does not exist: {ASSET_DIR}")
    
    if not sdir.is_dir():
        raise RuntimeError(f"ASSET_DIR is not a directory: {ASSET_DIR}")
    
    # Check if ASSET_DIR itself is a symlink
    if sdir.is_symlink():
        real_path = sdir.resolve()
        print(f"WARNING: ASSET_DIR is a symlink: {ASSET_DIR}")
        print(f"WARNING: Resolved to real path: {real_path}")
        print(f"WARNING: For proper functionality, consider using the real path in ASSET_DIR")
        return real_path
    
    # Check if any parent directory is a symlink
    for parent in sdir.parents:
        if parent.is_symlink():
            real_path = sdir.resolve()
            print(f"WARNING: ASSET_DIR contains a symlinked parent directory: {parent}")
            print(f"WARNING: Resolved ASSET_DIR to real path: {real_path}")
            print(f"WARNING: For proper functionality, consider using the real path in ASSET_DIR")
            return real_path
    
    return sdir


def directory_search(guid):
    """returns the locations of all files in the ASSET_DIR that begin with the
    given guid"""
    paths = []
    for file in Path(ASSET_DIR).glob("**/*"):
        if check_symlink(file):
            continue
        if guid in file.stem:
            paths.append(file)
    return paths


def file_typer(path):
    """determines the file type based on its extension"""
    return file_types_idx.get(path.suffix, 'other')


def aapb_generate(guid, extension):
    """generates a file from AAPB given a guid and file type, for future use, currently NOT IN USE"""
    # TODO: needs to be updated with AAPB API
    root = Path(ASSET_DIR)
    dir = root.joinpath(DOWNLOAD_DIR)
    if not dir.is_dir():
        dir.mkdir()
    filename = dir.joinpath(guid + extension)
    filename.touch()
    return filename


def search_assets(guid, file_type=None):
    if file_type is None:
        file_type = []
    paths = db.database_search(guid, file_type)
    # TODO (marc @ 12/12/25): doing a full directory search each time you do not find
    # results in the database, this is not horribly time consuming at the moment (on my
    # desktop it takes about two seconds when you have 16K files), but this needs to be
    # revisited when the number of assets gets much higher.
    if len(paths) == 0:
        # making sure the paths are strings, to match the paths from the database search
        paths = [str(p) for p in directory_search(guid)]
        # NOTE: disabling this for now because in some cases the update still results
        # in a fulll directory scan
        #if len(results) > 0:
        #    for result in results:
        #        insert_into_db(connection, guid, result)
        #    paths = database_search(connection, guid, file_type)
    return paths
