"""Discover notebook tasks from the bundle and verify their local targets."""

from dataclasses import dataclass
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "databricks.yml"
EXPECTED_JOBS = {
    "landing_to_bronze",
    "bronze_to_silver",
    "silver_to_gold",
    "gold_to_mlflowprediction",
    "prediction_monitoring",
    "data_drift_monitoring",
}


@dataclass(frozen=True)
class Reference:
    file: Path
    job: str
    task: dict

    @property
    def label(self):
        return f"{self.file.relative_to(ROOT)} [{self.job}]: {self.task.get('notebook_path')!r}"

    def is_external(self):
        raw = self.task.get("notebook_path")
        return isinstance(raw, str) and (
            self.task.get("source") == "GIT"
            or raw.startswith(("/Workspace/", "/Users/", "/Shared/", "/Repos/", "${workspace."))
        )

    def local_path(self):
        raw = self.task.get("notebook_path")
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError(f"{self.label}: expected a nonempty notebook_path")
        # Git-source tasks and workspace notebooks have no local file to inspect.
        if self.is_external():
            return None
        path = (self.file.parent / raw).resolve()
        if not path.is_relative_to(ROOT):
            raise ValueError(f"{self.label}: resolves outside repository to {path}")
        if not path.is_file():
            raise ValueError(f"{self.label}: file does not exist at {path}")
        return path


def notebook_tasks(node, file, job=""):
    """Walk nested tasks and target overrides, keeping the declaring job key."""
    if isinstance(node, list):
        for item in node:
            yield from notebook_tasks(item, file, job)
    elif isinstance(node, dict):
        for key, value in node.items():
            if key == "jobs" and isinstance(value, dict):
                for name, definition in value.items():
                    yield from notebook_tasks(definition, file, name)
            elif key == "notebook_task":
                if not isinstance(value, dict):
                    raise ValueError(f"{file} [{job}]: notebook_task must be a mapping")
                yield Reference(file, job, value)
            else:
                yield from notebook_tasks(value, file, job)


def load_yaml(file):
    try:
        return yaml.safe_load(file.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"{file}: {exc}") from exc


RESOURCE_FILES = sorted(
    file for file in (ROOT / "resources").rglob("*")
    if file.is_file() and file.suffix.lower() in {".yml", ".yaml"}
)
REFERENCES = [
    ref for file in [BUNDLE, *RESOURCE_FILES]
    for ref in notebook_tasks(load_yaml(file), file)
]


def local_notebooks():
    """Only open checked paths. Reference failures are reported by their own test."""
    paths = set()
    for ref in REFERENCES:
        try:
            path = ref.local_path()
        except ValueError:
            continue
        if path is not None:
            paths.add(path)
    return sorted(paths)


def test_existing_jobs_are_covered():
    included = {BUNDLE}
    for pattern in load_yaml(BUNDLE).get("include", []):
        included.update(ROOT.glob(pattern))
    covered = {
        ref.job for ref in REFERENCES
        if ref.file in included and not ref.is_external()
    }
    assert not EXPECTED_JOBS - covered, f"Missing local notebook jobs: {EXPECTED_JOBS - covered}"


@pytest.mark.parametrize("ref", REFERENCES, ids=[ref.label for ref in REFERENCES])
def test_notebook_reference(ref):
    try:
        path = ref.local_path()
    except ValueError as exc:
        pytest.fail(str(exc), pytrace=False)
    if path is None:
        pytest.skip(f"{ref.label}: external notebook")
