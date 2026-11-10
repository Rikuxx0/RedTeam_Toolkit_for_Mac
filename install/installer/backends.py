"""Small, explicit installation backends. No tool execution or service startup."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from .core import Detector, PlanItem, _macho_arm64


class InstallError(RuntimeError):
    def __init__(self, reason: str, result: str = "blocked"):
        super().__init__(reason)
        self.result = result


@dataclass(frozen=True)
class InstallResult:
    ident: str
    result: str
    reason: str
    hash_result: str = "not-applicable"


def _run(args: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, check=False, timeout=3600, **kwargs)


def _checked(runner, args: list[str], **kwargs) -> subprocess.CompletedProcess:
    try:
        result = runner(args, **kwargs)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise InstallError(f"{args[0]} could not complete: {type(exc).__name__}", "failed") from exc
    if result.returncode:
        raise InstallError(f"{args[0]} exited with status {result.returncode}", "failed")
    return result


def _safe_repo_destination(root: Path, relative: str) -> Path:
    if Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise InstallError("unsafe destination")
    result = (root / relative).resolve()
    if not result.is_relative_to(root.resolve()):
        raise InstallError("destination escapes repository")
    return result


def _publish_no_replace(source: Path, destination: Path) -> None:
    """Copy within destination volume, then link atomically without replacement."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() or destination.is_symlink():
        raise InstallError("destination appeared during installation")
    with tempfile.NamedTemporaryFile(prefix=".installer-", dir=destination.parent, delete=False) as temporary:
        staged = Path(temporary.name)
        try:
            with source.open("rb") as stream:
                shutil.copyfileobj(stream, temporary)
            temporary.flush()
            os.fsync(temporary.fileno())
        except Exception:
            staged.unlink(missing_ok=True)
            raise
    try:
        staged.chmod(source.stat().st_mode & 0o777)
        os.link(staged, destination)
    except FileExistsError as exc:
        raise InstallError("destination appeared during installation") from exc
    finally:
        staged.unlink(missing_ok=True)


