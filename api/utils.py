import re
import sys
import json
from pathlib import Path


def load_json(fname: str) -> dict:
    return json.loads(Path(fname).read_text())    


def strip_prefix(prefix: str, path: Path) -> Path:
    return Path(*path.parts[len(Path(prefix).parts):])
