# Notes on the current state of the repo

This code needs refactoring. Below are some of the problems.

In addition:

- some code should perhaps be refactored to mmif-python
- this could be its own package on PyPI


## Progress and changes

> While this list grows prose from below with proposed changes will be culled.

Structure was updated a bit, not quite using a clams\_datahousing package as suggested earlier but at least adding a sripts directory and refactoring the files inside the api directory (for now just the blueprints).

Dependencies:

- Removed the dependency on the local mmif-python archive.

Blueprints refactoring:

- Now using the following blueprints: api, assets, mmif\_download, mmif\_upload, www and experiments.
- The init file only has the very small api blueprint with the welcome message.
- Removed the complicated expression to parse the name of the module to get the import module.

More on blueprints:

- [https://adammking.medium.com/understanding-flask-blueprints-32d13f41e45a](https://adammking.medium.com/understanding-flask-blueprints-32d13f41e45a)
- [https://realpython.com/flask-blueprint/](https://realpython.com/flask-blueprint/)
- [https://blog.miguelgrinberg.com/post/the-flask-mega-tutorial-part-xv-a-better-application-structure](https://blog.miguelgrinberg.com/post/the-flask-mega-tutorial-part-xv-a-better-application-structure)
- [https://www.geeksforgeeks.org/python/flask-blueprints/](https://www.geeksforgeeks.org/python/flask-blueprints/)
- [https://oneuptime.com/blog/post/2026-01-27-flask-blueprints-modular/view](https://oneuptime.com/blog/post/2026-01-27-flask-blueprints-modular/view)

Unit tests:

- Updated tests to be more robust and work with only one temporary directory.


## Dependencies

Still depends on the local inspector archive, and it is also unclear what happens when we make changes to the storage-inspector interactions, maybe then reintroduing a new inspector archive is the easiest.


## Structure

The organization of the api directory is somewhat haphazard. The web service files seem to do a lot of stuff that should be done by some package that takes care of dealing with the storage. For example, many of the functions in mmif\_storage.py and www.py are dealing with setting parameters, manipulating app names and searching for MMIF files.

Taking it piece by piece:

- Blueprint **api**. This one is fine, it is in the init file and just returns a message.
- Blueprint **assets**. Its endpoint is just a search for assets, all the rest is guid manipulation, database functions, directory searching and checking. It allows the asset path to be a symlink.
- Blueprint **mmif\_upload**. Mostly alright, but upload\_mmif could use some attention.
- Blueprint **mmif\_download**. Not sure about mmif\_download and the rewind functionality.
- Blueprint **analytics**. One big function to collect all stats, at least factor that out.
- Blueprint **www**. Not as bad as I first thought, but check all routes for non-route logic and at least factor out the inspector code.
- Module **utils**. A coule of true utility funcitons but also classes ServerDirectory, ParameterFile and MmifFile. Those classes perhaps deserve their own module.

In general, separate routes from domain logic and have routes in their own files, perhaps inside a routes subdir, or maybe one subdir per blueprint where each blueprint has its own routes.py file.

Trying this with the assets blueprint first. Now it just does a search, it should probably have upload and download endpoints as well.

> Laptop should have something in the assets directory.


## Cleanup

Look at these directory names:

```
ASSET_DIR=/Users/Shared/aapb/assets
DOWNLOAD_DIR=/Users/Shared/aapb/downloads
STORAGE_DIR=/Users/Shared/aapb/mmif-storage-251016
```

The second one is not used (except for an in unused method in api.assets, see below).

The `prototype` has some yaml and json config files that do not appear to be used anywhere so they can be deleted or should at least be put elsewhere.

We do not need both the requirement files and the pyproject file since you can do

```bash
pip install .
```

But need to put pytest in an optional dependency.

Remove the following?

- wsgi.py (currently it does nothing)
- api.assets.aapb_generate does not seem to be used

Move the following?

- populate_*.py to scripts
- check_db.py to scripts

