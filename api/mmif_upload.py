import json
import os
from pathlib import Path

from flask import request, jsonify, Blueprint, current_app, send_file

from clams_utils.aapb import guidhandler
from mmif import utils, Mmif, View
from mmif.utils.workflow_helper import generate_workflow_identifier

from api import STORAGE_DIR
from api.utils import hash_from_dictionary


bp = Blueprint('mmif_upload', __name__)
print(f'{bp} import_name={bp.import_name} __name__={__name__}')


API_PREFIX = '/storeapi'


def identifier_of_first_document(mmif_file: Mmif):
    for doc in mmif_file.documents:
        if doc.id:
            return doc.id
    return None


@bp.post(f"{API_PREFIX}/upload")
def upload_mmif():
    try:
        body = request.get_data(as_text=True)
        overwrite = request.args.get('overwrite')
        overwrite = True if overwrite in ('1', 't', 'true', 'True') else False
        mmif = Mmif(body)
        # Assuming the first document is the "main" one that has the AAPB GUID
        doc_id = identifier_of_first_document(mmif)
        if doc_id is None:
            return upload_error_response(ValueError("No document with identifier found in MMIF"))
        guid = guidhandler.get_aapb_guid_from(mmif[doc_id].location)
        cur_root = Path(STORAGE_DIR)

        wfid, param_dicts = generate_workflow_identifier(
            mmif, return_param_dicts=True)
        # wf_id syntax is app1name/app1version/app1paramhash/app2name/...
        segments = wfid.split('/')
        if len(segments) % 3 != 0:
            return upload_error_response(ValueError("Malformed workflow identifier"))
        mmif_fname = None
        for i in range(0, len(segments), 3):
            appn = segments[i]
            appv = segments[i + 1]
            param_hash = segments[i + 2]
            cur_root = cur_root / Path(appn) / appv / param_hash
            cur_root.mkdir(parents=True, exist_ok=True)
            with open(cur_root.with_suffix('.json'), 'w') as f:
                json.dump(param_dicts[i // 3], f, indent=2)
            mmif_fname = cur_root / f'{guid}.mmif'
        if not mmif_fname:
            return upload_no_views_response(mmif_fname)
        if mmif_fname.exists():
            if overwrite:
                with open(mmif_fname, 'w') as f:
                    f.write(body)
                return upload_overwrite_response(mmif_fname)
            else:
                return upload_not_saved_response(mmif_fname)
        else:
            with open(mmif_fname, 'w') as f:
                f.write(body)
            return upload_created_response(mmif_fname)
    except Exception as e:
        return upload_error_response(e)


def upload_no_views_response(mmif_fname):
    return jsonify(
        {"status": "warning",
         "filename": str(mmif_fname),
         "message": f"file had no contentful views and was not saved"}), 200


def upload_created_response(mmif_fname):
    return jsonify(
        {"status": "success",
         "filename": str(mmif_fname),
         "message": "file created"}), 201


def upload_not_saved_response(mmif_fname):
    return jsonify(
        {"status": "warning",
         "filename": str(mmif_fname),
         "message": "file not saved because it already exists"}), 200


def upload_overwrite_response(mmif_fname):
    return jsonify(
        {"status": "success",
         "filename": str(mmif_fname),
         "message": "file existed and was overwritten"}), 201


def upload_no_version_response(appn):
    return jsonify(
        {"status": "error",
         "message": f"app {appn} version is underspecified"}), 400


def upload_error_response(e):
    return jsonify(
        {"status": "error",
         "message": f"{type(e).__name__} - {e}", }), 400

