"""

Routes relevant to the assets repository.

Examples:

    curl '127.0.0.1:8001/api/assets/search?guid=zw18'
    curl '127.0.0.1:8001/api/assets/search?guid=507-zw18k75z4h'
    curl '127.0.0.1:8001/api/assets/search?guid=507-zw18k75z4h&file=video'
    curl '127.0.0.1:8001/api/assets/search?guid=507-zw18k75z4h&file=video&file=other'
    curl '127.0.0.1:8001/api/assets/search?guid=507-zw18k75z4h&onlyfirst=true'

"""

# TODO: If there is a use case, and I think there is, then we should add routes
#       for uploading and downloading assets from the storage.


from flask import request, Blueprint

from api.model.assets import search_assets


bp = Blueprint('assets', __name__)
#print(f'{bp} import_name={bp.import_name} __name__={__name__}')


# The first route is a proposed new route, the second is what was used till now
@bp.get('/api/assets/search')
@bp.get('/searchapi')
def search_api():
    file_type = request.args.getlist('file') if 'file' in request.args else []
    guid = request.args['guid']
    only_first = request.args.get('onlyfirst', False)
    # TODO: hand in only_first as a parameter to search_assets
    paths = search_assets(guid, file_type)
    if len(paths) > 0:
        return paths[0] if only_first else paths
    else:
        return 'The requested file does not exist in our server', 404
