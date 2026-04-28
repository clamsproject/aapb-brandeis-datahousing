import time
import argparse
from pathlib import Path

from mmif import Mmif

from api import run
from api.cli import ClamShack, timestamp
from api.model.storage import upload_mmif


def main(args):

    print('>>>', args)

    jobs_file = Path(args.location) / 'jobs' / args.name

    ## Get a ClamShack and set the app and the batch

    shack = ClamShack(args.location)
    shack.app = (args.app, shack.apps[args.app])
    shack.batch = args.batch

    print('>>>', shack)
    #print('>>>', shack.app)

    ## Get the sources to run on

    sources = []
    if args.batch == 'default':
        sources = shack.sources

    ## Start a process and get its pid
    ## for now just running the local stuff

    for source in sources:
        t0 = time.time()
        try:
            mmif_in = Mmif(source.read_text())
            mmif_out = shack.app[1](mmif_in, {})
            #upload_mmif(str(mmif_out))
            message = 'SUCCES'
        except Exception as e:
            message = f'ERROR: {e}'
        time_elapsed = time.time() - t0
        with open(jobs_file, 'a') as fh:
            fh.write(f'GUID\t{source.stem}\t{time_elapsed:2.4f}\t{message}\n')

    time.sleep(1)
    with open(jobs_file, 'a') as fh:
        fh.write(f'DONE\t{timestamp()}\n')

    '''
    t0 = time.time()
    process = subprocess.Popen(['python', 'api/run/app.py', '--job', '--batch', batch])
    print(f'-- process    = {type(process)}')
    print(f'-- process id = {process.pid}')
    for i in range(3):
        time.sleep(1)
        return_code = process.poll()
        print(psutil.pid_exists(process.pid))
        subp = subprocess.Popen(['ps', '-p', f'{process.pid}'])
        print(process.poll())
    time.sleep(1)
    '''


def parse_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument('name')
    parser.add_argument('-l', '--location')
    parser.add_argument('-b', '--batch', default=None)
    parser.add_argument('-a', '--app', default=None)
    return parser.parse_args()



if __name__ == '__main__':

    args = parse_arguments()
    main(args)
