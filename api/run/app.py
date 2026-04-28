"""

This module takes care of running CLAMS Apps. It will typically be called from
the ClamsShack instance.

It contains a couple of mockup apps just for quick development cycles.

"""

import sys
import time
import argparse
import subprocess
from pathlib import Path
from random import Random

from mmif import Mmif, AnnotationTypes, DocumentTypes
from mmif.serialize.annotation import Annotation, Document

import api


def run_tokenizer(mmif_file: Mmif, params: dict) -> Mmif:
    if 'sleep' in params:
        time.sleep(params['sleep'])
    new_view = mmif_file.new_view()
    new_view.new_contain(AnnotationTypes.Token)
    return mmif_file


def run_spacy(mmif_file: Mmif, params: dict) -> Mmif | Exception:
    # doing this to make it fail once in a while so we can see what happens
    if Random().choice('abc') == 'a':
        raise Exception('Randomly generated exception')
    new_view = mmif_file.new_view()
    new_view.metadata.app = 'spacy-v3'
    new_view.new_contain(AnnotationTypes.Token)
    new_view.new_contain(AnnotationTypes.NamedEntity)
    for param, value in params.items():
        new_view.metadata.add_parameter(param, str(value))
    #print(mmif_file.views[0].metadata.parameters)
    time.sleep(2)
    return mmif_file


def run_swt(mmif_file: Mmif, params: dict):
    new_view = mmif_file.new_view()
    new_view.new_contain(AnnotationTypes.TimePoint)
    new_view.new_contain(AnnotationTypes.TimeFrame)
    return mmif_file


def create_document(identifier: str, path: Path) -> Document:
    doc = Document()
    doc.id = identifier
    if 'video' in path.parts:
        doc.at_type = DocumentTypes.VideoDocument
        doc.add_property('mime', f'video/{path.suffix}')
    elif 'text' in path.parts:
        doc.at_type = DocumentTypes.TextDocument
    else:
        print('Warning: could not determine @type')
    doc.add_property('location', str(path))
    return doc


def create_source(docs: list[Path]) -> Mmif:
    """Creates a MMIF sources from a list of document paths. This assumes it is
    possible to generate a document type from each path."""
    mmif = Mmif()
    for i, path in enumerate(docs):
        doc = create_document(f'd{i+1}', path)
        mmif.documents.append(doc)
    return mmif


def update_source(source_path: Path, asset_path: Path) -> Mmif:
    """Returns a Mmif object with the asset_path added if it was not already
    in there."""
    mmif = Mmif(source_path.read_text())
    locations = set([doc.location for doc in mmif.documents])
    # When searching the location we need to add the file:// prefix
    asset_loc = f'file://{str(asset_path)}'
    if asset_loc in locations:
        return mmif
    else:
        identifier = f'd{len(mmif.documents)+1}'
        doc = create_document(identifier, asset_path)
        mmif.documents.append(doc)
    return mmif


def run_job(name: str, location, batch, app):
    print('>>> starting batch process')
    cmd = ['python', 'run_batch.py', name,
           '--location', str(location), '--batch', batch, '--app', app]
    cmd_str = ' '.join(str(p) for p in cmd)
    with open(location / 'jobs' / name, 'a') as fh:
        fh.write(f'COMMAND\t{cmd_str}\n')
    process = subprocess.Popen(cmd, start_new_session=True)
    time.sleep(1)
    print('>>> job name   =', name)
    print('>>> process id =', process.pid)
    with open(location / 'jobs' / name, 'a') as fh:
        fh.write(f'PROCESS_ID\t{process.pid}\n')
    return(process.pid)


def parse_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument('-j', '--job', action='store_true')
    parser.add_argument('-b', '--batch', default=None)
    return parser.parse_args()



if __name__ == '__main__':

    if len(sys.argv) > 1 and sys.argv[1] == '--job':
        print('>>> running in batch mode')
        print('>>>', sys.argv)
        args = parse_arguments()
        print('>>>', args)
        run_batch(args)

    if False:
        
        path = Path('data/x/sources/aapb-6sEFeLNvHHZf.mmif')
        source = Mmif(path.read_text())
        result_swt = run_swt(source, {})
        result_tokenizer = run_tokenizer(result_swt, {'sleep': 1})
        result_spacy = run_spacy(result_tokenizer, {})
        with open('aapb-6sEFeLNvHHZf.mmif', 'w') as fh:
            fh.write(str(result_spacy))

        data_dir = '/Users/Shared/data/clams/aapb/assets-small'
        mmif = create_source([
            Path(f'{data_dir}/video/aapb-B3hpd0cw37bc.txt'),
            Path(f'{data_dir}/text/aapb-B3hpd0cw37bc.txt')])
        print(mmif)


