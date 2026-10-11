"""Research experiment tests (the scripts under scripts/experiments) carry the ``experiment`` marker.

The default run excludes them (``addopts`` in pytest.ini); run them on demand with
``python -m pytest -m experiment`` or ``./scripts/test.sh experiments``.
"""
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent


def pytest_collection_modifyitems(items):
    for item in items:
        try:
            inside = Path(str(item.fspath)).resolve().is_relative_to(HERE)
        except (OSError, ValueError):
            inside = False
        if inside:
            item.add_marker(pytest.mark.experiment)
