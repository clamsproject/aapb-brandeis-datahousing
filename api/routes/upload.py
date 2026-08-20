"""

Route for uploading MMIF documents.

"""

from flask import request, jsonify, Blueprint

from api import STORAGE_DIR
from api.errors import UploadWarning
from api.model.storage import upload_mmif


bp = Blueprint('mmif_upload', __name__)
#print(f'{bp} import_name={bp.import_name} __name__={__name__}')


@bp.post('/api/mmif/upload')
@bp.post('/storeapi/upload')
def upload():
    try:
        body = request.get_data(as_text=True)
        overwrite = request.args.get('overwrite')
        overwrite = True if overwrite in ('1', 't', 'true', 'True') else False
        path = upload_mmif(body, overwrite=overwrite)
    except UploadWarning as e:
        return_message = {"status": "warning", "message": str(e) }
        if e.path is not None:
            return_message["path"] = str(e.path)
        return jsonify(return_message), 200
    except Exception as e:
        return jsonify(
            {"status": "success", "message": str(e)}), 400
    return jsonify(
            {"status": "success",
             "path": str(path),
             "message": "file created"}), 201
