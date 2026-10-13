import contextlib
import importlib.metadata
import io
import json
import os
import pathlib
import shutil
import socket
import sys
import tempfile
import threading
import unittest
import unittest.mock
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "hooks"))

import mnemosyne_end_of_turn as eot
import mnemosyne_session_start as ss

from mnemobrain import cli, config, deps, doctor

DURABLE_MSG = "We use bun instead of node for everything in this repository now, always"


class EnvCase(unittest.TestCase):
    def setUp(self):
        self._saved = {
            k: os.environ.get(k) for k in os.environ if k.startswith(("MNEMOBRAIN_", "GBRAIN_"))
        }
        self.home = pathlib.Path(tempfile.mkdtemp(prefix="mbtest-"))
        os.environ["MNEMOBRAIN_HOME"] = str(self.home)

    def tearDown(self):
        shutil.rmtree(self.home, ignore_errors=True)
        for k in [k for k in os.environ if k.startswith(("MNEMOBRAIN_", "GBRAIN_"))]:
            os.environ.pop(k, None)
        for k, v in self._saved.items():
            if v is not None:
                os.environ[k] = v


class TestConfig(EnvCase):
    def test_default_home(self):
        del os.environ["MNEMOBRAIN_HOME"]
        self.assertEqual(config.home(), pathlib.Path.home() / ".mnemobrain")

    def test_home_env_override(self):
        self.assertEqual(config.home(), self.home)

    def test_gbrain_url_derives_from_port(self):
        os.environ["MNEMOBRAIN_GBRAIN_PORT"] = "4000"
        self.assertEqual(config.get_env("MNEMOBRAIN_GBRAIN_URL"), "http://127.0.0.1:4000/health")

    def test_file_key_strips_only_full_mnemosyne_prefix(self):
        self.assertEqual(
            config.file_key("MNEMOSYNE_TEMPORAL_HALFLIFE_HOURS"), "temporal_halflife_hours"
        )
        self.assertNotEqual(
            config.file_key("MNEMOSYNE_TEMPORAL_HALFLIFE_HOURS"), "emporal_halflife_hours"
        )
        self.assertEqual(config.file_key("MNEMOBRAIN_GBRAIN_REF"), "gbrain_ref")
        self.assertEqual(config.file_key("MNEMOBRAIN_MNEMOSYNE_VERSION"), "mnemosyne_version")

    def test_config_file_roundtrip_mnemosyne_key(self):
        os.environ.pop("MNEMOSYNE_TEMPORAL_HALFLIFE_HOURS", None)
        config.write_config()
        path = self.home / "config" / "mnemobrain.yaml"
        path.write_text(path.read_text() + "temporal_halflife_hours: 24\n")
        self.assertEqual(config.get_env("MNEMOSYNE_TEMPORAL_HALFLIFE_HOURS"), "24")

    def test_render_config_has_unmangled_mnemosyne_key(self):
        text = config.render_config()
        self.assertTrue(
            any(line.startswith("temporal_halflife_hours:") for line in text.splitlines())
        )
        self.assertFalse([line for line in text.splitlines() if line.startswith("emporal_")])

    def test_precedence_env_over_file_over_default(self):
        config.write_config()
        self.assertEqual(config.get_env("MNEMOBRAIN_GBRAIN_PORT"), "3131")
        os.environ["MNEMOBRAIN_GBRAIN_PORT"] = "4000"
        self.assertEqual(config.get_env("MNEMOBRAIN_GBRAIN_PORT"), "4000")
        del os.environ["MNEMOBRAIN_GBRAIN_PORT"]
        (self.home / "config" / "mnemobrain.yaml").write_text("gbrain_port: 4000\n")
        self.assertEqual(config.get_env("MNEMOBRAIN_GBRAIN_PORT"), "4000")


