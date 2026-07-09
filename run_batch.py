import json
import time
import requests
import argparse
from pathlib import Path

from mmif import Mmif

import api
from api.cli import ClamShack, timestamp
from api.model.storage import upload_mmif
from api.run import ClamsApp
from api.errors import StorageWarning


def main(args):
    """Set up a ClamShack instance, determine the input and run the selected app
    on all the input files."""
    jobs_file = Path(args.location) / 'jobs' / f'{args.name}.txt'
    print('>>>', jobs_file)
    shack = ClamShack(args.location, None)
    shack.app = ClamsApp(args.app_name, args.app_url)
    in_files = get_input_files(shack, args.path)
    for source in in_files:
        #print('>>>', source)
        t0 = time.time()
        try:
            mmif_in = Mmif(source.read_text())
            mmif_out = shack.app.run(mmif_in, args.params)
            serialized_mmif = mmif_out.serialize(pretty=True)
            #with open(source.name, 'w') as fh:
            #    fh.write(serialized_mmif)
            path = upload_mmif(serialized_mmif, root=shack.mmif_dir)
            message = 'SUCCES'
        except StorageWarning as e:
            message = f'{e}'
        except Exception as e:
            message = f'ERROR: {e}'
            raise e
        time_elapsed = time.time() - t0
        with open(jobs_file, 'a') as fh:
            #print(f'--- appending {source.stem} to {jobs_file}')
            fh.write(f'GUID\t{source.stem}\t{time_elapsed:2.4f}\t{message}\n')
        #break
    print('>>> done looping')
    with open(jobs_file, 'a') as fh:

        fh.write(f'DONE\t{timestamp()}\n')
    

def get_input_files(shack: ClamShack, path: str) -> list:
    """Get the input to run on, either the sources or the MMIF result from
    previous processing."""
    if path == '.':
        return shack.sources
    else:
        p = shack.mmif_dir / shack.cwd() / args.path
        return [f for f in p.iterdir() if f.is_file() and f.suffix == '.mmif']


def arg_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument('name', help='the name of the job')
    parser.add_argument('--location', help='location of the shack')
    parser.add_argument('--path', help='path in the shack\'s MMIF storage')
    parser.add_argument('--app-name', default=None, help='name of the app')
    parser.add_argument('--app-url', default=None, help='URL of the app')
    parser.add_argument('--params', default={}, help='parameters or parameter file')
    return parser



if __name__ == '__main__':

    args = arg_parser().parse_args()
    main(args)
