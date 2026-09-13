"""Reviewed data-only harness. Collection/import never executes an experiment.

Use the installed CLI for explicit fresh execution; this file is an inspectable
copy and is never dynamically imported by FaultLab's runner.
"""
from pathlib import Path


def test_bundle_inventory_is_data_only():
    from app.integrations.regression_runner import inspect_bundle
    bundle_directory = Path(__file__).resolve().parents[1]
    if not (bundle_directory / "manifest.json").is_file():
        import pytest
        pytest.skip("Installed template; no exported bundle selected")
    inspected = inspect_bundle(bundle_directory)
    assert inspected.bundle.export_version == "faultlab-regression/v1"
