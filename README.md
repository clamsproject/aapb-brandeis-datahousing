# AAPB-Brandeis datahousing server

Codebase for the datahousing server deployed on Brandeis-LLC site as a part of [CLAMS Project](https://www.clams.ai). 

At the moment, the server is used to resolve AAPB GUIDs to local file paths, and works with the accompanying client, [`mmif-docloc-baapb`](https://github.com/clamsproject/mmif-docloc-baapb) MMIF plugin.


## Usage 

### Within CLAMS apps

The server deployment address is stored as [a organization variable](https://github.com/organizations/clamsproject/settings/variables/actions). To use the server (and `baapb` scheme in MMIF document locations), set `BAAPB_RESOLVER_ADDRESS` environment variable to the deployment address, and install the client plugin. 

All `brandeis` tagged pre-built container images (available in https://github.com/orgs/clamsproject/packages) 


### Server API

There are API routes for (1) searching the assets (typically videos, audio streams and transcripts), (2) uploading MMIF files, (3) downloading MMIF files, and (4) retrieving MMIF storage analytics.


**Searching assets**

To query available assets use the `searchapi` route with these three query string parameters:

* `guid` (required) — the AAPB GUID to search for (either `cpb-aacip-xxx-yyyyyyyyyy` or simply `xxx-yyyyyyyyyy` )
* `file` — the type of the file to search for: one of `text`, `image`, `audio`, `video`, `markup` and `other`
* `onlyfirst` — when used only the first match will be returned, default is false

Examples (these use URLs as if you have deployed your own server (see below)):

```
curl '127.0.0.1:8001/searchapi?guid=507-zw18k75z4h'
curl '127.0.0.1:8001/searchapi?guid=507-zw18k75z4h&file=video'
curl '127.0.0.1:8001/searchapi?guid=507-zw18k75z4h&onlyfirst=true'
```

These return a message if no file was found, a list of server paths or a single path (if onlyfirst was used).


**Uploading MMIF files**

For this you use the `storeapi/upload` route:

```
curl -X POST 127.0.0.1:8001/storeapi/upload -d @<some_mmif_file>
curl -X POST 127.0.0.1:8001/storeapi/upload?overwrite=True -d @<some_mmif_file>
```

In the first case you get a warning if a file was already uploaded, in the second case existing files will be overwritten.


**Downloading MMIF files**

This uses the `storeapi/download` route. There are three modes. In the zero-guid mode you just hand in a pipeline specification and the server returns the server path and all files at that path:

```bash
curl -X POST 127.0.0.1:8001/storeapi/download \
    -H 'Content-Type: "application/json"' \
    -d '{"pipeline": {"swt-detection/v2.0-38-g7838415": {"pretty": "True"}}}'
```
```json
{
  "filenames": [
    "cpb-aacip-690722078b2"
  ],
  "pipeline": "/Users/Shared/aapb/storage-test/swt-detection/v2.0-38-g7838415/5fe49d06725497b274b6eaaf0fe0c5d2"
}
```

If you add a guid then the server will return a MMIF file or a warning if the file did not exist:

```bash
curl -X POST 127.0.0.1:8001/storeapi/download
    -H 'Content-Type: "application/json"'
    -d '
    {
        "pipeline": { "swt-detection/v2.0-38-g7838415": {"pretty": "True"} },
        "guid": "NON-EXISTING GUID"
    }'
```
```json
{
  "error": "Did not find: NON-EXISTING GUID"
}
```

With a list of guids you get a dictionary:

```bash
curl -X POST 127.0.0.1:8001/storeapi/download \
    -H 'Content-Type: "application/json"' \
    -d '
    {
        "pipeline": { "swt-detection/v2.0-38-g7838415": {"pretty": "True"} },
        "guid": ["cpb-aacip-690722078b2", "NO-SUCH-GUID"]
    }'
```
```json
{
  "NO-SUCH-GUID": {
    "error": "Did not find: NONE"
  },
  "cpb-aacip-690722078b2": {
  	...
  }
```


**MMIF storage analytics**

To retrieve information on the status of data in the MMIF storage directory, use the `storeapi/status` route:

```angular2html
curl -X GET 127.0.0.1:8001/storeapi/status
```

This returns a dictionary with information on the full pipeline, e.g.:

```json
{
  "dirty_pipeline_mmif_count": 0,
  "non_terminal_mmif_count": 1,
  "pipelines": [
    {
      "mmif_count": 1,
      "path": "swt-detection/v7.4/3fd99622c1a78613dc21c3dc4984e6fe",
      "spec": {
        "swt-detection/v7.4/3fd99622c1a78613dc21c3dc4984e6fe": {
          "pretty": "true",
          "tfAllowOverlap": "false",
          "tfLabelMap": "['I:chyron', 'Y:chyron', 'N:chyron']",
          ...
        }
      }
    },
    {
      "mmif_count": 1,
      "path": "swt-detection/v7.4/3fd99622c1a78613dc21c3dc4984e6fe/tesseract/v2.0/e0ba0bab08a08fda1ed9f16d35bd21aa",
      "spec": {
        "swt-detection/v7.4/3fd99622c1a78613dc21c3dc4984e6fe": {
          ...
        },
        "tesseract/v2.0/e0ba0bab08a08fda1ed9f16d35bd21aa": {
          ...
        }
      }
    },
    {
      "mmif_count": 1,
      "path": "swt-detection/v7.4/3fd99622c1a78613dc21c3dc4984e6fe/doctr-wrapper/v1.4/e0ba0bab08a08fda1ed9f16d35bd21aa",
      "spec": {
        "doctr-wrapper/v1.4/e0ba0bab08a08fda1ed9f16d35bd21aa": {
          ...
        },
        "swt-detection/v7.4/3fd99622c1a78613dc21c3dc4984e6fe": {
          ...
        }
      }
    }
  ],
  "total_mmif_files": 3,
  "total_pipelines": 3
}
```


### Deploy on your own

Install all the python dependencies with `pip install -r requirements.txt`, and configure your server using `.env` file or via environment variables (See `.env.sample` file for an example).

* `FLASK_APP`: must be `api`
* `FLASK_DEBUG`: set to `1` to enable debug mode, otherwise `0`
* `FLASK_RUN_PORT`: port number to listen on
* `FLASK_RUN_HOST`: hostname to listen
* `ASSET_DIR`: path to the directory on the server where the AAPB media files (assets) are stored
* `BUILD_DB`: set to `1` to build the database from scratch, otherwise `0`

Start the server with `flask run`.
