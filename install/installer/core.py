"""Selection, read-only detection, and fail-closed installation plans."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .manifest import FULL_COMMIT, ManifestError, SHA256


@dataclass(frozen=True)
class Detection:
    state: str
    reason: str
    version: str = "unknown"
    digest: str = "unknown"


@dataclass(frozen=True)
class PlanItem:
    ident: str
    method: str
    current: Detection
    result: str
    action: str
    reason: str
    estimated_bytes: int | None = None


def host_compatible() -> bool:
    return sys.platform == "darwin" and platform.machine() == "arm64"


def select(manifest: dict, *, profile: str = "standard", categories=(), names=()) -> list[str]:
    by_id = {tool["id"]: tool for tool in manifest["tools"]}
    if names:
        selected = set()
        for name in names:
            if name in by_id:
                selected.add(name)
            elif name in manifest.get("aliases", {}):
                selected.update(manifest["aliases"][name])
            else:
                raise ManifestError(f"unknown tool: {name}")
    elif categories:
        known_categories = {tool["category"] for tool in manifest["tools"]}
        unknown = set(categories) - known_categories
        if unknown:
            raise ManifestError(f"unknown category: {', '.join(sorted(unknown))}")
        selected = {tool["id"] for tool in manifest["tools"] if tool["category"] in categories}
    else:
        config = manifest.get("profiles", {}).get(profile)
        if not isinstance(config, dict):
            raise ManifestError(f"unknown profile: {profile}")
        selected = set(config.get("tools", []))
        if config.get("include_non_optional"):
            selected.update(tool["id"] for tool in manifest["tools"] if not tool["optional"])
        if config.get("include_all"):
            selected.update(by_id)
    ordered = []
    visited = set()

    def visit(ident: str) -> None:
        if ident in visited:
            return
        for dep in by_id[ident]["dependencies"]:
            visit(dep)
        visited.add(ident)
        ordered.append(ident)

    for ident in by_id:
        if ident in selected:
            visit(ident)
    return ordered


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _macho_arm64(path: Path) -> bool:
    # Thin, little-endian Mach-O. Universal files are left as unknown here.
    try:
        with path.open("rb") as stream:
            header = stream.read(8)
    except OSError:
        return False
    return len(header) == 8 and header[:4] == b"\xcf\xfa\xed\xfe" and int.from_bytes(header[4:], "little") == 0x0100000C


def _package_list_hash(env_dir: Path) -> str | None:
    lib = env_dir / "lib"
    if not lib.is_dir():
        return None
    sites = sorted(lib.glob("python*/site-packages"))
    if len(sites) != 1:
        return None
    packages = [(d.metadata.get("Name"), d.version) for d in importlib.metadata.distributions(path=[str(sites[0])])]
    packages = [(name, version) for name, version in packages if name]
    packages.sort(key=lambda item: (item[0].lower(), item[1]))
    canonical = "".join(
        f"{name.lower().replace('_', '-').replace('.', '-')}=={version}\n"
        for name, version in packages
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


class Detector:
    def __init__(self, root: Path, manifest: dict, lock: dict, runner=None, which=None):
        self.root, self.manifest, self.lock = root, manifest, lock
        self.project_root = root.parent if root.name == "install" else root
        self.runner = runner or self._run
        self.which = which or shutil.which
        self._brew = {}

    @staticmethod
    def _run(args: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(args, capture_output=True, text=True, timeout=20, check=False)

    def _brew_versions(self, kind: str) -> dict[str, str] | None:
        if kind in self._brew:
            return self._brew[kind]
        if not self.which("brew"):
            self._brew[kind] = None
            return None
        try:
            result = self.runner(["brew", "list", "--formula" if kind == "brew" else "--cask", "--versions"])
        except (OSError, subprocess.TimeoutExpired):
            self._brew[kind] = None
            return None
        if result.returncode:
            self._brew[kind] = None
            return None
        self._brew[kind] = {
            parts[0]: " ".join(parts[1:]) for line in result.stdout.splitlines()
            if (parts := line.split()) and len(parts) > 1
        }
        return self._brew[kind]

    def _env_path(self, env: str) -> Path | None:
        if env.startswith("uv-tool:"):
            return Path.home() / ".local/share/uv/tools" / env.split(":", 1)[1]
        if env in self.manifest.get("python_environment_locks", {}):
            return self.project_root / env
        return None

    def detect(self, tool: dict) -> Detection:
        ident, method = tool["id"], tool["install_method"]
        if not host_compatible():
            return Detection("incompatible", "host is not macOS arm64")
        if method == "wordlist-bundle":
            directory = self.project_root / "wordlists"
            if directory.is_symlink() or (directory.exists() and not directory.is_dir()):
                return Detection("incompatible", "wordlists destination is not a normal directory")
            if not self.which("git"):
                return Detection("unknown", "Git is required for pinned wordlists")
            missing = 0
            for repository in self.lock["wordlist_bundle"]["repositories"]:
                destination = directory / repository["name"]
                if destination.is_symlink():
                    return Detection("incompatible", "wordlist destination is a symlink")
                if not destination.exists():
                    missing += 1
                    continue
                if not destination.is_dir() or not (destination / ".git").exists():
                    return Detection("incompatible", "wordlist destination has unverified content")
                try:
                    head = self.runner(["git", "-C", str(destination), "rev-parse", "HEAD"])
                    dirty = self.runner(["git", "-C", str(destination), "status", "--porcelain"])
                except (OSError, subprocess.TimeoutExpired):
                    return Detection("unknown", "wordlist revision could not be read")
                if head.returncode or head.stdout.strip() != repository["revision"] or dirty.returncode or dirty.stdout.strip():
                    return Detection("incompatible", "wordlist revision differs or checkout has local changes")
            return Detection("missing" if missing else "verified", f"{missing} pinned wordlist repositories absent" if missing else "all pinned wordlist revisions match")
        if method == "docker-compose":
            compose = self._file_path(tool["executable"])
            if not compose or not compose.is_file():
                return Detection("missing", "Compose configuration absent")
            digest = tool.get("image_digest", "")
            if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest) or not tool.get("image"):
                return Detection("missing", "Compose exists; image digest is unconfirmed")
            if not self.which("docker"):
                return Detection("unknown", "Docker CLI unavailable")
            try:
                result = self.runner(["docker", "image", "inspect", f"{tool['image']}@{digest}"])
            except (OSError, subprocess.TimeoutExpired):
                return Detection("unknown", "Docker Engine unavailable")
            if result.returncode:
                return Detection("missing", "pinned Docker image absent")
            return Detection("verified", "pinned Docker image present")
        if tool["architecture"].startswith("windows"):
            path = self._file_path(tool["executable"])
            return Detection("installed" if path and path.exists() else "manual-required", "Windows artifact; no execution on macOS")
        if method in ("brew", "brew-cask"):
            versions = self._brew_versions(method)
            if versions is None:
                return Detection("unknown", "Homebrew unavailable or inventory unreadable")
            name = tool["source"].split(":", 1)[1]
            current = versions.get(name)
            if current is None:
                return Detection("missing", "not registered with Homebrew")
            expected = self.lock.get("brew", {}).get("formula" if method == "brew" else "cask", {}).get(name)
            if expected and current != expected:
                return Detection("incompatible", f"Homebrew version differs: observed {current}, locked {expected}", current)
            return Detection("verified", "Homebrew registration and version match", current)
        if method == "go-module":
            path = self.which(str(tool["executable"])) or str(Path.home() / "go/bin" / str(tool["executable"]))
            if not Path(path).is_file():
                return Detection("missing", "Go binary absent")
            if not os.access(path, os.X_OK):
                return Detection("broken", "Go binary is not executable")
            pin = self.lock.get("go_modules", {}).get(ident)
            if not pin:
                return Detection("unknown", "no Go module pin")
            try:
                result = self.runner(["go", "version", "-m", path])
            except (OSError, subprocess.TimeoutExpired):
                return Detection("unknown", "Go build metadata unavailable")
            fields = next((line.split("\t")[2:] for line in result.stdout.splitlines() if line.startswith("\tmod\t")), None)
            if result.returncode or not fields or len(fields) < 3:
                return Detection("unknown", "Go build metadata unreadable")
            if fields[:3] != [pin["module"], pin["version"], pin["sum"]]:
                return Detection("incompatible", "Go module version or checksum differs", fields[1])
            return Detection("verified", "Go module path, version and checksum match", fields[1], fields[2])
        env = tool.get("python_environment")
        if env and env in self.manifest.get("python_environment_locks", {}):
            env_path = self._env_path(env)
            if not env_path or not env_path.is_dir():
                return Detection("missing", "isolated Python environment absent")
            lock_path = self.root / self.manifest["python_environment_locks"][env]
            expected = json.loads(lock_path.read_text())["package_list_sha256"]
            observed = _package_list_hash(env_path)
            if observed is None:
                return Detection("unknown", "Python package metadata unreadable")
            if observed != expected:
                return Detection("incompatible", "Python package list differs from Level 2 snapshot")
            if ident == "netexec":
                candidates = list(env_path.glob("lib/python*/site-packages/nxc/cli.py"))
                target = self.lock.get("patch_records", {}).get("netexec", {}).get("patched_file_sha256")
                if len(candidates) != 1 or _sha(candidates[0]) != target:
                    return Detection("incompatible", "NetExec patch state differs; existing uv tool is protected")
            source_script = self._file_path(tool["executable"])
            if method == "python-venv-source" and source_script and source_script.is_file():
                return Detection("verified", "source script present and Python package list matches Level 2 snapshot")
            if not self._executable_present(tool["executable"]):
                return Detection("broken", "Python CLI entry point absent")
            return Detection("verified", "Python package list matches Level 2 snapshot (not artifact-verified)")
        paths = [part.strip() for part in str(tool["executable"]).split(";")]
        if tool["executable"] == "unknown":
            if method in ("brew", "brew-cask"):
                return Detection("unknown", "executable unspecified")
            return Detection("manual-required", "artifact or executable unspecified")
        found = [self._file_path(part) for part in paths]
        if not all(path is not None and path.exists() for path in found):
            return Detection("missing", "executable or source path absent")
        if any(path.is_file() and not os.access(path, os.X_OK) for path in found if path is not None) and method not in ("docker-compose", "docker-source", "repository-scripts", "source", "source-build", "source-cross-build"):
            return Detection("broken", "file is not executable")
        matched = 0
        for path in found:
            if path is None or not path.is_file():
                continue
            relative = path.relative_to(self.project_root).as_posix() if path.is_relative_to(self.project_root) else None
            artifact = self.lock.get("artifacts", {}).get(relative)
            if artifact:
                actual = _sha(path)
                if actual != artifact["sha256"]:
                    return Detection("incompatible", "artifact SHA-256 mismatch", digest=actual)
                matched += 1
                if method == "official-binary" and not _macho_arm64(path):
                    return Detection("incompatible", "official binary is not thin arm64 Mach-O")
        if method == "source-build" and ident == "havoc":
            return Detection("installed", "native binaries present; upstream source revision remains unknown")
        if matched == len(found):
            return Detection("verified", "local artifact SHA-256 matches snapshot (provenance unconfirmed)")
        return Detection("installed", "file or command present; version not verified")

    def _file_path(self, value: str) -> Path | None:
        if value == "unknown":
            return None
        if "/" in value or value.startswith("."):
            if value.startswith("/"):
                return Path(value)
            if value.startswith("c2/empire/"):
                return self.root / value
            return self.project_root / value
        selected = self.which(value)
        return Path(selected) if selected else None

    def _executable_present(self, value: str) -> bool:
        path = self._file_path(value)
        return bool(path and path.exists() and (path.is_dir() or os.access(path, os.X_OK)))


def capability(tool: dict, lock: dict, manifest: dict) -> tuple[str, str]:
    """Return automatic backend or a precise hold reason, without side effects."""
    method, ident = tool["install_method"], tool["id"]
    if method == "brew" and tool["source"].startswith("homebrew-core:") and tool["version"] != "unknown":
        return "brew", "catalog version must match before installation"
    if method == "go-module" and ident in lock.get("go_modules", {}):
        return "go", "module checksum must match before staged build"
    if method == "official-binary":
        url = tool.get("artifact_url")
        relative = tool["executable"]
        digest = lock.get("artifacts", {}).get(relative, {}).get("sha256")
        if isinstance(url, str) and url.startswith("https://") and digest and SHA256.fullmatch(digest):
            return "binary", "download to staging; verify SHA-256 and architecture"
        return "manual-required", "official release URL and trusted SHA-256 pair not established"
    if method == "docker-compose":
        digest = tool.get("image_digest", "")
        if re.fullmatch(r"sha256:[0-9a-f]{64}", digest) and tool.get("image"):
            return "docker", "pull image by digest; never start containers"
        return "manual-required", "image digest or image reference unconfirmed"
    if method in ("source", "source-build"):
        if FULL_COMMIT.fullmatch(tool["revision"]) and tool.get("source_dir") and ident not in manifest.get("patch_records", {}):
            return "git", "clone fixed revision to an absent destination"
        return "manual-required", "source revision, destination or patch base unconfirmed"
    if method in ("uv-tool", "uv-tool-git", "python-venv", "python-venv-source"):
        env = tool.get("python_environment")
        rel = manifest.get("python_environment_locks", {}).get(env)
        level = lock.get("python_locks", {}).get(next((key for key, value in lock.get("python_locks", {}).items() if value.get("file") == rel), ""), {}).get("reproducibility_level")
        return "manual-required", f"Python environment lock Level {level or 'unknown'}; artifact hashes and resolver pin absent"
    if method == "pipx":
        return "manual-required", "pipx environment has no artifact-verified lock; preserve existing installation"
    if method == "wordlist-bundle":
        return "wordlists", "clone missing repositories at locked commits; at least 16 GiB free required, actual download size unknown"
    if method == "brew-cask":
        return "manual-required", "GUI/Cask license and distribution conditions require review"
    return "manual-required", "manual or unsupported install method"


def build_plan(root: Path, manifest: dict, lock: dict, identifiers: list[str], detector: Detector) -> list[PlanItem]:
    by_id = {tool["id"]: tool for tool in manifest["tools"]}
    plan = []
    for ident in identifiers:
        tool = by_id[ident]
        detected = detector.detect(tool)
        method = tool["install_method"]
        if detected.state in ("verified", "installed"):
            result, action, reason = "skipped", "none", detected.reason
        elif detected.state in ("incompatible", "broken", "unknown"):
            result, action, reason = "blocked", "none", detected.reason
        elif detected.state == "manual-required":
            result, action, reason = "manual-required", "none", detected.reason
        else:
            backend, reason = capability(tool, lock, manifest)
            result = "ready" if backend != "manual-required" else "manual-required"
            action = backend if result == "ready" else "none"
        size = None
        if action == "binary":
            size = lock.get("artifacts", {}).get(tool["executable"], {}).get("size_bytes")
        plan.append(PlanItem(ident, method, detected, result, action, reason, size))
    by_plan = {item.ident: item for item in plan}
    final = []
    for item in plan:
        if item.result == "ready":
            unsatisfied = [
                dep for dep in by_id[item.ident]["dependencies"]
                if by_plan[dep].result in ("blocked", "manual-required")
            ]
            if unsatisfied:
                item = PlanItem(item.ident, item.method, item.current, "blocked", "none", "dependency unavailable: " + ", ".join(unsatisfied), item.estimated_bytes)
        final.append(item)
        by_plan[item.ident] = item
    return final
