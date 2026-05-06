"""

This module takes care of running CLAMS Apps. The main functionality is:

- Running jobs
- Creating and updating MMIF source files

The latter is done here because the code in mmif.utils.cli.source was so complex
that it was easier to recreate it here than figure out how to use it properly.

In addition, this module contains a couple of fake apps for quick development
cycles.

"""

import sys
import time
import json
import argparse
import subprocess
from pathlib import Path
from random import Random

from mmif import Mmif, AnnotationTypes, DocumentTypes
from mmif.serialize.annotation import Annotation, Document

import api


def run_job(name: str, location: Path, path: Path, batch: str, app: str, params: dict):
    # TODO: consider handing it the ClamShack instance
    # TODO: consider putting this code on ClamShack
    param_string = json.dumps(params)
    cmd = ['python', 'run_batch.py', name,
           '--location', str(location),
           '--path', str(path),
           '--batch', batch,
           '--app', app,
           '--params', param_string]
    cmd_str = ' '.join(str(p) for p in cmd)
    with open(location / 'jobs' / name, 'a') as fh:
        fh.write(f'COMMAND\t{cmd_str}\n')
    process = subprocess.Popen(cmd, start_new_session=True)
    with open(location / 'jobs' / name, 'a') as fh:
        fh.write(f'PROCESS_ID\t{process.pid}\n')
    return(process.pid)


def run_tokenizer(mmif_file: Mmif, params: dict) -> Mmif:
    atypes = [AnnotationTypes.Token]
    return run_app('http://apps.clams.ai/tokenizer/v1', mmif_file, params, atypes)


def run_spacy(mmif_file: Mmif, params: dict) -> Mmif:
    atypes = [AnnotationTypes.Token, AnnotationTypes.NamedEntity]
    return run_app('http://apps.clams.ai/spacy/v3', mmif_file, params, atypes)


def run_swt(mmif_file: Mmif, params: dict):
    atypes = [AnnotationTypes.TimePoint, AnnotationTypes.TimeFrame]
    return run_app('http://apps.clams.ai/swt/v7.0', mmif_file, params, atypes)


def run_app(name: str, mmif_file: Mmif, params: dict, types: list):
    # doing this to make it fail once in a while so we can see what happens
    if Random().choice('abc') == 'a':
        raise Exception('Randomly generated exception')
    new_view = mmif_file.new_view()
    new_view.metadata.app = name
    for t in types:
        new_view.new_contain(t)
        new_view.new_contain(AnnotationTypes.NamedEntity)
    for param, value in params.items():
        new_view.metadata.add_parameter(param, str(value))
    # faking that it is taking some time
    time.sleep(5)
    return mmif_file


def create_document(doc_id: str, path: Path) -> Document:
    # TODO: this should be generalized and deal with all mime types
    doc = Document()
    doc.id = doc_id
    # TODO: should not just rely on the path
    if 'video' in path.parts:
        doc.at_type = DocumentTypes.VideoDocument
        doc.add_property('mime', f'video/{path.suffix[1:]}')
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
