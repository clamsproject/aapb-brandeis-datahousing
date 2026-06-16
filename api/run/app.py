"""

This module takes care of running CLAMS Apps. The main functionality is:

- Running jobs
- Creating and updating MMIF source files

The latter is done here because the code in mmif.utils.cli.source was so complex
that it was easier to recreate it here than figure out how to use it properly.

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


def run_job(name: str, location: Path, path: Path, batch: str, app: tuple, params: dict):
    # TODO: consider handing it the ClamShack instance
    # TODO: consider putting this code on ClamShack
    param_string = json.dumps(params)
    cmd = ['python', 'run_batch.py', name,
           '--location', str(location),
           '--path', str(path),
           '--batch', batch,
           '--app-name', app.name,
           '--app-url', app.url,
           '--params', param_string]
    cmd_str = ' '.join(str(p) for p in cmd)
    with open(location / 'jobs' / name, 'a') as fh:
        fh.write(f'COMMAND\t{cmd_str}\n')
    process = subprocess.Popen(cmd, start_new_session=True)
    with open(location / 'jobs' / name, 'a') as fh:
        fh.write(f'PROCESS_ID\t{process.pid}\n')
    return(process.pid)


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
        doc.add_property('mime', f'text/plain')
    else:
        print('Warning: could not determine @type')
    doc.add_property('location', str(path))
    return doc


def create_source(docs: list[Path]) -> Mmif:
    """Creates a MMIF source from a list of document paths. This assumes it is
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
