Temporary directory with packages needed by this code, in particular by the
inspector. These potentially include:

- A newer version of mmif-python than stipulated in the project file. This is
  usually when a newer version of the summarizer is needed that is not available
  on PyPI.

- An initial version of the MMIF Inspector, which is also not available on PyPI.

Once the above packages are available on PyPI then this entire directory should be deleted.