class TestConfigWriter(EnvCase):
    def path(self):
        return self.home / "config" / "mnemobrain.yaml"

    def test_write_twice_same_bytes(self):
        self.assertTrue(config.write_config())
        first = self.path().read_bytes()
        self.assertFalse(config.write_config())
        self.assertEqual(first, self.path().read_bytes())

    def test_parse_roundtrip(self):
        config.write_config()
        parsed = config.parse_config(self.path().read_text())
        self.assertEqual(
            parsed["mnemosyne_version"], config.DEFAULTS["MNEMOBRAIN_MNEMOSYNE_VERSION"]
        )
        self.assertEqual(parsed["gbrain_ref"], config.DEFAULTS["MNEMOBRAIN_GBRAIN_REF"])
        self.assertEqual(parsed["gbrain_url"], config.default_value("MNEMOBRAIN_GBRAIN_URL"))


class TestLauncher(EnvCase):
    def test_launcher_serve_http_no_home_flag(self):
        text = cli.render_launcher("/bin/gbrain-fake")
        self.assertIn('exec "/bin/gbrain-fake" serve --http --port "3131"', text)
        self.assertNotIn("--" + "home", text)

    def test_launcher_env_is_home_and_ollama_mapping_only(self):
        text = cli.render_launcher("/bin/gbrain-fake")
        self.assertIn(f'HOME="{self.home}"', text)
        self.assertIn(f'OLLAMA_BASE_URL="{config.get_env("MNEMOBRAIN_OLLAMA_URL")}"', text)
        for phantom in (
            "GBRAIN_" + "HOME",
            "MNEMOSYNE_" + "HOME",
            "MNEMOBRAIN_OLLAMA_URL",
            "MNEMOBRAIN_EMBED_MODEL",
            "MNEMOBRAIN_EMBED_DIMS",
        ):
            self.assertNotIn(phantom, text)

    def test_launcher_port_override(self):
        os.environ["MNEMOBRAIN_GBRAIN_PORT"] = "4711"
        self.assertIn('--port "4711"', cli.render_launcher("/bin/gbrain-fake"))


class TestEnvLines(EnvCase):
    def test_env_lines_export_real_names(self):
        text = "\n".join(config.env_lines())
        self.assertIn(f'export MNEMOSYNE_DATA_DIR="{self.home}/data/mnemosyne"', text)
        self.assertNotIn("GBRAIN_" + "HOME", text)
        self.assertNotIn("MNEMOSYNE_" + "HOME", text)


class TestGbrainVersionCheck(EnvCase):
    def pkg_dir(self):
        d = self.home / "node_modules" / "gbrain"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def test_version_match_passes(self):
        os.environ["MNEMOBRAIN_GBRAIN_REF"] = "v0.54.1"
        (self.pkg_dir() / "package.json").write_text(json.dumps({"version": "0.54.1"}))
        self.assertEqual(doctor.check_gbrain_version(), "PASS")

    def test_version_mismatch_fails_with_bun_lock_fix(self):
        os.environ["MNEMOBRAIN_GBRAIN_REF"] = "v0.54.1.1"
        (self.pkg_dir() / "package.json").write_text(json.dumps({"version": "0.53.0"}))
        result = io.StringIO()
        with contextlib.redirect_stderr(result):
            status = doctor.check_gbrain_version()
        self.assertEqual(status, "FAIL")
        self.assertIn("bun.lock", result.getvalue())

    def test_sha_like_ref_is_skip(self):
        os.environ["MNEMOBRAIN_GBRAIN_REF"] = "a" * 40
        (self.pkg_dir() / "package.json").write_text(json.dumps({"version": "0.54.1"}))
        self.assertEqual(doctor.check_gbrain_version(), "SKIP")

    def test_no_install_returns_none(self):
        self.assertIsNone(doctor.check_gbrain_version())


class TestGbrainConfig(EnvCase):
    def path(self):
        return self.home / ".gbrain" / "config.json"

    def test_write_creates_valid_json_then_keeps(self):
        self.assertTrue(config.write_gbrain_config())
        data = json.loads(self.path().read_text())
        self.assertEqual(
            set(data), {"engine", "database_path", "embedding_model", "embedding_dimensions"}
        )
        self.assertEqual(data["engine"], "pglite")
        self.assertEqual(data["database_path"], str(self.home / ".gbrain" / "brain.pglite"))
        self.assertEqual(data["embedding_model"], config.get_env("MNEMOBRAIN_EMBED_MODEL"))
        self.assertEqual(data["embedding_dimensions"], int(config.get_env("MNEMOBRAIN_EMBED_DIMS")))
        self.assertFalse(config.write_gbrain_config())

    def test_write_resolves_env_overrides(self):
        os.environ["MNEMOBRAIN_EMBED_MODEL"] = "text-embedding-3-small"
        os.environ["MNEMOBRAIN_EMBED_DIMS"] = "1536"
        self.assertTrue(config.write_gbrain_config())
        data = json.loads(self.path().read_text())
        self.assertEqual(data["embedding_model"], "text-embedding-3-small")
        self.assertEqual(data["embedding_dimensions"], 1536)


