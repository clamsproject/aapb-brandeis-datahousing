"""

Scratch file for some potentially random experiments.


# getting something little

curl -X POST 127.0.0.1:8001/storeapi/download \
    -H 'Content-Type: "application/json"' \
    -d '{"workflow": {
            "slatedetection/v2.0": {
                "threshold": "0.6", "pretty": "True", "stopAt": "9000"}}}'

curl -X POST 127.0.0.1:8001/storeapi/download \
    -H 'Content-Type: "application/json"' \
    -d '{"workflow": {
            "slatedetection/v2.0": {
                "threshold": "0.6", "pretty": "True", "stopAt": "9000"}},
         "guid": "cpb-aacip-29-1615dx6g"}'

# getting a large MMIF file (4mb)

curl -X POST 127.0.0.1:8001/storeapi/test1 \
    -H 'Content-Type: "application/json"' \
    -d '{"workflow": {"whisper-wrapper/v8": {"modelSize": "small"}}}'

curl -X POST 127.0.0.1:8001/storeapi/test1 \
    -H 'Content-Type: "application/json"' \
    -d '{"workflow": {"whisper-wrapper/v8": {"modelSize": "small"}},
         "guid": "cpb-aacip-507-4746q1t25k"}'

# now getting a bunch of SWT files

curl -X POST 127.0.0.1:8001/storeapi/download \
    -H 'Content-Type: "application/json"' \
    -d '{"workflow": {
            "swt-detection/v6.1": {
                "useStitcher": "false", "runningTime": "true", "hwFetch": "true"}}}'

curl -X POST 127.0.0.1:8001/storeapi/download \
    -H 'Content-Type: "application/json"' \
    -d '{"workflow": {
            "swt-detection/v6.1": {
                "useStitcher": "false", "runningTime": "true", "hwFetch": "true"}},
         "guid": [
            "cpb-aacip-259-wh2dcb8p", "cpb-aacip-c72fd5cbadc", "cpb-aacip-259-4j09zf95",
            "cpb-aacip-516-8c9r20sq57", "cpb-aacip-259-5717pw8g"]}'

# now a two-part workflow

curl -X POST 127.0.0.1:8001/storeapi/download \
    -H 'Content-Type: "application/json"' \
    -d '{"workflow": {
            "swt-detection/v6.1": {
                "useStitcher": "false", "runningTime": "true", "hwFetch": "true"},
            "simple-timepoints-stitcher/v3.1": {
                "minTFDuration": "1000", "minTPScore": "0.001", "minTFScore": "0.01",
                "labelMapPreset": "swt-v4-6way", "allowOverlap": "false"}}}'

curl -X POST 127.0.0.1:8001/storeapi/download \
    -H 'Content-Type: "application/json"' \
    -d '{"workflow": {
            "swt-detection/v6.1": {
                "useStitcher": "false", "runningTime": "true",  "hwFetch": "true"},
            "simple-timepoints-stitcher/v3.1": {
                "minTFDuration": "1000", "minTPScore": "0.001", "minTFScore": "0.01",
                "labelMapPreset": "swt-v4-6way", "allowOverlap": "false"}},
         "guid": [
            "cpb-aacip-75-72b8h82x", "cpb-aacip-f3fa7215348", "cpb-aacip-512-4m9183583s",
            "cpb-aacip-512-3f4kk9534t", "cpb-aacip-259-g737390m"]}'

"""


import os, time, copy, json, random
from flask import request, Blueprint, Response, jsonify, current_app
from api import utils


bp = Blueprint('experiments', __name__)
#print(f'{bp} import_name={bp.import_name} __name__={__name__}')


@bp.get('/experiments/stream')
def stream():
    def generate():
        for i in range(10):
            yield f'{{"{i}": True}}\n'
    return Response(generate(), mimetype='application/jsonl')


# To test a number of large files all handed over at the same time, prints the 
# memory use of the results object.
@bp.post('/experiments/test1')
def test1():
    t0 = time.time()
    data = json.loads(request.data.decode('utf-8'))
    print('>>>', data)
    workflow = ms.path_from_workflow_specs(data)
    num_apps = len(data.get('workflow', []))
    guid = data.get('guid')
    print('>>>', guid, num_apps, workflow)
    directory = os.environ.get('STORAGE_DIR')
    workflow = os.path.join(directory, workflow)
    if guid is None:
        return ms.zero_guid_download_response(workflow)
    else:
        mmif = ms.get_mmif_for_guid(workflow, guid, num_apps)
        print('>>>', type(mmif), len(str(mmif)))
    result = {}
    for i in range(10):
        result[f'{guid}-{i}'] = copy.deepcopy(mmif)
        print('SIZE', utils.getsize(result))
    print(time.time() - t0)
    return {}
    return jsonify(result)
    #return Response(generate(), mimetype='application/jsonl')


# To test a number of large files streamed one by one
@bp.get('/experiments/test2')
def test2():
    def generate():
        for i in range(10):
            yield f'{{"{i}": True}}\n'
    return Response(generate(), mimetype='application/jsonl')
