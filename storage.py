"""Phase 1 — atomic local JSON storage helpers.

Stdlib only and Streamlit-independent. Corrupted files are never
silently overwritten: loading raises StorageCorruptedError and leaves
the original file untouched for manual recovery.
"""

import json
import os
import tempfile
from pathlib import Path

import config


class StorageError(Exception):
    """Base storage error."""


class StorageCorruptedError(StorageError):
    """Raised when an existing JSON file cannot be parsed."""

    def __init__(self, path, original):
        super().__init__(f"Corrupted JSON at {path}: {original}")
        self.path = Path(path)
        self.original = original


def data_path(filename):
    """Return absolute Path for a file inside the project data dir."""
    root = Path(__file__).resolve().parent
    return root / config.DATA_DIR / filename


def store_path(store_name):
    """Map a logical store name (see config.STORES) to its file Path."""
    try:
        filename = config.STORES[store_name]
    except KeyError:
        raise StorageError(f"Unknown store: {store_name!r}") from None
    return data_path(filename)


def load_json(path, default):
    """Load JSON file, returning default when missing.

    Raises StorageCorruptedError (without modifying the file) when the
    file exists but is empty or contains invalid JSON.
    """
    path = Path(path)
    if not path.exists():
        return default
    try:
        text = path.read_text(encoding="utf-8")
        if not text.strip():
            raise StorageCorruptedError(path, "empty file")
        return json.loads(text)
    except StorageCorruptedError:
        raise
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise StorageCorruptedError(path, exc) from exc
    except OSError as exc:
        raise StorageError(f"Cannot read {path}: {exc}") from exc


def save_json(path, data):
    """Persist data as JSON atomically (temp file + os.replace + fsync)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=path.name + ".", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    return path


def load_store(store_name, default):
    """Load one of the config.STORES entries by logical name."""
    return load_json(store_path(store_name), default)


def save_store(store_name, data):
    """Save one of the config.STORES entries by logical name."""
    return save_json(store_path(store_name), data)
