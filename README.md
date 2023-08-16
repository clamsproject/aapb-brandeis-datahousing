# AAPB-Brandeis datahousing server

Codebase for the datahousing server deployed on Brandeis-LLC site as a part of [CLAMS Project](https://www.clams.ai). 

At the moment, the server is used to resovle AAPB GUIDs to local file paths, and works with the accompanying client, [`mmif-docloc-baapb`](https://github.com/clamsproject/mmif-docloc-baapb) MMIF plugin.

## Usage 

### Within CLAMS apps
The server deployment address is stored as [a organization variable](https://github.com/organizations/clamsproject/settings/variables/actions). To use the server (and `baapb` scheme in MMIF document locations), set `BAAPB_RESOLVER_ADDRESS` environment variable to the deployment address, and install the client plugin. 


All `brandeis` tagged pre-built container images (available in https://github.com/orgs/clamsproject/packages) 


### Outside of CLAMS apps

#### As a API
To use the server directly outside of a CLAMS app, use `searchapi` route with these two query string parameters:

* `file`: one of `text`, `audio`, `video`, `markup`, that indicates the type of the file to search for
* `guid`: the AAPB GUID to search for (either `cpb-aacip-xxx-yyyyyyyyyy` or simply `xxx-yyyyyyyyyy` form)

#### As a web app

Connect to `/` route to use the web app. The web app allows you to search for files by GUID.

### Deploy on your own

Install all the python dependencies with `pip install -r requirements.txt`, and configure your server using `.env` file or via environment variables (See `.env.sample` file for an example).

* `FLASK_APP`: must be `api`
* `FLASK_DEBUG`: set to `1` to enable debug mode, otherwise `0`
* `FLASK_RUN_PORT`: port number to listen
* `FLASK_RUN_HOST`: hostname to listen
* `ASSET_DIR`: path to the directory where the AAPB media files (assets) are stored
* `BUILD_DB`: set to `1` to build the database from scratch, otherwise `0`