class _Handler(BaseHTTPRequestHandler):
    code = 200

    def _respond(self):
        body = json.dumps({"status": "ok"}).encode()
        self.send_response(self.code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    do_POST = _respond
    do_GET = _respond

    def log_message(self, format, *args):
        pass


def _post_handler(code, body):
    class H(_Handler):
        pass

    H.code = code
    return H


class McpServerCase(EnvCase):
    def setUp(self):
        super().setUp()
        self.server = HTTPServer(("127.0.0.1", 0), self.handler_class())
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        os.environ["MNEMOBRAIN_GBRAIN_URL"] = f"http://127.0.0.1:{self.port}/mcp"
        os.environ["GBRAIN_ADMIN_BOOTSTRAP_TOKEN"] = "dummy-token"

    def handler_class(self):
        return _Handler

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        super().tearDown()


class TestMcpUrl(EnvCase):
    def test_default_url_becomes_mcp(self):
        self.assertEqual(
            doctor.mcp_url(),
            "http://127.0.0.1:3131/mcp",
        )

    def test_url_ending_health_is_replaced(self):
        os.environ["MNEMOBRAIN_GBRAIN_URL"] = "http://127.0.0.1:4000/health"
        self.assertEqual(doctor.mcp_url(), "http://127.0.0.1:4000/mcp")

    def test_url_not_ending_health_gets_mcp_appended(self):
        os.environ["MNEMOBRAIN_GBRAIN_URL"] = "http://127.0.0.1:4000"
        self.assertEqual(doctor.mcp_url(), "http://127.0.0.1:4000/mcp")


class TestAdminToken(EnvCase):
    def test_env_wins_over_file(self):
        os.environ["GBRAIN_ADMIN_BOOTSTRAP_TOKEN"] = "envtok"
        (self.home / "gbrain-admin.token").write_text("filetok\n")
        self.assertEqual(doctor.admin_token(), "envtok")

    def test_file_fallback_read_and_stripped(self):
        (self.home / "gbrain-admin.token").write_text("  filetok  \n")
        self.assertEqual(doctor.admin_token(), "filetok")

    def test_missing_everything_is_none(self):
        self.assertIsNone(doctor.admin_token())


class TestMcpAuthCheck(McpServerCase):
    def test_200_is_pass(self):
        self.assertEqual(doctor.mcp_auth_check()[0], "PASS")

    def test_401_is_fail(self):
        self.server.RequestHandlerClass = _post_handler(401, {})
        status, detail, _fix = doctor.mcp_auth_check()
        self.assertEqual(status, "FAIL")
        self.assertIn("token rejected", detail)
        self.assertIn("invalid_token", detail)

    def test_server_down_is_none(self):
        os.environ["MNEMOBRAIN_GBRAIN_URL"] = f"http://127.0.0.1:{self.port + 1}/mcp"
        self.assertIsNone(doctor.mcp_auth_check())


class TestPortOpen(unittest.TestCase):
    def test_open_and_closed_socket(self):
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            port = listener.getsockname()[1]
            self.assertTrue(cli._port_open(port))
        finally:
            listener.close()
        self.assertFalse(cli._port_open(port))


class TestRunningHealthy(EnvCase):
    def pidfile(self, pid):
        d = self.home / "services"
        d.mkdir(parents=True, exist_ok=True)
        p = d / "gbrain.pid"
        p.write_text(f"{pid}\n")
        return p

    def test_healthy_pid_is_true(self):
        with unittest.mock.patch.object(doctor, "health_check", return_value=(True, "ok at url")):
            healthy, pid, detail = cli.running_healthy(self.pidfile(os.getpid()))
        self.assertTrue(healthy)
        self.assertEqual(pid, os.getpid())
        self.assertEqual(detail, "ok at url")

    def test_unhealthy_pid_is_false(self):
        with unittest.mock.patch.object(
            doctor, "health_check", return_value=(False, "unreachable")
        ):
            healthy, _pid, detail = cli.running_healthy(self.pidfile(os.getpid()))
        self.assertFalse(healthy)
        self.assertEqual(detail, "unreachable")

    def test_missing_pidfile_is_none(self):
        healthy, pid, detail = cli.running_healthy(self.home / "services" / "gbrain.pid")
        self.assertIsNone(healthy)
        self.assertIsNone(pid)
        self.assertEqual(detail, "not running")


class TestEndOfTurnPolicy(unittest.TestCase):
    def test_durable_user_message_qualifies(self):
        self.assertTrue(eot.qualifies(DURABLE_MSG))
        self.assertTrue(
            eot.qualifies("Actually the timeout must be 30 seconds, not 10 - always use 30")
        )

    def test_issue12_chatter_samples_are_rejected(self):
        for line in (
            "the test will finish around 13:25, please wait for it",
            "here is the list of saved sessions from this morning, take a look when ready",
            "you can close the window now, the job keeps running in the background",
        ):
            self.assertFalse(eot.qualifies(line), line)

    def test_short_strings_are_rejected(self):
        self.assertFalse(eot.qualifies(""))
        self.assertFalse(eot.qualifies("ok"))

    def test_assistant_only_is_none_by_policy(self):
        os.environ.pop("MNEMOSYNE_STORE_TURNS", None)
        self.assertIsNone(
            eot.decide("", "Sure, I finished the refactor and every test passes now.")
        )

    def test_escape_hatch_stores_assistant_text(self):
        os.environ["MNEMOSYNE_STORE_TURNS"] = "1"
        try:
            self.assertEqual(eot.decide("", "assistant reply text"), "assistant reply text")
        finally:
            os.environ.pop("MNEMOSYNE_STORE_TURNS", None)


class TestEndOfTurnStore(EnvCase):
    def test_store_uses_conservative_defaults(self):
        captured = {}

        def fake_remember(text, source=None, importance=None, scope=None, metadata=None):
            captured.update(
                text=text, source=source, importance=importance, scope=scope, metadata=metadata
            )
            return "mem-1"

        with unittest.mock.patch.object(eot, "get_remember", return_value=fake_remember):
            eot.store(DURABLE_MSG, "agent-hook")
        self.assertEqual(captured["importance"], 0.5)
        self.assertEqual(captured["scope"], "session")
        self.assertEqual(captured["source"], "agent-hook")
        self.assertIn("auto", captured["metadata"])

    def test_turn_suffix_on_source(self):
        captured = {}

        def fake_remember(text, source=None, **kwargs):
            captured["source"] = source

        with unittest.mock.patch.object(eot, "get_remember", return_value=fake_remember):
            eot.store("x", "agent-hook", turn=True)
        self.assertEqual(captured["source"], "agent-hook-turn")


class TestSessionStartHook(unittest.TestCase):
    def _run(self, get_recall):
        import contextlib
        import io

        out = io.StringIO()
        with (
            unittest.mock.patch.object(ss, "get_recall", return_value=get_recall),
            contextlib.redirect_stdout(out),
        ):
            ss.main(["ss.py", "user preferences"])
        return out.getvalue()

    def test_recall_results_are_printed_one_per_line(self):
        memories = [{"content": "User prefers dark mode"}, {"content": "We use bun for gbrain"}]
        block = self._run(lambda q, top_k=5: list(memories))
        self.assertIn("- User prefers dark mode", block)
        self.assertIn("- We use bun for gbrain", block)

    def test_recall_raising_exits_clean(self):
        def boom(q, top_k=5):
            raise RuntimeError("no bank")

        self.assertEqual(self._run(boom), "")

    def test_empty_recall_prints_nothing(self):
        self.assertEqual(self._run(lambda q, top_k=5: []), "")


class TestBunLookup(unittest.TestCase):
    def _fake_bun(self, home, contents="echo 1.2.3"):
        bin_dir = pathlib.Path(home) / ".bun" / "bin"
        bin_dir.mkdir(parents=True, exist_ok=True)
        fake = bin_dir / "bun"
        fake.write_text(f"#!/bin/sh\n{contents}\n")
        fake.chmod(0o755)
        return fake

    def test_home_fallback_when_path_misses(self):
        with tempfile.TemporaryDirectory() as td:
            self._fake_bun(td, "echo 1.3.11")
            env = dict(os.environ, PATH="")
            with (
                unittest.mock.patch.object(
                    deps.pathlib.Path, "home", return_value=pathlib.Path(td)
                ),
                unittest.mock.patch.dict(os.environ, env, clear=True),
            ):
                self.assertEqual(deps.bun_version(), (1, 3, 11))

    def test_which_hit_wins_over_home_fallback(self):
        with tempfile.TemporaryDirectory() as td:
            self._fake_bun(td, "echo 1.2.3")
            on_path = pathlib.Path(td, "bun-on-path")
            on_path.write_text("#!/bin/sh\necho 9.9.9\n")
            on_path.chmod(0o755)
            env = dict(os.environ, PATH=str(td))
            with (
                unittest.mock.patch.object(deps.shutil, "which", return_value=str(on_path)),
                unittest.mock.patch.object(
                    deps.pathlib.Path, "home", return_value=pathlib.Path(td)
                ),
                unittest.mock.patch.dict(os.environ, env, clear=True),
            ):
                self.assertEqual(deps.bun_version(), (9, 9, 9))

    def test_missing_everywhere_is_none(self):
        with tempfile.TemporaryDirectory() as td:
            env = dict(os.environ, PATH="")
            with (
                unittest.mock.patch.object(
                    deps.pathlib.Path, "home", return_value=pathlib.Path(td)
                ),
                unittest.mock.patch.dict(os.environ, env, clear=True),
            ):
                self.assertIsNone(deps.bun_version())

    def test_doctor_fix_line_mentions_login_shells(self):
        with unittest.mock.patch.object(deps, "bun_version", return_value=None):
            _ok, _detail, fix = deps.check_bun()
        self.assertIn("~/.bun/bin", fix)
        self.assertIn("install bun:", fix)


class TestMnemosyneHermesCheck(unittest.TestCase):
    def test_known_bad_version_listed(self):
        self.assertIn("0.7.4", deps.MNEMOSYNE_HERMES_KNOWN_BAD)

    def test_known_bad_version_fails_without_probe(self):
        result = io.StringIO()
        probe = unittest.mock.patch.object(doctor.subprocess, "run")
        with (
            unittest.mock.patch.object(doctor.importlib.metadata, "version", return_value="0.7.4"),
            probe as probe_run,
            contextlib.redirect_stderr(result),
        ):
            status = doctor.check_mnemosyne_hermes()
        self.assertEqual(status, "FAIL")
        self.assertIn("known-unconstructible", result.getvalue())
        self.assertIn("0.7.4", result.getvalue())
        probe_run.assert_not_called()

    def test_package_missing_is_skip(self):
        result = io.StringIO()
        with (
            unittest.mock.patch.object(
                doctor.importlib.metadata,
                "version",
                side_effect=importlib.metadata.PackageNotFoundError("mnemosyne-hermes"),
            ),
            contextlib.redirect_stderr(result),
        ):
            status = doctor.check_mnemosyne_hermes()
        self.assertEqual(status, "SKIP")
        self.assertIn("not installed", result.getvalue())

    def test_probe_nonzero_non_module_error_is_fail(self):
        stub = unittest.mock.Mock(
            returncode=1,
            stdout="",
            stderr="RuntimeError:\nMnemosyne: no binding for the current home '/opt/data'",
        )
        result = io.StringIO()
        with (
            unittest.mock.patch.object(doctor.importlib.metadata, "version", return_value="0.8.0"),
            unittest.mock.patch.object(
                doctor, "hermes_root", return_value=pathlib.Path("/opt/hermes")
            ),
            unittest.mock.patch.object(doctor.subprocess, "run", return_value=stub),
            contextlib.redirect_stderr(result),
        ):
            status = doctor.check_mnemosyne_hermes()
        self.assertEqual(status, "FAIL")
        self.assertIn("no binding for the current home '/opt/data'", result.getvalue())

    def test_probe_zero_is_pass_only_with_hermes_environment(self):
        stub = unittest.mock.Mock(returncode=0, stdout="OK\n", stderr="")
        result = io.StringIO()
        with (
            unittest.mock.patch.object(doctor.importlib.metadata, "version", return_value="0.8.0"),
            unittest.mock.patch.object(
                doctor, "hermes_root", return_value=pathlib.Path("/opt/hermes")
            ),
            unittest.mock.patch.object(doctor.subprocess, "run", return_value=stub) as probe,
            contextlib.redirect_stderr(result),
        ):
            status = doctor.check_mnemosyne_hermes()
        self.assertEqual(status, "PASS")
        self.assertIn("provider constructs", result.getvalue())
        kwargs = probe.call_args.kwargs
        self.assertIn("env", kwargs)
        self.assertIn("PYTHONPATH", kwargs["env"])
        self.assertTrue(kwargs["env"]["PYTHONPATH"].startswith("/opt/hermes" + os.pathsep))
        self.assertIn("import hermes_constants", " ".join(probe.call_args.args[0]))

    def test_probe_hermes_constants_module_error_is_skip(self):
        stub = unittest.mock.Mock(
            returncode=1,
            stdout="",
            stderr="ModuleNotFoundError: No module named 'hermes_constants'",
        )
        result = io.StringIO()
        with (
            unittest.mock.patch.object(doctor.importlib.metadata, "version", return_value="0.8.0"),
            unittest.mock.patch.object(
                doctor, "hermes_root", return_value=pathlib.Path("/opt/hermes")
            ),
            unittest.mock.patch.object(doctor.subprocess, "run", return_value=stub),
            contextlib.redirect_stderr(result),
        ):
            status = doctor.check_mnemosyne_hermes()
        self.assertEqual(status, "SKIP")
        self.assertIn("not conclusive", result.getvalue())

    def test_no_root_is_skip_and_probe_never_runs(self):
        probe = unittest.mock.Mock()
        result = io.StringIO()
        with (
            unittest.mock.patch.object(doctor.importlib.metadata, "version", return_value="0.8.0"),
            unittest.mock.patch.object(doctor, "hermes_root", return_value=None),
            unittest.mock.patch.object(doctor.subprocess, "run", probe),
            contextlib.redirect_stderr(result),
        ):
            status = doctor.check_mnemosyne_hermes()
        self.assertEqual(status, "SKIP")
        self.assertIn("not conclusive", result.getvalue())
        self.assertIn("MNEMOBRAIN_HERMES_ROOT", result.getvalue())
        probe.assert_not_called()

    def test_check_is_registered(self):
        self.assertIn(doctor.check_mnemosyne_hermes, doctor.CHECKS)
        self.assertGreater(
            doctor.CHECKS.index(doctor.check_mnemosyne_hermes),
            doctor.CHECKS.index(doctor.check_mnemosyne),
        )


class TestHermesEmbeddingsCheck(unittest.TestCase):
    def test_package_missing_is_skip(self):
        result = io.StringIO()
        with (
            unittest.mock.patch.object(
                doctor.importlib.metadata,
                "version",
                side_effect=importlib.metadata.PackageNotFoundError("mnemosyne-hermes"),
            ),
            contextlib.redirect_stderr(result),
        ):
            status = doctor.check_mnemosyne_hermes_embeddings()
        self.assertEqual(status, "SKIP")
        self.assertIn("not installed", result.getvalue())

    def test_no_root_is_skip_and_probe_never_runs(self):
        probe = unittest.mock.Mock()
        result = io.StringIO()
        with (
            unittest.mock.patch.object(doctor.importlib.metadata, "version", return_value="0.8.0"),
            unittest.mock.patch.object(doctor, "hermes_root", return_value=None),
            unittest.mock.patch.object(doctor.subprocess, "run", probe),
            contextlib.redirect_stderr(result),
        ):
            status = doctor.check_mnemosyne_hermes_embeddings()
        self.assertEqual(status, "SKIP")
        self.assertIn("not conclusive", result.getvalue())
        self.assertIn("MNEMOBRAIN_HERMES_ROOT", result.getvalue())
        probe.assert_not_called()

    def test_known_bad_is_skip_without_probe(self):
        probe = unittest.mock.Mock()
        result = io.StringIO()
        with (
            unittest.mock.patch.object(doctor.importlib.metadata, "version", return_value="0.7.4"),
            unittest.mock.patch.object(
                doctor, "hermes_root", return_value=pathlib.Path("/opt/hermes")
            ),
            unittest.mock.patch.object(doctor.subprocess, "run", probe),
            contextlib.redirect_stderr(result),
        ):
            status = doctor.check_mnemosyne_hermes_embeddings()
        self.assertEqual(status, "SKIP")
        probe.assert_not_called()

    def test_constructs_and_embeds_is_pass(self):
        stub = unittest.mock.Mock(returncode=0, stdout="OK\nCAP True True\n", stderr="")
        result = io.StringIO()
        with (
            unittest.mock.patch.object(doctor.importlib.metadata, "version", return_value="0.8.0"),
            unittest.mock.patch.object(
                doctor, "hermes_root", return_value=pathlib.Path("/opt/hermes")
            ),
            unittest.mock.patch.object(doctor.subprocess, "run", return_value=stub),
            contextlib.redirect_stderr(result),
        ):
            status = doctor.check_mnemosyne_hermes_embeddings()
        self.assertEqual(status, "PASS")
        self.assertIn("can embed", result.getvalue())

    def test_constructs_without_engine_is_warn_with_consequence_and_fix(self):
        stub = unittest.mock.Mock(returncode=0, stdout="OK\nCAP False False\n", stderr="")
        result = io.StringIO()
        with (
            unittest.mock.patch.object(doctor.importlib.metadata, "version", return_value="0.8.0"),
            unittest.mock.patch.object(
                doctor, "hermes_root", return_value=pathlib.Path("/opt/hermes")
            ),
            unittest.mock.patch.object(doctor.subprocess, "run", return_value=stub),
            contextlib.redirect_stderr(result),
        ):
            status = doctor.check_mnemosyne_hermes_embeddings()
        self.assertEqual(status, "WARN")
        out = result.getvalue()
        self.assertIn("dense recall disabled", out)
        self.assertIn("keyword-only", out)
        self.assertIn("fix: ", out)
        self.assertIn("pip install", out)
        self.assertIn("embeddings", out)

    def test_engine_import_crash_after_construction_is_warn(self):
        stub = unittest.mock.Mock(
            returncode=1, stdout="OK\n", stderr="ModuleNotFoundError: No module named 'numpy'"
        )
        result = io.StringIO()
        with (
            unittest.mock.patch.object(doctor.importlib.metadata, "version", return_value="0.8.0"),
            unittest.mock.patch.object(
                doctor, "hermes_root", return_value=pathlib.Path("/opt/hermes")
            ),
            unittest.mock.patch.object(doctor.subprocess, "run", return_value=stub),
            contextlib.redirect_stderr(result),
        ):
            status = doctor.check_mnemosyne_hermes_embeddings()
        self.assertEqual(status, "WARN")
        self.assertIn("dense recall disabled", result.getvalue())
        self.assertIn("numpy", result.getvalue())

    def test_construction_fails_is_skip(self):
        stub = unittest.mock.Mock(returncode=1, stdout="", stderr="RuntimeError: boom")
        result = io.StringIO()
        with (
            unittest.mock.patch.object(doctor.importlib.metadata, "version", return_value="0.8.0"),
            unittest.mock.patch.object(
                doctor, "hermes_root", return_value=pathlib.Path("/opt/hermes")
            ),
            unittest.mock.patch.object(doctor.subprocess, "run", return_value=stub),
            contextlib.redirect_stderr(result),
        ):
            status = doctor.check_mnemosyne_hermes_embeddings()
        self.assertEqual(status, "SKIP")
        self.assertIn("not conclusive", result.getvalue())

    def test_check_is_registered_next_to_construction_check(self):
        self.assertIn(doctor.check_mnemosyne_hermes_embeddings, doctor.CHECKS)
        self.assertEqual(
            doctor.CHECKS.index(doctor.check_mnemosyne_hermes_embeddings),
            doctor.CHECKS.index(doctor.check_mnemosyne_hermes) + 1,
        )


if __name__ == "__main__":
    unittest.main()
