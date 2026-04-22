# Notes on the current state of the repo

This code needed refactoring. These are some notes reflecting what was done.

In addition:

- some code should perhaps be refactored to mmif-python
- this might be its own package on PyPI


## Progress and changes

The code structure was updated, not quite using a clams\_datahousing package as suggested earlier but at least adding a scripts directory and refactoring the files inside the api directory.

Blueprints refactoring:

- Now using the following blueprints: api, assets, mmif\_download, mmif\_upload, www and experiments.
- All blueprints are created in their own file.
- Removed the complicated expression to parse the name of the module to get the import module.
- Most routes were moved to `api.routes` with the exception of the routes for the webpage and the exepriments.

Unit tests:

- Updated tests to be more robust and work with only one temporary directory.

Overal structure:

- Separated routes and domain logic. Now every route accesses some domain logic which could also be accessed locally from the command line.
- The one exception is the www blueprint, where the the GUI code still has some domain logic in it.

Dependencies:

- Dependency on the mmif-python package in `/packages` was removed.
- Still depends on the local inspector archive.
- It is also unclear what happens when we make changes to the storage-inspector interactions, maybe then reintroduing a new package is the easiest.

Cleanup:

- Removed the DOWNLOAD\_DIR environment variable.
- Removed the `prototype` directory which had some yaml and json config files for tests that are not in this repo.
- Removed some code that did not seem to have a purpose anymore. 
- Moved some non-api scripts into a separate directory.

Other:

- Renamed `wsgi.py` into `app_production.py` because with the former you would do a full database build each time you type `flask --help`. Also changed the imports so it works after the refactoring.
- Changed `baapb-datahousing.container` so that it loads the right app.


## Remaining issues

We do not need both the requirement files and the pyproject file since you can do `pip install .`. But using requirements files has been our approach so far and we have no current plans to change that. 

Perhaps part of the code or all of the code in `api/utils.py` should be moved.

Documentation may have to be updated.

I did not test the interaction of `app_production.py` and `baapb-datahousing.container`. It might also make sense to not always create the entire database. Probably connected to this is that the location of the database is now hardwired to `api/database.db`, would like to consider using another environment setting for this.