"""Offline installer tests. No package manager or C2 operation is performed."""

import copy
import hashlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from contextlib import redirect_stdout
from unittest.mock import patch

from installer.backends import Backends, InstallError
from installer.core import Detection, Detector, build_plan, capability, select
from installer.manifest import ManifestError, load, parse_manifest, validate
from installer.main import main


ROOT = Path(__file__).resolve().parents[2]


class FixedDetector:
    def __init__(self, states):
        self.states = states

    def detect(self, tool):
        return self.states.get(tool["id"], Detection("missing", "fixture absent"))


class ManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest, cls.lock = load(ROOT)

    def test_real_manifest_and_locks(self):
        self.assertEqual(len(self.manifest["tools"]), 109)
        self.assertEqual(len({t["id"] for t in self.manifest["tools"]}), 109)
        self.assertEqual(set(self.lock["tools"]), {t["id"] for t in self.manifest["tools"]})

    def test_parser_rejects_unsafe_yaml(self):
        with self.assertRaises(ManifestError):
            parse_manifest("schema_version: !python/object/apply:os.system []\n")

    def test_duplicate_id(self):
        m = copy.deepcopy(self.manifest)
        m["tools"].append(copy.deepcopy(m["tools"][0]))
        with self.assertRaisesRegex(ManifestError, "duplicate tool id"):
            validate(ROOT, m, self.lock)

    def test_missing_required_attribute(self):
        m = copy.deepcopy(self.manifest)
        del m["tools"][0]["source"]
        with self.assertRaisesRegex(ManifestError, "missing required"):
            validate(ROOT, m, self.lock)

    def test_unsafe_backend_arguments(self):
        m = copy.deepcopy(self.manifest)
        next(t for t in m["tools"] if t["id"] == "kerbrute")["executable"] = "/tmp/unwanted"
        with self.assertRaisesRegex(ManifestError, "invalid Go executable"):
            validate(ROOT, m, self.lock)
        m = copy.deepcopy(self.manifest)
        next(t for t in m["tools"] if t["id"] == "nmap")["source"] = "homebrew-core:--cleanup"
        with self.assertRaisesRegex(ManifestError, "invalid Homebrew package"):
            validate(ROOT, m, self.lock)

    def test_undefined_dependency_and_cycle(self):
        m = copy.deepcopy(self.manifest)
        m["tools"][0]["dependencies"] = ["nonexistent"]
        with self.assertRaisesRegex(ManifestError, "undefined dependency"):
            validate(ROOT, m, self.lock)
        m = copy.deepcopy(self.manifest)
        sliver = next(t for t in m["tools"] if t["id"] == "sliver-server")
        sliver["dependencies"] = ["sliver-client"]
        client = next(t for t in m["tools"] if t["id"] == "sliver-client")
        client["dependencies"] = ["sliver-server"]
        with self.assertRaisesRegex(ManifestError, "cycle"):
            validate(ROOT, m, self.lock)

    def test_lock_hash_mismatch(self):
        lock = copy.deepcopy(self.lock)
        key = next(iter(lock["python_locks"]))
        lock["python_locks"][key]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ManifestError, "Python lock hash mismatch"):
            validate(ROOT, self.manifest, lock)

    def test_profile_and_alias_selection(self):
        minimal = select(self.manifest, profile="minimal")
        standard = select(self.manifest, profile="standard")
        full = select(self.manifest, profile="full")
        self.assertEqual(len(minimal), 6)
        self.assertGreater(len(standard), len(minimal))
        self.assertEqual(len(full), 109)
        self.assertEqual(select(self.manifest, names=["sliver"]), ["sliver-server", "sliver-client"])
        self.assertEqual(len(select(self.manifest, categories=["c2"])), 10)  # C2 plus runtime dependencies
        with self.assertRaises(ManifestError):
            select(self.manifest, names=["unknown-tool"])


class DetectionAndPlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest, cls.lock = load(ROOT)
        cls.by_id = {tool["id"]: tool for tool in cls.manifest["tools"]}

    def test_brew_version_mismatch(self):
        def fake(args):
            return subprocess.CompletedProcess(args, 0, "nmap 0.0.1\n", "")
        with patch("installer.core.host_compatible", return_value=True):
            detector = Detector(ROOT, self.manifest, self.lock, runner=fake, which=lambda name: "/fake/brew" if name == "brew" else None)
            result = detector.detect(self.by_id["nmap"])
        self.assertEqual(result.state, "incompatible")

    def test_binary_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            file = root / "bin/tool"
            file.parent.mkdir()
            file.write_bytes(b"wrong")
            file.chmod(0o755)
            tool = dict(self.by_id["sliver-server"], executable="bin/tool")
            lock = {"artifacts": {"bin/tool": {"sha256": "0" * 64}}}
            with patch("installer.core.host_compatible", return_value=True):
                result = Detector(root, self.manifest, lock).detect(tool)
            self.assertEqual(result.state, "incompatible")

    def test_existing_tool_is_skipped(self):
        ids = select(self.manifest, names=["nmap"])
        plan = build_plan(ROOT, self.manifest, self.lock, ids, FixedDetector({"nmap": Detection("verified", "same version")}))
        self.assertEqual(plan[0].result, "skipped")
        self.assertEqual(plan[0].action, "none")

    def test_plan_methods_and_missing_pins(self):
        ids = select(self.manifest, names=["nmap", "kerbrute", "sliver-server", "empire", "netexec", "havoc"])
        plan = build_plan(ROOT, self.manifest, self.lock, ids, FixedDetector({}))
        decisions = {x.ident: x for x in plan}
        self.assertEqual(decisions["nmap"].action, "brew")
        self.assertEqual(decisions["kerbrute"].action, "go")
        self.assertEqual(decisions["sliver-server"].result, "manual-required")
        self.assertEqual(decisions["empire"].result, "manual-required")
        self.assertEqual(decisions["netexec"].result, "manual-required")
        self.assertEqual(decisions["havoc"].result, "manual-required")

    def test_dependency_unavailable_blocks_parent(self):
        ids = select(self.manifest, names=["kerbrute"])
        plan = build_plan(ROOT, self.manifest, self.lock, ids, FixedDetector({"go": Detection("unknown", "no Go") }))
        self.assertEqual([x.ident for x in plan], ["go", "kerbrute"])
        self.assertEqual(plan[-1].result, "blocked")

    def test_level_two_python_is_not_auto_installable(self):
        backend, reason = capability(self.by_id["netexec"], self.lock, self.manifest)
        self.assertEqual(backend, "manual-required")
        self.assertIn("Level 2", reason)

    def test_docker_digest_enables_only_pull_plan(self):
        tool = dict(self.by_id["empire"], image="bcsecurity/empire", image_digest="sha256:" + "a" * 64)
        self.assertEqual(capability(tool, self.lock, self.manifest)[0], "docker")

    def test_git_plan_requires_fixed_commit(self):
        tool = dict(self.by_id["havoc"], source_dir="c2/Havoc")
        self.assertEqual(capability(tool, self.lock, self.manifest)[0], "manual-required")

    def test_automatic_capability_count(self):
        counts = {}
        for tool in self.manifest["tools"]:
            backend = capability(tool, self.lock, self.manifest)[0]
            counts[backend] = counts.get(backend, 0) + 1
        self.assertEqual(counts["brew"], 46)
        self.assertEqual(counts["go"], 10)
        self.assertEqual(counts["manual-required"], 53)

    def test_cli_dry_run_is_read_only(self):
        output = io.StringIO()
        with patch("installer.main.Backends", side_effect=AssertionError("backend was invoked")):
            with redirect_stdout(output):
                code = main(["--dry-run", "--tool", "netexec", "--json"], ROOT)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())["selected_count"], 3)

    def test_install_source_and_tool_destination_are_separate(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            source = project / "install"
            compose = source / "c2/empire/compose.yaml"
            compose.parent.mkdir(parents=True)
            compose.write_text("services: {}\n")
            tool_path = project / "c2/Sliver/bin/sliver-server_darwin-arm64"
            tool_path.parent.mkdir(parents=True)
            tool_path.write_bytes(b"fixture")
            detector = Detector(source, self.manifest, self.lock, which=lambda _: None)
            self.assertEqual(detector._file_path("c2/empire/compose.yaml"), compose)
            self.assertEqual(detector._file_path("c2/Sliver/bin/sliver-server_darwin-arm64"), tool_path)
            self.assertEqual(Backends(source, self.manifest, self.lock).project_root, project)


class BackendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest, cls.lock = load(ROOT)
        cls.by_id = {tool["id"]: tool for tool in cls.manifest["tools"]}

    def test_brew_uses_exact_catalog_version_without_upgrade(self):
        seen = []
        def runner(args, **kwargs):
            seen.append(args)
            if args[:2] == ["brew", "info"]:
                return subprocess.CompletedProcess(args, 0, json.dumps({"formulae": [{"versions": {"stable": "7.991"}, "revision": 0}]}), "")
            if args[:2] == ["brew", "outdated"]:
                return subprocess.CompletedProcess(args, 0, '{"formulae":[]}', "")
            return subprocess.CompletedProcess(args, 0, "", "")
        result = Backends(ROOT, self.manifest, self.lock, runner=runner)._brew(self.by_id["nmap"])
        self.assertEqual(result.result, "success")
        self.assertEqual(seen[-1], ["brew", "install", "--formula", "nmap"])
        self.assertFalse(any("upgrade" in command for args in seen for command in args))

    def test_brew_mismatch_blocks_before_install(self):
        seen = []
        def runner(args, **kwargs):
            seen.append(args)
            return subprocess.CompletedProcess(args, 0, json.dumps({"formulae": [{"versions": {"stable": "0.0.1"}}]}), "")
        with self.assertRaisesRegex(InstallError, "differs from lock"):
            Backends(ROOT, self.manifest, self.lock, runner=runner)._brew(self.by_id["nmap"])
        self.assertEqual(len(seen), 1)

    def test_brew_outdated_dependency_blocks_install(self):
        seen = []
        def runner(args, **kwargs):
            seen.append(args)
            if args[:2] == ["brew", "info"]:
                return subprocess.CompletedProcess(args, 0, '{"formulae":[{"versions":{"stable":"7.991"}}]}', "")
            if args[:2] == ["brew", "deps"]:
                return subprocess.CompletedProcess(args, 0, "openssl@3\n", "")
            if args[:2] == ["brew", "outdated"]:
                return subprocess.CompletedProcess(args, 0, '{"formulae":[{"name":"openssl@3"}]}', "")
            return subprocess.CompletedProcess(args, 0, "", "")
        with self.assertRaisesRegex(InstallError, "implicit upgrade"):
            Backends(ROOT, self.manifest, self.lock, runner=runner)._brew(self.by_id["nmap"])
        self.assertFalse(any(args[:2] == ["brew", "install"] for args in seen))

    def test_go_checksum_mismatch_stops_before_build(self):
        seen = []
        def runner(args, **kwargs):
            seen.append(args)
            return subprocess.CompletedProcess(args, 0, '{"Sum":"h1:wrong"}', "")
        with self.assertRaisesRegex(InstallError, "checksum mismatch"):
            Backends(ROOT, self.manifest, self.lock, runner=runner)._go(self.by_id["kerbrute"])
        self.assertEqual(len(seen), 1)

    def test_existing_binary_is_never_fetched(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / "bin/tool"
            destination.parent.mkdir()
            destination.write_bytes(b"existing")
            tool = dict(self.by_id["sliver-server"], executable="bin/tool", artifact_url="https://github.com/example/tool")
            backend = Backends(root, self.manifest, {"artifacts": {"bin/tool": {"sha256": "0" * 64}}}, fetcher=lambda *args, **kwargs: self.fail("network accessed"))
            with self.assertRaisesRegex(InstallError, "already exists"):
                backend._binary(tool)
            self.assertEqual(destination.read_bytes(), b"existing")

    def test_docker_plan_never_starts_container(self):
        seen = []
        def runner(args, **kwargs):
            seen.append(args)
            if "--format" in args:
                return subprocess.CompletedProcess(args, 0, '{"services":{"empire":{"ports":[{"host_ip":"127.0.0.1"}]}}}', "")
            return subprocess.CompletedProcess(args, 0, "", "")
        tool = dict(self.by_id["empire"], image="bcsecurity/empire", image_digest="sha256:" + "a" * 64)
        result = Backends(ROOT, self.manifest, self.lock, runner=runner)._docker(tool)
        self.assertEqual(result.result, "success")
        self.assertEqual(seen[-1][:2], ["docker", "pull"])
        self.assertFalse(any(command in ("up", "down") for args in seen for command in args))

    def test_docker_nonlocal_port_blocks_pull(self):
        seen = []
        def runner(args, **kwargs):
            seen.append(args)
            if "--format" in args:
                return subprocess.CompletedProcess(args, 0, '{"services":{"x":{"ports":[{"host_ip":"0.0.0.0"}]}}}', "")
            return subprocess.CompletedProcess(args, 0, "", "")
        tool = dict(self.by_id["empire"], image="bcsecurity/empire", image_digest="sha256:" + "a" * 64)
        with self.assertRaisesRegex(InstallError, "non-localhost"):
            Backends(ROOT, self.manifest, self.lock, runner=runner)._docker(tool)
        self.assertFalse(any("pull" in args for args in seen))

    def test_backend_failure_is_failed_not_blocked(self):
        def runner(args, **kwargs):
            if args[:2] == ["brew", "info"]:
                return subprocess.CompletedProcess(args, 0, json.dumps({"formulae": [{"versions": {"stable": "7.991"}}]}), "")
            if args[:2] == ["brew", "outdated"]:
                return subprocess.CompletedProcess(args, 0, '{"formulae":[]}', "")
            return subprocess.CompletedProcess(args, 7, "", "failure")
        with self.assertRaises(InstallError) as caught:
            Backends(ROOT, self.manifest, self.lock, runner=runner)._brew(self.by_id["nmap"])
        self.assertEqual(caught.exception.result, "failed")

    def test_netexec_patch_applies_only_to_fixture(self):
        patch_file = ROOT / "patches/netexec/version-exit-code.patch"
        original = "\n    if args.version:\n        print(f\"{VERSION} - {CODENAME} - {COMMIT} - {DISTANCE}\")\n        sys.exit(1)\n\n    # Multiply output_tries by 10 to enable more fine granural control, see exec methods\n    if hasattr(args, \"get_output_tries\"):\n"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nxc/cli.py"
            path.parent.mkdir()
            path.write_text("\n" * 126 + original)
            result = subprocess.run(["git", "apply", "--check", str(patch_file)], cwd=directory, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr.decode())


if __name__ == "__main__":
    unittest.main()
