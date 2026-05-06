# ClamShack notes


Assuming:

- Relatively small Shack sizes, no more than several hundred or a thousand assets.
- There is some way to get the type (video, text etcetera) from the assets path.
- MMIF files always end with `.mmif`.
- All asset and MMIF file management happens through the Shack.
- All assets are available on a local or mounted disk.
- While the Shack is in business, no other processes make changes to them.


### Naming

The name used to be CLAMS Shack, but that seemed clunky with the two esses. It was changed into ClamShack, which somewhat looses its connection to what the acronym stands for but does on the other hand evoke that instead of a whole bunch of data there is only one morsel in there.


### Assets

For now make sure that the assets match the GUID requirements of the AAPB data, that is, start with `cpb-aacip-` and followed by a set of digits and lowercase numbers.

When adding an asset we automatically create a source MMIF file for it. If an asset is added that is an additional asset for a GUID then the MMIF source will be recreated. Assets are not stored in the Shack, instead a list of absolute asset paths is maintained. This does not use the code in the `mmif source` utility, which should be revised.

Todo:

- Recreating a source potentially introduces non-determanism of workflow results. We are considering an approach where we can have multiple sources for a GUID.
- Make sure that the mime type is properly derived from the path, at the moment it expects there to be a path part that matches `text` or `video`.


### Workflows and CLAMS Apps

Available applications are registered. At the moment this means that there are three hard-coded fake applications that act as if they are CLAMS Apps, taking MMIF input and creating MMIF output.

The names of the fake CLAMS Apps need to be realistic, for example `http://apps.clams.ai/swt-detection/v7.4`. Without that parsing the path would not give a proper (appname, version) pair like `('swt-detection', 'v7.4')`.

Running an app requires three things:

- The user selects one of the available apps to form a one-app workflow (multi-app workflow are a later worry).
- The user selects the input by navigating through the MMIF storage.
- The user defines a unique name for the job and then starts the job, which will run in the background as a separate process. This latter step will probably on work on Linux-like systems.

Next up is to make sure that apps are registered from available Docker container that are exposed on a port. This could be done by searching the list of active containers and pinging them to see any app metadata are volunteered.

Other things to do:

- Jobs overide prior results, perhaps add a flag as with the storage upload to allow/disallow overwrite.


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

- Would like to sort them on start time
- They are less fragile than they used to be, but should still consider using a Job class that reads the job file and perhaps some changes to the format and content of the job file: (1) separate lines to represent things like batch info, app name, parameters etcetera, (2) add a count of files to be processed (allows later inspection of the file to print a percentage done number). 
- Make sure that files like '.DS_store' and others that are not jobs will be skipped, should be done in ClamShack


### Other

Q: When initializing also create .env?<br/>
A: No, because than you overwrite the current one, but maybe create .env-shack

When loading a shack assets names and MMIF files names are loaded, but the latter are not updated when we run jobs.