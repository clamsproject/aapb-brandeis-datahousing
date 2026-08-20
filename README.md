# AAPB-Brandeis datahousing server

Codebase for the datahousing server deployed on the Brandeis-LLC site as a part of the [CLAMS Project](https://www.clams.ai).

At the moment, the server is used to resolve AAPB GUIDs to local file paths, and works with the accompanying client, [`mmif-docloc-baapb`](https://github.com/clamsproject/mmif-docloc-baapb) MMIF plugin.


## Usage 


### Within CLAMS apps

The server deployment address is stored as [an organization variable](https://github.com/organizations/clamsproject/settings/variables/actions). To use the server (and `baapb` scheme in MMIF document locations), set the `BAAPB_RESOLVER_ADDRESS` environment variable to the deployment address, and install the client plugin. 

<!--
All `brandeis` tagged pre-built container images (available in https://github.com/orgs/clamsproject/packages) 
-->

### Server API

There are API routes for (1) searching the assets (typically videos, audio streams and transcripts), (2) uploading MMIF files, (3) downloading MMIF files, and (4) retrieving MMIF storage analytics.


**Searching assets**

To query available assets use the `api/assets/search` or `searchapi` route with these three query string parameters:

* `guid` — part of the AAPB GUID to search for (min. 3 characters), required parameter
* `file` — the type of the file to search for: any number of `text`, `image`, `audio`, `video`, `markup` and `other`, default is to search for all types
* `onlyfirst` — when used only the first match will be returned, default is false

Examples for a local install (the host name and port numbers may differ depending on how you deployed your server, see below):

```
curl '127.0.0.1:8001/api/assets/search?guid=zw18'
curl '127.0.0.1:8001/api/assets/search?guid=507-zw18k75z4h'
curl '127.0.0.1:8001/api/assets/search?guid=507-zw18k75z4h&file=video'
curl '127.0.0.1:8001/api/assets/search?guid=507-zw18k75z4h&file=video&file=other'
curl '127.0.0.1:8001/api/assets/search?guid=507-zw18k75z4h&onlyfirst=true'
```

These return a message if no file was found, a list of server paths or a single path (if onlyfirst was used). Note that searches for short strings that occur in many GUIDs may take a few seconds.


**Uploading MMIF files**

For this you use the `api/mmif/upload` or `storeapi/upload` route:

```
curl -X POST 127.0.0.1:8001/api/mmif/upload -d @<some_mmif_file>
curl -X POST 127.0.0.1:8001/api/mmif/upload?overwrite=True -d @<some_mmif_file>
```

In the first case you get a warning if a file was already uploaded, in the second case existing files will be overwritten.


**Peeking into a workflow directory**

This uses the `api/mmif/peek` or the `storeapi/peek` route which takes a workflow specification and returns the server path and all files at that path:

```bash
curl -X POST 127.0.0.1:5000/api/mmif/peek \
    -H 'Content-Type: "application/json"' \
    -d '{"workflow": {"swt-detection/v8.6": {"pretty": "True"}}}'
```
```json
{
  "filenames": [
    "cpb-aacip-259-wh2dcb8p",
    "cpb-aacip-c72fd5cbadc",
    "cpb-aacip-259-4j09zf95",
    "cpb-aacip-516-8c9r20sq57",
    "cpb-aacip-259-5717pw8g"
  ],
  "workflow_id": "swt-detection/v8.6/5fe49d06725497b274b6eaaf0fe0c5d2"
}
```

The workflow can have more than one application:

```bash
curl -X POST 127.0.0.1:5000/api/mmif/peek \
    -H 'Content-Type: "application/json"' \
    -d '{"swt-detection/v8.6": {}, "smolvlm2-captioner/v1.0": {}}'
```

If the pipeline path did not exist on the server, the response will still include a workflow path, but the list of files will be empty.


**Downloading MMIF files**

This uses the `api/mmif/download` or `storeapi/download` route. There are two modes: single identifier and list of identifiers. 

The one-identifier mode takes a workflow specification and an identifier, and the server will return a MMIF file or a warning if the file did not exist:

```bash
curl -X POST 127.0.0.1:8001/api/mmif/download \
    -H 'Content-Type: "application/json"' \
    -d '{"workflow": { "swt-detection/v8.6": {"pretty": "True"} },
         "guid": "non-existing-identifier"}'
```
```json
{
  "error": "Did not find: non-existing-identifier"
}
```

With a list of identifiers (including just one identifier), the server will return a ZIP file. The `--output` ZIP file name must be specified in the request to the server.

```bash
curl -X POST 127.0.0.1:8001/api/mmif/download \
    -H 'Content-Type: "application/zip"' \
    --output mmif_zip.zip \
    -d '{"workflow": { "whisper-wrapper/v3": {"modelSize": "tiny"} },
         "guid": ["cpb-aacip-507-154dn40c26", "no-such-id"]}'
```

The zipfile returned has the MMIF files for each GUID, in addition it has an error log with notifications on which files could not be retrieved and a file with the workflow path from the server.


**MMIF storage analytics**

To retrieve information on the status of data in the MMIF storage directory, use the `api/mmif/status` or `storeapi/status` route:

```bash
curl -X GET 127.0.0.1:8001/api/mmif/status
```

This returns a dictionary with information on the full workflow, e.g.:

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

There is also a command to retrieve just the paths:

```bash
curl -X GET 127.0.0.1:8001/api/mmif/path
```


### Storage Server Browser

Some of the functionality above is also available via the Storage Server Browser at [http://localhost:8001/www/](http://localhost:8001/www/). You can search for assets and MMIF files, and then view the MMIF files and see descriptions and summaries for them. You can also open the inspector on a MMIF file. You cannot upload and download files.


## Deploy on your own

Install all Python dependencies with `pip install -r requirements.txt` and configure your server using a `.env` file or via environment variables (this is both for general Flask settings and application-specific settings, see `.env.sample` for an example configuration file). The following variables need to be defined:

* `FLASK_APP`: must be `api`
* `FLASK_DEBUG`: set to `1` to enable debug mode, otherwise `0`
* `FLASK_RUN_PORT`: port number to listen on
* `FLASK_RUN_HOST`: hostname
* `ASSET_DIR`: path to the directory on the server where the AAPB media files (assets) are stored
* `STORAGE_DIR`: the directory where MMIF files are stored
* `BUILD_DB`: set to `1` to build the database from scratch, otherwise `0`
* `DEVELOPER_MODE`: set to `1`  for developer mode, which adds some routes to the API

Before you start the server for the first time you should build the assets database.

```bash
flask create-db
```

To start the server do

```bash
flask run
```

### Using Docker

With Docker your server configuration settings in `.env` are likely to be more like the example in `.env.docker`:

```python
FLASK_APP=api
FLASK_DEBUG=1
FLASK_RUN_PORT=8080
FLASK_RUN_HOST=0.0.0.0
ASSET_DIR=/data/assets
STORAGE_DIR=/data/mmif
BUILD_DB=1
DEVELOPER_MODE=0
```

To build a Docker image (change name and tag as needed):

```bash
docker build -t aapb-data:v1 -f Containerfile .
```

To run the container:

```bash
docker run --name aapb -d --rm -it -p 8080:8080 -v /Users/Shared/aapb:/data aapb-data:v1
```

This assumes that locally the assets and MMIF files live in subdirectories of `/Users/Shared/aapb`, adjust that path as needed. Note how the -v option mounts the local asset/mmif directories to the '/data' directory on the container, if you had used another path in the configuration settings for `ASSET_DIR` and `STORAGE_DIR` then you would have to adjust the docker-run command.

The server runs on [http://localhost:8080/www/](http://localhost:8080/www/)

Since `BUILD_DB` is set to 1 you should expect a delay, the API and website won't be running until the databse is created.

