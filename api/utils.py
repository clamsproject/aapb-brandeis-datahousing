from pathlib import Path


def strip_prefix(prefix: str, path: Path) -> Path:
    return Path(*path.parts[len(Path(prefix).parts):])
