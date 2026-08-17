from flask import Blueprint


bp = Blueprint('api', __name__)
#print(f'{bp} import_name={bp.import_name} __name__={__name__}')


@bp.get('/')
def index():
    return {"message": "This is the MMIF storage server"}


@bp.get('/api')
def index_api():
    return {"message": "This is the MMIF storage server API"}
