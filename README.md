# AAPB-Brandeis datahousing server

Codebase for the datahousing server deployed on the Brandeis-LLC site as a part of the [CLAMS Project](https://www.clams.ai).

The server resolves AAPB GUIDs to the local file paths of the matching assets (videos, audio streams, transcripts and other files). It works with the accompanying client, the [`mmif-docloc-baapb`](https://github.com/clamsproject/mmif-docloc-baapb) MMIF plugin.

Storage of MMIF files is handled by [`mmif-storage`](https://github.com/clamsproject/mmif-storage) and [`mmif-storage-api`](https://github.com/clamsproject/mmif-storage-api).


## Usage

### Within CLAMS apps

To resolve `baapb://` URIs in MMIF document locations from within a CLAMS app:

1. Add [`mmif-docloc-baapb`](https://github.com/clamsproject/mmif-docloc-baapb) to the dependencies of the app. The plugin registers itself with `mmif-python` (version 1.0.2 or later).
1. Set the `BAAPB_RESOLVER_ADDRESS` environment variable to the deployment address of this server, including the port number (`hostname:port`). The address of the Brandeis deployment is stored as [an organization variable](https://github.com/organizations/clamsproject/settings/variables/actions).

The plugin then resolves `baapb://` URIs to local file paths when the app reads a MMIF document. For more information on MMIF plugins, see the [MMIF Python SDK documentation](https://clams.ai/mmif-python/latest/plugins.html).

### Server API

To query available assets, use the `api/assets/search` route (also available as `searchapi`) with these query string parameters:

* `guid`: part of the AAPB GUID to search for (minimum 3 characters), required
* `file`: the type of the file to search for, any number of `text`, `image`, `audio`, `video`, `markup` and `other`; the default is all types
* `onlyfirst`: when present, only the first match is returned

Examples for a local install (the host name and port number depend on how you deployed the server, see below):

```bash
curl '127.0.0.1:5000/api/assets/search?guid=zw18'
curl '127.0.0.1:5000/api/assets/search?guid=507-zw18k75z4h'
curl '127.0.0.1:5000/api/assets/search?guid=507-zw18k75z4h&file=video'
curl '127.0.0.1:5000/api/assets/search?guid=507-zw18k75z4h&file=video&file=other'
curl '127.0.0.1:5000/api/assets/search?guid=507-zw18k75z4h&onlyfirst=true'
```

The response is a JSON list of server paths, or a single path if `onlyfirst` was used. If no file matches, the server responds with status 404 and a message. Searches for short strings that occur in many GUIDs can take a few seconds.

### Asset browser

The same search is available in a web browser at the `/www/` path of the server, for example [http://localhost:5000/www/](http://localhost:5000/www/).


## Deploy on your own

Install the Python dependencies with `pip install -r requirements.txt` and configure the server with a `.env` file or with environment variables (see `.env.sample` for an example). The following variables are used:

* `FLASK_APP`: must be `api`
* `FLASK_DEBUG`: set to `1` to enable debug mode, otherwise `0`
* `FLASK_RUN_PORT`: port number to listen on
* `FLASK_RUN_HOST`: host name
* `ASSET_DIR`: path to the directory on the server where the AAPB media files (assets) are stored, required
* `BUILD_DB`: set to `1` to build the assets database from scratch at each start, otherwise `0` (the default)

The directory tree under `ASSET_DIR` can have any structure. The file type of an asset is taken from its file extension. Only files with a name that starts with `cpb` are indexed.

Before you start the server for the first time, build the assets database:

```bash
flask create-db
```

To start the server:

```bash
flask run
```

### Using a container

In a container the configuration in `.env` is likely to be more like the example in `.env.docker`.

To build an image (change name and tag as needed):

```bash
docker build -t aapb-data:v1 -f Containerfile .
```

To run the container:

```bash
docker run --name aapb -d --rm -it -p 8080:8080 -v /Users/Shared/aapb:/data aapb-data:v1
```

This assumes that the assets live in the `assets` subdirectory of `/Users/Shared/aapb` on the host. The `-v` option mounts that directory on `/data` in the container, which matches `ASSET_DIR=/data/assets` in `.env.docker`. If you use another path for `ASSET_DIR`, adjust the mount accordingly.

The server runs on [http://localhost:8080/www/](http://localhost:8080/www/).

Because `BUILD_DB` is set to `1`, the API and the browser are not available until the database is created.

### Production

`app_production.py` is the entry point for a WSGI server such as gunicorn. It reads its configuration from a `.env.production` file next to it, builds the assets database once, and then creates the application:

```bash
gunicorn --bind 0.0.0.0:8080 --timeout 1200 app_production:app
```

`baapb-datahousing.container` is the [quadlet](https://docs.podman.io/en/latest/markdown/podman-systemd.unit.5.html) unit used for the Brandeis deployment. It runs the command above in an image built from `Containerfile`.
