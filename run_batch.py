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

    jobs_file = Path(args.location) / 'jobs' / args.name

    ## Get a ClamShack and set up the app and the batch
    shack = ClamShack(args.location, None)
    shack.batch = args.batch
    shack.app = ClamsApp(args.app_name, args.app_url)

    ## Get the input to run on, either the sources or the result of previous
    ## processing, for now only deals with the default batch
    if args.path == '.':
        in_files = shack.sources
    else:
        p = shack.mmif_dir / shack.cwd() / args.path
        in_files = [f for f in p.iterdir() if f.is_file() and f.suffix == '.mmif']

    ## Run all input through the app
    for source in in_files:
        t0 = time.time()
        try:
            mmif_in = Mmif(source.read_text())
            mmif_out = shack.app.run(mmif_in, args.params)
            serialized_mmif = mmif_out.serialize(pretty=True)
            with open(source.name, 'w') as fh:
                fh.write(serialized_mmif)
            path = upload_mmif(serialized_mmif, root=shack.mmif_dir)
            message = 'SUCCES'
        except StorageWarning as e:
            message = f'{e}'
        except Exception as e:
            message = f'ERROR: {e}'
            raise e
        time_elapsed = time.time() - t0
        with open(jobs_file, 'a') as fh:
            fh.write(f'GUID\t{source.stem}\t{time_elapsed:2.4f}\t{message}\n')
    with open(jobs_file, 'a') as fh:
        fh.write(f'DONE\t{timestamp()}\n')


def arg_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument('name')
    parser.add_argument('--location')
    parser.add_argument('--path')
    parser.add_argument('--batch', default=None)
    parser.add_argument('--app-name', default=None)
    parser.add_argument('--app-url', default=None)
    parser.add_argument('--params', default={})
    return parser



if __name__ == '__main__':

    args = arg_parser().parse_args()
    main(args)
