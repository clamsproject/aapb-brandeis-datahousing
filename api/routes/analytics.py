"""

Routes that provides analytics of the MMIF storage or just the paths.

Example:

    curl -X GET 127.0.0.1:8001/api/status
    curl -X GET 127.0.0.1:8001/api/paths

"""

from flask import jsonify, Blueprint

from api import STORAGE_DIR
from api.model import analytics


bp = Blueprint('analytics', __name__)
#print(f'{bp} import_name={bp.import_name} __name__={__name__}')


API_PREFIX = '/storeapi'


@bp.get(f"/api/status")
@bp.get(f"{API_PREFIX}/status")
def storage_analytics():
    stats = analytics.storage_analytics()
    return jsonify(stats)


@bp.get(f"/api/paths")
def storage_paths():
    stats = analytics.storage_analytics()
    return jsonify([wf["path"] for wf in stats["workflows"]])
