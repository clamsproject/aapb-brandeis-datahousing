"""

Batch script to add MMIF files from a directory to the storage server.

The storage server is expected to run on 127.0.0.1:8001.

Usage:

$ python populate.py <directory> [-d] [-c INT]

This walks through the entire directory and tries to upload all files with the .mmif
extension. It assumes that MMIF files are always inside directories starting with
"preds@". Failures are written to the log. When debug=True the log name will be just
"log.txt", otherwise the name will include a timestamp. The -c option limits the
number of files from a "preds@" directory, the default is some high number.

For example, for the entire evaluation code or some subdirectory thereof:

$ python populate.py ../aapb-evaluations
$ python populate.py ../aapb-evaluations/timeframe-eval
$ python populate.py ../aapb-evaluations/timeframe-eval/preds@swt@3.1@batch2

Curl request used in this code:

$ curl -X POST 127.0.0.1:8001/storeapi/upload -d @<some_mmif_fille>

TODO (marc @ 4/21/25). This needs to be generalized (assuming it is useful useful beyond
what I used it for when populating MMIF storage) since it only works for files on the
evaluations repository at https://github.com/clamsproject/aapb-evaluations, which is now
deprecated.

"""


import os, argparse, time, subprocess
from datetime import datetime


url = '127.0.0.1:8001/storeapi/upload'


def timestamp():
    return datetime.now().strftime('%Y-%m-%dT%H:%M:%S')


def populate_storage_directory(evaluation_data: str, maxcount: int, debug: bool):
    log = 'log.txt' if debug else f'log-{timestamp()}.txt'
    with open(log, 'w') as fh_log:
        for directory, _, filenames in os.walk(top=evaluation_data):
            if 'preds@' in directory:
                fh_log.write(f'{timestamp()} >>> Uploading files from {directory}\n')
                print(f'Uploading files from {directory}')
                count = 0
                for filename in filenames:
                    if not filename.endswith('.mmif'):
                        continue
                    count += 1
                    if count > maxcount:
                        break
                    print(f'    {count} {filename}')
                    t0 = time.time()
                    path = f'{directory}/{filename}'
                    size = os.path.getsize(path)
                    command = ['curl', '-X', 'POST', url, '-d', f'@{path}']
                    result = subprocess.run(command, capture_output=True)
                    time_elapsed = time.time() - t0
                    fh_log.write(f'{timestamp()} --- {filename} size={size} time={time_elapsed:.6f}\n')
                    fh_log.write(f'{result.stdout.decode("utf-8").strip()}\n')


if __name__ == '__main__':

    parser = argparse.ArgumentParser()
    parser.add_argument('evaluation_data')
    parser.add_argument('-c', '--count', type=int, default=10000)
    parser.add_argument('-d', '--debug', action='store_true')
    args = parser.parse_args()
    populate_storage_directory(args.evaluation_data, args.count, args.debug)
