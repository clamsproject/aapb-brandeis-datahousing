"""

Route that provides analytics of the MMIF storage.

Example:

    curl -X GET 127.0.0.1:8001/storeapi/status

"""

from flask import jsonify, Blueprint

from api import STORAGE_DIR
from api.model import analytics


bp = Blueprint('analytics', __name__)
#print(f'{bp} import_name={bp.import_name} __name__={__name__}')


API_PREFIX = '/storeapi'


@bp.get(f"{API_PREFIX}/status")
def storage_analytics():
    stats = analytics.storage_analytics()
    return jsonify(stats)
