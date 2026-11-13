"""Parse each Python cell independently, without importing or running its code."""

import ast
import json
import re

import pytest

from test_bundle_references import ROOT, local_notebooks


MAGIC = re.compile(r"^(?:# MAGIC\s+)?(%%?[\w.]+|!(?!=)\S*)")


def code_cells():
    for path in local_notebooks():
        label = str(path.relative_to(ROOT))
        try:
            notebook = json.loads(path.read_text(encoding="utf-8"))
            metadata = notebook.get("metadata", {})
            databricks = metadata.get("application/vnd.databricks.v1+notebook", {})
            default = metadata.get("language_info", {}).get("name") or databricks.get("language", "python")
            cells = notebook["cells"]
            if not isinstance(cells, list):
                raise ValueError("expected a cells array")
            for index, cell in enumerate(cells):
                if cell["cell_type"] != "code":
                    continue
                cell_metadata = cell.get("metadata", {}).get("application/vnd.databricks.v1+cell", {})
                language = cell_metadata.get("language") or default
                yield pytest.param(
                    f"{label} cell {index}", "".join(cell["source"]), language,
                    id=f"{label}-cell-{index}",
                )
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
            # A malformed notebook must not prevent collection of the other tests.
            yield pytest.param(label, "", "", id=label, marks=pytest.mark.skip(
                reason=f"{label}: cannot inspect cells ({exc}); see format validation"
            ))


@pytest.mark.parametrize("label,source,language", list(code_cells()))
def test_python_syntax(label, source, language):
    for line in source.splitlines():
        stripped = line.strip()
        command = MAGIC.match(stripped)
        if command:
            pytest.skip(f"{label}: {command[1]} command")
        if stripped and not stripped.startswith("#"):
            break
    if language.lower() not in {"python", "python3"}:
        pytest.skip(f"{label}: {language} code cell")
    try:
        ast.parse(source, filename=label)
    except SyntaxError as exc:
        # Also recognize line magics mixed with Python. Checking the parser's
        # offending line avoids matching shell-like text inside Python strings.
        line = (exc.text or "").strip()
        command = MAGIC.match(line)
        if not command and exc.offset and exc.text:
            # IPython also accepts assignments such as files = !ls.
            prefix = exc.text[:exc.offset - 1].rstrip()
            if prefix.endswith("="):
                command = MAGIC.match(exc.text[exc.offset - 1:])
        if command:
            pytest.skip(f"{label}, line {exc.lineno}: {command[1]} command")
        pytest.fail(f"{label}, line {exc.lineno}: {exc.msg}\n{exc.text or ''}", pytrace=False)
