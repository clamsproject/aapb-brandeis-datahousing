# Data Warehouse Developer Notes

Notes taken while working on the AAPB-Brandeis datahousing server.

[ [Indentifiers](notes-guids.md)
| [MMIF downloads](notes-mmif-downloads.md)
]


## Installation 

For local install see the end of the README file. Basically: (1) install requirements, (2) copy `.env.sample` into `.env` and edit as needed. The code use dotenv.load_dotenv() to set variables in os.environ.

Start the server with `flask run`.

To populate a database with all the files in the assets (as defined by ASSET_DIR in `.env`) you should set BUILD_DB to 1 and restart the server. It will then load all file paths. Set BUILD_DB back to 0 for your next run otherwise the database will be recreated every time you start the server.

> TODO: would like to do change the startup/setup so that you do not have to set and reset the BUILD_DB variable.


## Other comments


### Benchmarking

Loading all MMIF files from the main branch in aapb-evalualtion (about 1400, for 243Mb) took about 6 minutes.


### Automatic garbage collection

> "Given the power of rewind, we can always delete any intermediate MMIF, and keep only the files in the terminal subdirectory."

My suggestion is to not bother about this till until we know how much redundancy we are talking about. See [issue #19](https://github.com/clamsproject/aapb-brandeis-datahousing/issues/19).


### More

Return values are a bit mixed, sometimes a json structure, sometimes a string (which is JSON, but you get the point).
