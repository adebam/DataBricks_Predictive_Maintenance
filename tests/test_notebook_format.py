"""Check the on-disk notebook schema before nbformat can normalize it."""

import json

import nbformat
import pytest
from nbformat.validator import iter_validate

from test_bundle_references import ROOT, local_notebooks


NOTEBOOKS = local_notebooks()


@pytest.mark.parametrize("path", NOTEBOOKS, ids=[str(path.relative_to(ROOT)) for path in NOTEBOOKS])
def test_notebook_format(path):
    try:
        text = path.read_text(encoding="utf-8")
        raw = json.loads(text)
        if not isinstance(raw, dict) or not isinstance(raw.get("cells"), list):
            raise ValueError("expected a notebook object with a cells array")
        for error in iter_validate(raw):
            raise error
        ids = [cell["id"] for cell in raw["cells"] if "id" in cell]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate cell ID")
        nbformat.reads(text, as_version=nbformat.NO_CONVERT)
    except Exception as exc:
        pytest.fail(f"{path}: {exc}", pytrace=False)
