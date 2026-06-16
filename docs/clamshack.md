# ClamShack notes

Some notes on he ClamShack tool, parts of it meant to slowly morph into a manual.


## Introduction

Assumptions:

- Relatively small Shack sizes, no more than several hundred or a thousand assets.
- There is some way to get the type (video, text etcetera) from the assets path.
- MMIF files always end with `.mmif`.
- All asset and MMIF file management happens through the Shack.
- All assets are available on a local or mounted disk.
- CLAMS Apps are running in containers.

The name used to be CLAMS Shack, but that seemed clunky with the two esses. It was changed into ClamShack, which somewhat looses its connection to what the acronym stands for but does on the other hand feel so much better. ClamShack will often be abbrviated to Shack.


### Running the ClamShack and the ClamShell

To create a shack:

```bash
python -m api.cli --shack <DIRECTORY> --assets <FILE>
```

This creates a new directory, if the directory already exists then the code will exit with a warning.

To open an already existing Shack:

```bash
python -m api.cli --shack <DIRECTORY>
```

After either command you end up in the ClamShell REPL where you have access to a bunch of commands as well as to the `shack` variable, which contains the Python ClamShack object.


## Assets

Every ClamShack is associated with an assets list, this association can be done only once, once you have specified a set of assets you cannot change them anymore, you would have to create a new Shack if you want to do that.

> This may be changed at some point and we may allow extra assets to be added later. For now we like how this makes sure you always now that each job that was run for this Shack has always applied to the same assets.

The assets list looks like this:

```
/Users/Shared/aapb/assets-small/
video/cpb-aacip-ektu19x2tppz.mp4
text/cpb-aacip-ektu19x2tppz.txt
video/cpb-aacip-c0s1okl2t02r.mp4
text/cpb-aacip-c0s1okl2t02r.txt
```

There is a top-level directory (which will be the one mounted to `/data` on the container, see below) followed by relative paths from the top-level directory. The full path should point to an existing file.

For now we make sure that the asset names match the GUID requirements of the AAPB data, that is, they start with `cpb-aacip-` and followed by a set of digits and lowercase letters. There can be multiple assets for each GUID.

When adding an asset we automatically create a source MMIF file for it. If an asset is added that is an additional asset for a GUID then the MMIF source will be recreated. Assets are not stored in the Shack, instead a list of absolute asset paths is maintained.

> Creating MMIF sources does not use the code in the `mmif source` utility. That code seems oddly complex and should be revised.

MMIF source files live in the ClamShack directory in `sources` and look like this:

```python
{
  "metadata": {
    "mmif": "http://mmif.clams.ai/1.1.0"
  },
  "documents": [
    {
      "@type": "http://mmif.clams.ai/vocabulary/VideoDocument/v1",
      "properties": {
        "mime": "video/mp4",
        "id": "d1",
        "location": "file:///data/video/cpb-aacip-ektu19x2tppz.mp4"
      }
    },
    {
      "@type": "http://mmif.clams.ai/vocabulary/TextDocument/v1",
      "properties": {
        "id": "d2",
        "location": "file:///data/text/cpb-aacip-ektu19x2tppz.txt"
      }
    }
  ],
  "views": []
}
```

Note how the location has appended the relative path of the asset from the list to the container's data directory.

Todo:

- Recreating a source potentially introduces non-determinism of workflow results. We are considering an approach where we can have multiple sources for a GUID.
- Make sure that the mime type is properly derived from the path, at the moment it expects there to be a path part that matches `text` or `video`.
- Determine whether we allow additonal files to be added. If not, initialization of a ClamShack should require an asset list. If we do allow later additions, then we should at least make sure that the top-level directory path is the same. And we should also perhaps deal with the fact that two runs on the default batch may involve different files.
- Also to determine is whether we really want to allow batches or just define the ClamShack as something that is created for a batch.


## Workflows and CLAMS Apps

The Shack has only access to CLAMS Apps that are running as Docker or Podman containers. Those apps can be registered by providing the host name and the port for the app.

Running an app requires several things from the user:

- Make sure CLAMS Apps are running in containers.
- Register an app with the ClamShack.
- Select one of the available apps to form a one-app workflow (multi-app workflow are a later worry).
- Select the input by navigating through the MMIF storage.
- Create a unique name for the job and then start the job, which will run in the background as a separate process. This latter step will probably only work on Linux-like systems.

Next up is to make sure that apps are registered from available Docker container that are exposed on a port. This could be done by searching the list of active containers and pinging them to see any app metadata are volunteered.


### Step 1: CLAMS Containers

As mentioned above, running containers are needed for the Shack. Here is as an example how to run the spaCy container. First get the image:

