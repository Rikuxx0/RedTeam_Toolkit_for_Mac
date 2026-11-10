"""Read the repository's deliberately small YAML subset without bootstrap packages.

The manifest uses one-line flow collections and indented mappings. Unsupported
YAML syntax fails closed; this is not a general YAML parser or code evaluator.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlsplit


class ManifestError(ValueError):
    pass


METHODS = {
    "brew", "brew-cask", "uv-tool", "uv-tool-git", "pipx", "python-venv",
    "python-venv-source", "go-module", "source-build", "source",
    "source-cross-build", "official-binary", "docker-compose",
    "docker-source", "manual-application", "manual-verified-artifact",
    "manual-go-binary", "repository-scripts", "framework", "xcode",
    "mixed", "unknown", "optional", "wordlist-bundle",
}
REQUIRED = {
    "id", "name", "category", "install_method", "source", "version",
    "revision", "architecture", "executable", "install_scope",
    "dependencies", "optional", "status", "verification", "notes",
}
STATUSES = {"installed", "verified", "missing", "broken", "unknown"}
SHA256 = re.compile(r"^[0-9a-f]{64}$")
FULL_COMMIT = re.compile(r"^[0-9a-f]{40}$")


class _Flow:
    def __init__(self, text: str):
        self.text, self.pos = text, 0

    def _space(self) -> None:
        while self.pos < len(self.text) and self.text[self.pos].isspace():
            self.pos += 1

    def _quoted(self) -> str:
        quote = self.text[self.pos]
        start = self.pos
        self.pos += 1
        if quote == "'":
            parts = []
            while self.pos < len(self.text):
                char = self.text[self.pos]
                self.pos += 1
                if char == "'":
                    if self.pos < len(self.text) and self.text[self.pos] == "'":
                        parts.append("'")
                        self.pos += 1
                    else:
                        return "".join(parts)
                else:
                    parts.append(char)
            raise ManifestError("unterminated single-quoted string")
        escaped = False
        while self.pos < len(self.text):
            char = self.text[self.pos]
            self.pos += 1
            if char == '"' and not escaped:
                try:
                    return json.loads(self.text[start:self.pos])
                except json.JSONDecodeError as exc:
                    raise ManifestError("unsupported double-quoted YAML string") from exc
            if char == "\\" and not escaped:
                escaped = True
            else:
                escaped = False
        raise ManifestError("unterminated double-quoted string")

    def value(self):
        self._space()
        if self.pos >= len(self.text):
            raise ManifestError("empty YAML value")
        char = self.text[self.pos]
        if char in "'\"":
            return self._quoted()
        if char == "[":
            self.pos += 1
            result = []
            self._space()
            if self._eat("]"):
                return result
            while True:
                result.append(self.value())
                self._space()
                if self._eat("]"):
                    return result
                if not self._eat(","):
                    raise ManifestError("expected comma in list")
        if char == "{":
            self.pos += 1
            result = {}
            self._space()
            if self._eat("}"):
                return result
            while True:
                self._space()
                key_start = self.pos
                while self.pos < len(self.text) and self.text[self.pos] != ":":
                    if self.text[self.pos] in "{},[]":
                        raise ManifestError("invalid flow mapping key")
                    self.pos += 1
                if self.pos == len(self.text):
                    raise ManifestError("missing flow mapping colon")
                key = self.text[key_start:self.pos].strip()
                if not key or key in result:
                    raise ManifestError("empty or duplicate flow mapping key")
                self.pos += 1
                result[key] = self.value()
                self._space()
                if self._eat("}"):
                    return result
                if not self._eat(","):
                    raise ManifestError("expected comma in mapping")
        start = self.pos
        while self.pos < len(self.text) and self.text[self.pos] not in ",]}":
            self.pos += 1
        token = self.text[start:self.pos].strip()
        if not token or token.startswith(("!", "&", "*")):
            raise ManifestError("unsupported YAML token")
        if token in ("true", "false"):
            return token == "true"
        if token in ("null", "~"):
            return None
        if re.fullmatch(r"-?\d+", token):
            return int(token)
        return token

    def _eat(self, expected: str) -> bool:
        self._space()
        if self.pos < len(self.text) and self.text[self.pos] == expected:
            self.pos += 1
            return True
        return False


def _value(text: str):
    parser = _Flow(text)
    result = parser.value()
    parser._space()
    if parser.pos != len(text):
        raise ManifestError("trailing YAML data")
    return result


def _pair(line: str) -> tuple[str, str]:
    # A key such as "uv-tool:netexec" contains a colon of its own.
    if ": " in line:
        return tuple(line.split(": ", 1))
    if line.endswith(":"):
        return line[:-1], ""
    raise ManifestError("missing mapping delimiter")


def parse_manifest(text: str) -> dict:
    root = {}
    section = None
    child = None
    for number, raw in enumerate(text.splitlines(), 1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if "\t" in raw[: len(raw) - len(raw.lstrip())]:
            raise ManifestError(f"line {number}: tab indentation")
        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()
        try:
            if indent == 0:
                if ":" not in line:
                    raise ManifestError("missing top-level colon")
                key, rest = _pair(line)
                if key in root:
                    raise ManifestError("duplicate top-level key")
                section, child = key, None
                root[key] = _value(rest.strip()) if rest.strip() else ([] if key == "tools" else {})
            elif indent == 2 and section == "tools" and line.startswith("- "):
                root["tools"].append(_value(line[2:]))
            elif indent == 2 and isinstance(root.get(section), dict):
                key, rest = _pair(line)
                if key in root[section]:
                    raise ManifestError("duplicate section key")
                if rest.strip():
                    root[section][key] = _value(rest.strip())
                    child = None
                else:
                    root[section][key] = {}
                    child = key
            elif indent == 4 and child is not None:
                key, rest = line.split(":", 1)
                if key in root[section][child]:
                    raise ManifestError("duplicate nested key")
                root[section][child][key] = _value(rest.strip())
            else:
                raise ManifestError("unsupported indentation or collection")
        except (ValueError, IndexError) as exc:
            raise ManifestError(f"line {number}: {exc}") from exc
    return root


def _repo_file(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise ManifestError(f"invalid repository path: {relative!r}")
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ManifestError(f"path escapes repository: {relative}")
    return path


def _safe_source(source: str) -> bool:
    if source in ("unknown", "Apple") or source.startswith(("homebrew-core:", "homebrew-cask:")):
        return True
    if source.startswith("github.com/"):
        return "@" not in source and ".." not in source
    if source.startswith("https://"):
        parsed = urlsplit(source)
        return parsed.hostname in {"github.com", "raw.githubusercontent.com"} and not (
            parsed.username or parsed.password or parsed.query or parsed.fragment
        )
    return False


def load(root: Path) -> tuple[dict, dict]:
    root = root.resolve()
    manifest_path = root / "manifests/tools.yaml"
    lock_path = root / "manifests/versions.lock"
    manifest = parse_manifest(manifest_path.read_text(encoding="utf-8"))
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    validate(root, manifest, lock)
    return manifest, lock


def validate(root: Path, manifest: dict, lock: dict) -> None:
    if manifest.get("schema_version") != 1 or lock.get("schema_version") != 1:
        raise ManifestError("unsupported schema_version")
    if manifest.get("platform") != "darwin-arm64" or lock.get("platform") != "darwin-arm64":
        raise ManifestError("unsupported manifest platform")
    tools = manifest.get("tools")
    if not isinstance(tools, list) or not tools:
        raise ManifestError("tools must be a non-empty list")
    by_id = {}
    for tool in tools:
        if not isinstance(tool, dict) or REQUIRED - set(tool):
            raise ManifestError("tool missing required attributes")
        ident = tool["id"]
        if not isinstance(ident, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", ident):
            raise ManifestError("invalid tool id")
        if ident in by_id:
            raise ManifestError(f"duplicate tool id: {ident}")
        by_id[ident] = tool
        if tool["install_method"] not in METHODS or tool["status"] not in STATUSES:
            raise ManifestError(f"invalid method/status: {ident}")
        if not isinstance(tool["version"], str) or not isinstance(tool["revision"], str):
            raise ManifestError(f"version/revision must be strings: {ident}")
        if not isinstance(tool["optional"], bool) or not isinstance(tool["dependencies"], list):
            raise ManifestError(f"invalid optional/dependencies: {ident}")
        if not isinstance(tool["notes"], list) or not isinstance(tool["verification"], dict):
            raise ManifestError(f"invalid notes/verification: {ident}")
        if not _safe_source(tool["source"]):
            raise ManifestError(f"unsafe source: {ident}")
        if tool["install_method"] in ("brew", "brew-cask"):
            expected_prefix = "homebrew-core:" if tool["install_method"] == "brew" else "homebrew-cask:"
            if not tool["source"].startswith(expected_prefix):
                raise ManifestError(f"invalid Homebrew source: {ident}")
            name = tool["source"].split(":", 1)[1]
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9@+_.-]*", name):
                raise ManifestError(f"invalid Homebrew package name: {ident}")
            kind = "formula" if tool["install_method"] == "brew" else "cask"
            if lock.get("brew", {}).get(kind, {}).get(name) != tool.get("brew_version", tool["version"]):
                raise ManifestError(f"Homebrew version lock mismatch: {ident}")
        if tool["install_method"] == "go-module":
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", tool["executable"]):
                raise ManifestError(f"invalid Go executable name: {ident}")
        if tool["install_method"] == "official-binary":
            _repo_file(root, tool["executable"])
        if tool["install_method"] == "docker-compose" and tool.get("image"):
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/:\-]*", tool["image"]):
                raise ManifestError(f"invalid Docker image reference: {ident}")
        for part in str(tool["executable"]).split(";"):
            part = part.strip()
            if not part or "\x00" in part or ".." in Path(part).parts:
                raise ManifestError(f"unsafe executable: {ident}")
        recorded = lock.get("tools", {}).get(ident)
        if not recorded or any(recorded.get(key) != tool[key] for key in ("version", "revision", "status")):
            raise ManifestError(f"versions.lock mismatch: {ident}")
    if set(lock.get("tools", {})) != set(by_id):
        raise ManifestError("versions.lock tool ID set mismatch")
    for tool in tools:
        if any(dep not in by_id for dep in tool["dependencies"]):
            raise ManifestError(f"undefined dependency: {tool['id']}")
    visiting, visited = set(), set()
    def visit(ident: str) -> None:
        if ident in visiting:
            raise ManifestError(f"dependency cycle at {ident}")
        if ident in visited:
            return
        visiting.add(ident)
        for dep in by_id[ident]["dependencies"]:
            visit(dep)
        visiting.remove(ident)
        visited.add(ident)
    for ident in by_id:
        visit(ident)
    for profile, config in manifest.get("profiles", {}).items():
        if not isinstance(config, dict) or any(x not in by_id for x in config.get("tools", [])):
            raise ManifestError(f"invalid profile: {profile}")
    for alias, targets in manifest.get("aliases", {}).items():
        if alias in by_id or not isinstance(targets, list) or any(x not in by_id for x in targets):
            raise ManifestError(f"invalid tool alias: {alias}")
    for env, rel in manifest.get("python_environment_locks", {}).items():
        path = _repo_file(root, rel)
        if not path.is_file():
            raise ManifestError(f"missing Python lock: {env}")
        entries = [x for x in lock.get("python_locks", {}).values() if x.get("file") == rel]
        if len(entries) != 1 or not SHA256.fullmatch(entries[0].get("sha256", "")):
            raise ManifestError(f"invalid Python lock record: {env}")
        if hashlib.sha256(path.read_bytes()).hexdigest() != entries[0]["sha256"]:
            raise ManifestError(f"Python lock hash mismatch: {env}")
    for ident, record in manifest.get("patch_records", {}).items():
        if ident not in by_id:
            raise ManifestError(f"patch target absent: {ident}")
        rel = record.get("file") or record.get("record")
        path = _repo_file(root, rel)
        expected = lock.get("patch_records", {}).get(ident, {}).get("sha256", "")
        if not path.is_file() or not SHA256.fullmatch(expected) or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ManifestError(f"patch hash mismatch: {ident}")
    for rel, artifact in lock.get("artifacts", {}).items():
        _repo_file(root, rel)
        if not SHA256.fullmatch(artifact.get("sha256", "")):
            raise ManifestError(f"invalid artifact hash: {rel}")
    for ident, pin in lock.get("go_modules", {}).items():
        if ident not in by_id or by_id[ident]["install_method"] != "go-module":
            raise ManifestError(f"invalid Go pin: {ident}")
        if not re.fullmatch(r"h1:[A-Za-z0-9+/]{43}=", pin.get("sum", "")):
            raise ManifestError(f"invalid Go checksum: {ident}")
        if pin.get("module") != by_id[ident]["source"]:
            raise ManifestError(f"Go module path mismatch: {ident}")
        expected_version = by_id[ident]["version"]
        if pin.get("version") not in (expected_version, "v" + expected_version):
            raise ManifestError(f"Go module version mismatch: {ident}")
    bundle = lock.get("wordlist_bundle")
    wordlist_tools = [tool for tool in tools if tool["install_method"] == "wordlist-bundle"]
    if wordlist_tools:
        if len(wordlist_tools) != 1 or wordlist_tools[0]["id"] != "wordlists" or not isinstance(bundle, dict):
            raise ManifestError("invalid wordlist bundle definition")
        if not isinstance(bundle.get("minimum_free_bytes"), int) or bundle["minimum_free_bytes"] < 8 * 1024**3:
            raise ManifestError("invalid wordlist free-space reserve")
        repositories = bundle.get("repositories")
        if not isinstance(repositories, list) or not repositories or len(repositories) > 32:
            raise ManifestError("invalid wordlist repository list")
        names = set()
        for repository in repositories:
            if not isinstance(repository, dict) or set(repository) != {"name", "url", "revision"}:
                raise ManifestError("invalid wordlist repository record")
            name, url, revision = repository["name"], repository["url"], repository["revision"]
            parsed = urlsplit(url) if isinstance(url, str) else None
            if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", name) or name in names:
                raise ManifestError("invalid wordlist destination")
            names.add(name)
            if not parsed or parsed.scheme != "https" or parsed.hostname != "github.com" or parsed.username or parsed.password or parsed.query or parsed.fragment or not re.fullmatch(r"/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\.git", parsed.path):
                raise ManifestError("invalid wordlist source URL")
            if not isinstance(revision, str) or not FULL_COMMIT.fullmatch(revision):
                raise ManifestError("invalid wordlist revision")
    elif bundle is not None:
        raise ManifestError("orphaned wordlist bundle lock")
