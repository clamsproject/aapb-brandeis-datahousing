"""

Routes that provides analytics of the MMIF storage or just the paths.

Example:

    curl -X GET 127.0.0.1:8001/api/mmif/status
    curl -X GET 127.0.0.1:8001/api/mmif/paths

"""

from flask import jsonify, Blueprint

from api import STORAGE_DIR
from api.model import analytics


bp = Blueprint('analytics', __name__)
#print(f'{bp} import_name={bp.import_name} __name__={__name__}')


@bp.get('/api/mmif/status')
@bp.get('/storeapi/status')
def storage_analytics():
    stats = analytics.storage_analytics()
    return jsonify(stats)


@bp.get(f"/api/mmif/paths")
def storage_paths():
    stats = analytics.storage_analytics()
    return jsonify([wf["path"] for wf in stats["workflows"]])
