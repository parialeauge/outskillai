"""Deployment packaging: one pinned dependency set, no unused libraries."""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMAGES = ("Dockerfile.backend", "Dockerfile.combined")
UNUSED = {"langchain-openai"}
COPY_LINE = re.compile(r"^COPY\s+(?P<args>.+)$")
REQ_LINE = re.compile(
    r"^(?P<name>[A-Za-z0-9._-]+)(?P<extra>\[[^\]]+\])?==(?P<version>[^\s#]+)$"
)
PYPROJECT_LINE = re.compile(
    r"^(?P<name>[A-Za-z0-9._-]+)(?P<extra>\[[^\]]+\])?==(?P<version>.+)$"
)


def _parse_requirements(path: Path) -> dict[str, str]:
    pins: dict[str, str] = {}
    for raw in path.read_text().splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith("-r "):
            continue
        match = REQ_LINE.match(line)
        assert match, f"unpinned or malformed requirements line: {raw!r}"
        key = match.group("name").lower() + (match.group("extra") or "")
        pins[key] = match.group("version")
    return pins


def _parse_pyproject_deps(items: list[str]) -> dict[str, str]:
    pins: dict[str, str] = {}
    for raw in items:
        match = PYPROJECT_LINE.match(raw)
        assert match, f"pyproject dependency must be pinned with ==: {raw!r}"
        key = match.group("name").lower() + (match.group("extra") or "")
        pins[key] = match.group("version")
    return pins


def _declared_packages() -> set[str]:
    """Top-level import roots pyproject ships, e.g. apps / backend / shared."""
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())
    patterns = project["tool"]["setuptools"]["packages"]["find"]["include"]
    return {pattern.rstrip("*") for pattern in patterns}


def _copied_sources(dockerfile: str) -> set[str]:
    """Source paths a Dockerfile copies from the build context."""
    sources: set[str] = set()
    for raw in dockerfile.splitlines():
        match = COPY_LINE.match(raw.strip())
        if not match:
            continue
        args = [arg for arg in match.group("args").split() if not arg.startswith("--")]
        if match.group("args").startswith("--from"):
            continue
        for src in args[:-1]:
            sources.add(src.strip("/").removeprefix("./"))
    return sources


def test_pyproject_runtime_pins_match_requirements():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())
    pyproject = _parse_pyproject_deps(project["project"]["dependencies"])
    requirements = _parse_requirements(ROOT / "requirements.txt")
    assert pyproject == requirements


def test_unused_libraries_are_not_declared():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())
    declared = {item.split("==", 1)[0].split("[", 1)[0].lower() for item in project["project"]["dependencies"]}
    requirements = {
        line.split("==", 1)[0].split("[", 1)[0].lower()
        for raw in (ROOT / "requirements.txt").read_text().splitlines()
        if (line := raw.split("#", 1)[0].strip()) and not line.startswith("-r ")
    }
    leftover = UNUSED & (declared | requirements)
    assert leftover == set(), f"unused libraries still declared: {sorted(leftover)}"


def test_docker_editable_install_does_not_reresolve_pins():
    for name in IMAGES:
        text = (ROOT / name).read_text()
        assert "pip install --no-cache-dir -r requirements.txt" in text
        assert "pip install --no-cache-dir --no-deps -e ." in text
        assert "pip install --no-cache-dir -e ." not in text.replace(
            "pip install --no-cache-dir --no-deps -e .", ""
        )


def test_declared_packages_exist_on_disk():
    for name in _declared_packages():
        assert (ROOT / name).is_dir(), f"pyproject declares {name} but the directory is missing"


def test_images_copy_every_declared_package():
    """A missed COPY still builds a green image that dies on the first import."""
    required = _declared_packages() | {"pyproject.toml", "requirements.txt", "langgraph.json"}
    for name in IMAGES:
        copied = _copied_sources((ROOT / name).read_text())
        missing = required - copied
        assert not missing, f"{name} never copies {sorted(missing)} into the image"


def test_deploy_files_do_not_copy_legacy_packages_dir():
    for name in IMAGES:
        text = (ROOT / name).read_text()
        assert "COPY packages " not in text
    assert "packages*" not in tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["setuptools"]["packages"]["find"]["include"]


def test_image_tags_match_project_version():
    version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    frontend = (ROOT / "frontend" / "package.json").read_text()
    assert f'"version": "{version}"' in frontend
    for name in ("docker-compose.yml", "docker-compose.backend.yml", "docker-compose.frontend.yml"):
        text = (ROOT / name).read_text()
        tags = re.findall(r"image:\s+pactlify(?:-backend|-frontend)?:([0-9]+\.[0-9]+\.[0-9]+)", text)
        assert tags, f"{name} has no pactlify image tag"
        assert set(tags) == {version}, f"{name} tags {tags} do not match pyproject {version}"


def test_editable_metadata_tracks_backend_package():
    """Stale pactlify.egg-info still lists packages/ and 0.4.0 after the rename."""
    top = ROOT / "pactlify.egg-info" / "top_level.txt"
    info = ROOT / "pactlify.egg-info" / "PKG-INFO"
    assert top.is_file(), "run pip install --no-deps -e . so deploy metadata exists"
    names = {line.strip() for line in top.read_text().splitlines() if line.strip()}
    assert "packages" not in names
    assert _declared_packages() <= names
    version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    assert f"Version: {version}" in info.read_text()


def test_vercel_is_frontend_only_not_a_fastapi_function():
    config = json.loads((ROOT / "vercel.json").read_text())
    assert "builds" not in config
    assert "routes" not in config
    assert "functions" not in config
    assert config["framework"] == "vite"
    assert config["outputDirectory"] == "frontend/dist"
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert "vercel" not in project.get("tool", {})
    ignore = (ROOT / ".vercelignore").read_text()
    assert "frontend/" in ignore
    assert (ROOT / "frontend" / "vercel.json").is_file()
    assert (ROOT / "scripts" / "build_package.sh").is_file()
