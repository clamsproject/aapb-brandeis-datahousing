"""

The run package takes care of all worries related to running a batch job.

This is where available apps are listed. In the final version this will inspect
either the list of running containers or allow the user so assign a host and port
to a app name. At the moment it just registers the fake apps.

"""

from api.run.app import run_tokenizer, run_spacy, run_swt
from api.run.app import run_job

APPS = {
	"tokenizer-v1": run_tokenizer,
	"spacy-v3": run_spacy,
	"swt-v7.0": run_swt
}