```bash
docker pull ghcr.io/clamsproject/app-spacy-wrapper:v2.1
```

As usual the tricky part is to mount the container correctly so it can find the assets. We mount the `/data` directory on the container to the local directory where the assets live, using the asset list example from above:

```bash
docker run --rm -d -p 5001:5000 -v /Users/Shared/aapb/assets-small:/data --name spacy ghcr.io/clamsproject/app-spacy-wrapper:v2.1
```

Basically, the `/data` directory maps to the highest path that governs all assets. 

Now we can access the metadata of the app or running it:

```
curl http://127.0.0.1:5001
cat test/sources/cpb-aacip-p38dffl7ov46.mmif | curl -X POST 127.0.0.1:5001 -d@-
```


### Step 2: Registration

And from the Shack you can register the app:

```
ClamShell test> register http://127.0.0.1:5001
Registered http://apps.clams.ai/spacy-wrapper/v2.1
```

Registration involves the ClamShack retrieving the applications identifier from the metadata of the app and storing the identifier and the URL in a dictionary (you can get this dictionary by typing `shack.apps` in the ClamShell):

```python
{'http://apps.clams.ai/spacy-wrapper/v2.1': 'http://127.0.0.1:5001'}
```

> One common mistake is to forget to add the http scheme when registering an app. With the curl command you can omit the http scheme, but for the register command you need it and it can be hard so see why the command fails.


### Step 3: CLAMS App selection

This is simple now that we only do a one-app pipeline, simply select the one registered application:

```
ClamShell test> apps
╭─────────────────────────────────────────────────────────────────────────────────╮
│ Registered CLAMS Apps                                                           │
╰─────────────────────────────────────────────────────────────────────────────────╯
 0: http://apps.clams.ai/spacy-wrapper/v2.1

ClamShell test> apps 0
Selected http://apps.clams.ai/spacy-wrapper/v2.1
```

The first commands list the registered apps and the second selects one using the index in the dictionary (you could also use the full app identifier).


### Step 4: Selecting the input

Select the input by navigating through the MMIF storage, which is kept in the `mmif` directory. By default the cursor in the MMIF storage directory is at the top level, which means that the input is going to be the MMIF base source files that were created for the assets. To update the path in the MMIF storage use the following commands. 

| command | description                                                          |
| ------- | -------------------------------------------------------------------- |
| pwd     | List the current directory, can also be done with the `show` command |
| dir     | Show all sub directories of the current directory                    |
| files   | Show all files in the current directory                              |
| cd      | Change the directory, use the index or the name of the directory     |


### Step 5: Run the job

Create a unique name for the job and then start the job, which will run in the background as a separate process. This will probably only work on Linux-like systems. For this, use the `run` command, which will use the selected app and the selected path. Control will immediately come back to the ClamShell, you can see status of all jobs with `jobs`.


## Various developer notes


### Search

Distinguish between several kinds of search.

- Asset search on GUIDs. This is already implemented.
- MMIF file search on GUIDs, apps and workflow properties. The first could be folded into the asset search. On apps and/or workflow properties we should search every part of the workflow, for example, a spaCy result is still a spaCy result if it is in the last step of a workflow.
- A mix of search inputs, for example GUIDs and apps.


### Batches

There is a default batch which just uses all assets or MMIF sources. Add batches by selecting elements or by reading a list of identifiers or by getting it from the website at:

- [https://github.com/clamsproject/aapb-annotations/tree/main/batches](https://github.com/clamsproject/aapb-annotations/tree/main/batches)

Todo:

- Add other batches beyond the one default batch
- Should be able to create them (manually, from list, from aapb-annotation url).
- Should be used in `run_batch.py`.
- Maybe the default batch does not need to be in the batches dictionary.


### Jobs

One thing that happens when you run a job is that the api storage code will not use the `STORAGE_DIR` environment variable. This is so we can isolate this better. The upload code was adjusted for this.

Todo:

- Jobs overide prior results, perhaps add a flag as with the storage upload to allow/disallow overwrite.
- Would like to sort them on start time
- They are less fragile than they used to be, but should still consider using a Job class that reads the job file and perhaps some changes to the format and content of the job file: (1) separate lines to represent things like batch info, app name, parameters etcetera, (2) add a count of files to be processed (allows later inspection of the file to print a percentage done number). 
- Make sure that files like '.DS_store' and others that are not jobs will be skipped, should be done in ClamShack


### Other

Q: When initializing also create .env?<br/>
A: No, because than you overwrite the current one, but maybe create .env-shack

When loading a shack assets names and MMIF files names are loaded, but the latter are not updated when we run jobs.