class Backends:
    def __init__(self, root: Path, manifest: dict, lock: dict, runner=None, fetcher=None):
        self.root, self.manifest, self.lock = root, manifest, lock
        self.project_root = root.parent if root.name == "install" else root
        self.runner = runner or _run
        self.fetcher = fetcher or urllib.request.urlopen

    def execute(self, item: PlanItem, tool: dict) -> InstallResult:
        if item.result != "ready":
            return InstallResult(item.ident, item.result, item.reason)
        # Recheck immediately before writing. A newly appeared file is never replaced.
        current = Detector(self.root, self.manifest, self.lock).detect(tool)
        if current.state in ("verified", "installed"):
            return InstallResult(item.ident, "skipped", "already present at execution time")
        if current.state != "missing":
            return InstallResult(item.ident, "blocked", "state changed before installation: " + current.reason)
        try:
            if item.action == "brew":
                return self._brew(tool)
            if item.action == "go":
                return self._go(tool)
            if item.action == "binary":
                return self._binary(tool)
            if item.action == "docker":
                return self._docker(tool)
            if item.action == "git":
                return self._git(tool)
            raise InstallError("unsupported backend")
        except InstallError as exc:
            return InstallResult(item.ident, exc.result, str(exc))

    def _brew(self, tool: dict) -> InstallResult:
        name = tool["source"].split(":", 1)[1]
        expected = tool.get("brew_version", tool["version"])
        env = os.environ.copy()
        env["HOMEBREW_NO_AUTO_UPDATE"] = "1"
        info = _checked(self.runner, ["brew", "info", "--json=v2", "--formula", name], env=env)
        try:
            record = json.loads(info.stdout)["formulae"][0]
            stable = record["versions"]["stable"]
            revision = int(record.get("revision", 0))
            candidate = stable + (f"_{revision}" if revision else "")
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise InstallError("Homebrew catalog version unreadable") from exc
        if candidate != expected:
            raise InstallError(f"Homebrew catalog version {candidate} differs from lock {expected}")
        dependencies = _checked(self.runner, ["brew", "deps", "--formula", name], env=env)
        outdated = _checked(self.runner, ["brew", "outdated", "--formula", "--json=v2"], env=env)
        try:
            outdated_names = {entry["name"] for entry in json.loads(outdated.stdout)["formulae"]}
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise InstallError("Homebrew outdated dependency inventory unreadable") from exc
        if set(dependencies.stdout.splitlines()) & outdated_names:
            raise InstallError("existing Homebrew dependency is outdated; refusing implicit upgrade")
        _checked(self.runner, ["brew", "install", "--formula", name], env=env)
        return InstallResult(tool["id"], "success", "Homebrew formula installed at locked catalog version", "Homebrew-managed")

    def _go(self, tool: dict) -> InstallResult:
        pin = self.lock["go_modules"][tool["id"]]
        module, version = pin["module"], pin["version"]
        env = os.environ.copy()
        env["GOTOOLCHAIN"] = "local"
        metadata = _checked(self.runner, ["go", "mod", "download", "-json", f"{module}@{version}"], env=env)
        try:
            observed = json.loads(metadata.stdout)["Sum"]
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise InstallError("Go module checksum unavailable") from exc
        if observed != pin["sum"]:
            raise InstallError("Go module checksum mismatch")
        dest = Path.home() / "go/bin" / tool["executable"]
        if dest.exists() or dest.is_symlink():
            raise InstallError("Go binary destination already exists")
        with tempfile.TemporaryDirectory(prefix="redteam-go-") as directory:
            staged_bin = Path(directory) / "bin"
            staged_bin.mkdir()
            env["GOBIN"] = str(staged_bin)
            env["GOOS"] = "darwin"
            env["GOARCH"] = "arm64"
            _checked(self.runner, ["go", "install", f"{module}@{version}"], env=env)
            built = staged_bin / tool["executable"]
            if not built.is_file() or not _macho_arm64(built):
                raise InstallError("staged Go output missing or not arm64 Mach-O", "failed")
            _publish_no_replace(built, dest)
        return InstallResult(tool["id"], "success", "fixed Go module built into an absent destination", "Go module sum matched")

    def _binary(self, tool: dict) -> InstallResult:
        relative = tool["executable"]
        dest = _safe_repo_destination(self.project_root, relative)
        if dest.exists() or dest.is_symlink():
            raise InstallError("binary destination already exists")
        expected = self.lock["artifacts"][relative]["sha256"]
        url = tool["artifact_url"]
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.hostname not in {"github.com", "raw.githubusercontent.com"} or parsed.username or parsed.password or parsed.query:
            raise InstallError("untrusted binary URL")
        with tempfile.TemporaryDirectory(prefix="redteam-binary-") as directory:
            staged = Path(directory) / "download"
            digest = hashlib.sha256()
            size = 0
            try:
                response = self.fetcher(url, timeout=60)
                final = urlsplit(response.geturl())
                if final.scheme != "https" or final.hostname not in {"github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com", "raw.githubusercontent.com"}:
                    raise InstallError("binary download redirected to an untrusted host")
                with response, staged.open("wb") as output:
                    for block in iter(lambda: response.read(1024 * 1024), b""):
                        size += len(block)
                        if size > 2 * 1024**3:
                            raise InstallError("binary exceeds 2 GiB safety cap")
                        output.write(block)
                        digest.update(block)
            except OSError as exc:
                raise InstallError("binary download failed", "failed") from exc
            if digest.hexdigest() != expected:
                raise InstallError("binary SHA-256 mismatch")
            if not _macho_arm64(staged):
                raise InstallError("download is not thin arm64 Mach-O")
            staged.chmod(0o755)
            _publish_no_replace(staged, dest)
        return InstallResult(tool["id"], "success", "verified official binary placed without replacement", "SHA-256 matched")

    def _docker(self, tool: dict) -> InstallResult:
        compose = _safe_repo_destination(self.root, tool["executable"])
        if not compose.is_file():
            raise InstallError("Compose file missing")
        _checked(self.runner, ["docker", "compose", "-f", str(compose), "config", "--quiet"])
        config = _checked(self.runner, ["docker", "compose", "-f", str(compose), "config", "--format", "json"])
        try:
            services = json.loads(config.stdout)["services"]
            for service in services.values():
                for port in service.get("ports", []):
                    if port.get("host_ip") not in ("127.0.0.1", "::1"):
                        raise InstallError("Compose publishes a non-localhost port")
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise InstallError("Compose published ports could not be verified") from exc
        image = f"{tool['image']}@{tool['image_digest']}"
        _checked(self.runner, ["docker", "pull", image])
        return InstallResult(tool["id"], "success", "digest-pinned image fetched; no container started", "digest pinned")

    def _git(self, tool: dict) -> InstallResult:
        if not re.fullmatch(r"[0-9a-f]{40}", tool["revision"]):
            raise InstallError("Git revision is not a full commit")
        dest = _safe_repo_destination(self.project_root, tool["source_dir"])
        if dest.exists() or dest.is_symlink():
            raise InstallError("Git destination already exists")
        dest.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".installer-git-", dir=dest.parent) as directory:
            checkout = Path(directory) / "checkout"
            _checked(self.runner, ["git", "clone", "--no-checkout", tool["source"], str(checkout)])
            _checked(self.runner, ["git", "-C", str(checkout), "checkout", "--detach", tool["revision"]])
            head = _checked(self.runner, ["git", "-C", str(checkout), "rev-parse", "HEAD"]).stdout.strip()
            if head != tool["revision"] or (checkout / ".gitmodules").exists():
                raise InstallError("Git revision mismatch or unpinned submodules")
            if dest.exists() or dest.is_symlink():
                raise InstallError("Git destination appeared during clone")
            checkout.rename(dest)
        return InstallResult(tool["id"], "success", "fixed Git revision placed in absent directory", "commit matched")
