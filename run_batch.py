import json
import time
import argparse
from pathlib import Path

from rich.console import Console

from mmif import Mmif

import api
from api import run
from api.cli import ClamShack, timestamp
from api.model.storage import upload_mmif


console = Console()


def main(args):

    jobs_file = Path(args.location) / 'jobs' / args.name

    ## Get a ClamShack and set the app and the batch
    shack = ClamShack(args.location)
    shack.app = (args.app, shack.apps[args.app])
    shack.batch = args.batch

    ## Get the input to run on, for now only deals with the default batch, also
    ## need to deal with non-source input.
    if args.path == '.':
        in_files = shack.sources
    else:
        p = shack.mmif_dir / shack.cwd() / args.path
        in_files = [f for f in p.iterdir()]

    ## Run all sources through the app, for now just running the local mocked apps
    for source in in_files:
        t0 = time.time()
        try:
            mmif_in = Mmif(source.read_text())
            mmif_out = shack.app[1](mmif_in, json.loads(args.params))
            serialized_mmif = mmif_out.serialize(pretty=True)
            path = upload_mmif(serialized_mmif, root=shack.mmif_dir)
            message = 'SUCCES'
            #break
        except Exception as e:
            message = f'ERROR: {e}'
        time_elapsed = time.time() - t0
        with open(jobs_file, 'a') as fh:
            fh.write(f'GUID\t{source.stem}\t{time_elapsed:2.4f}\t{message}\n')
        #break
    with open(jobs_file, 'a') as fh:
        fh.write(f'DONE\t{timestamp()}\n')


def arg_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument('name')
    parser.add_argument('--location')
    parser.add_argument('--path')
    parser.add_argument('--batch', default=None)
    parser.add_argument('--app', default=None)
    parser.add_argument('--params', default={})
    return parser



if __name__ == '__main__':

    args = arg_parser().parse_args()
    main(args)
