import contextlib
import importlib
import importlib.util
import io
import json
import os
import pathlib
import re
import shutil
import sys
import tempfile
import unittest
import unittest.mock
import uuid

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "hooks"))

import mnemosyne_session_start as ss

from mnemobrain import cli, deps, doctor

TABLE = """\
slug updated_at
old-guide 2020-01-01T00:00:00Z
deep/nested/page 2020-06-01T00:00:00Z
fresh-guide 2099-01-01T00:00:00Z
"""

TABLE_REFRESHED = """\
slug updated_at
old-guide 2099-01-01T00:00:00Z
fresh-guide 2099-01-01T00:00:00Z
"""

# Real renderer shape (cli.ts case 'list_pages'): TAB-separated, date-only
# third column, title with spaces; slash slugs are real.
TSV_REAL = (
    "slug\ttype\tupdated_at\ttitle\n"
    "old-guide\tresearch\t2020-03-01\tOld Guide Title With Spaces\n"
    "deep/nested/page\tguide\t2020-06-01\tNested Title Also With Spaces\n"
    "fresh-guide\tguide\t2099-01-01\tFresh Enough Title\n"
)


class EnvCase(unittest.TestCase):
    def setUp(self):
        self._saved = {
            k: os.environ.get(k) for k in os.environ if k.startswith(("MNEMOBRAIN_", "MNEMOSYNE_"))
        }
        for k in [k for k in os.environ if k.startswith(("MNEMOBRAIN_", "MNEMOSYNE_"))]:
            os.environ.pop(k, None)
        self.home = pathlib.Path(tempfile.mkdtemp(prefix="mbtest-"))
        os.environ["MNEMOBRAIN_HOME"] = str(self.home)

    def tearDown(self):
        shutil.rmtree(self.home, ignore_errors=True)
        for k in [k for k in os.environ if k.startswith(("MNEMOBRAIN_", "MNEMOSYNE_"))]:
            os.environ.pop(k, None)
        for k, v in self._saved.items():
            if v is not None:
                os.environ[k] = v

    def write_fake_gbrain(self, table):
        bin_dir = self.home / "node_modules" / ".bin"
        bin_dir.mkdir(parents=True, exist_ok=True)
        fake = bin_dir / "gbrain"
        fake.write_text(f"#!/bin/sh\ncat <<'MBTABLE'\n{table}\nMBTABLE\n")
        fake.chmod(0o755)
        return fake

    def run_cmd(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(argv)
        return code, out.getvalue(), err.getvalue()


class TestRethink(EnvCase):
    def rethink_dir(self):
        return self.home / "rethink"

    def test_request_files_for_stale_pages_only(self):
        self.write_fake_gbrain(TABLE)
        code, out, _err = self.run_cmd(["rethink", "--stale-days", "30", "--limit", "10"])
        self.assertEqual(code, 0)
        self.assertIn("rethink: 2 stale pages (queued 2 request files in", out)
        self.assertIn(str(self.rethink_dir()), out)
        old = self.rethink_dir() / "old-guide.md"
        self.assertTrue(old.exists())
        text = old.read_text()
        self.assertIn("# rethink: old-guide", text)
        self.assertIn("stale_since: 2020-01-01T00:00:00Z", text)
        self.assertIn("reason: page not updated in 30 days", text)
        self.assertIn("gbrain get <slug> --include-content", text)
        self.assertIn("requested: ", text)
        nested = self.rethink_dir() / "deep__nested__page.md"
        self.assertTrue(nested.exists())
        self.assertIn("# rethink: deep/nested/page", nested.read_text())
        self.assertFalse((self.rethink_dir() / "fresh-guide.md").exists())

    def test_limit_queues_only_oldest(self):
        self.write_fake_gbrain(TABLE)
        code, out, _err = self.run_cmd(["rethink", "--limit", "1"])
        self.assertEqual(code, 0)
        self.assertIn("rethink: 2 stale pages (queued 1 request files in", out)
        self.assertTrue((self.rethink_dir() / "old-guide.md").exists())
        self.assertFalse((self.rethink_dir() / "deep__nested__page.md").exists())

    def test_self_clean_removes_request_files_for_refreshed_pages(self):
        self.write_fake_gbrain(TABLE)
        code, _out, _err = self.run_cmd(["rethink"])
        self.assertEqual(code, 0)
        self.assertTrue((self.rethink_dir() / "old-guide.md").exists())
        self.write_fake_gbrain(TABLE_REFRESHED)
        code, _out, _err = self.run_cmd(["rethink"])
        self.assertEqual(code, 0)
        self.assertFalse((self.rethink_dir() / "old-guide.md").exists())
        self.assertFalse((self.rethink_dir() / "deep__nested__page.md").exists())

    def test_json_shape(self):
        self.write_fake_gbrain(TABLE)
        code, out, _err = self.run_cmd(["rethink", "--json", "--limit", "1"])
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertEqual(len(data), 1)
        self.assertEqual(set(data[0]), {"slug", "updated_at", "request_file"})
        self.assertEqual(data[0]["slug"], "old-guide")
        self.assertEqual(data[0]["updated_at"], "2020-01-01T00:00:00Z")
        self.assertTrue(data[0]["request_file"].endswith("old-guide.md"))
        self.assertTrue(pathlib.Path(data[0]["request_file"]).exists())

    def test_missing_bin_is_exit_1_with_message(self):
        with unittest.mock.patch.object(deps.shutil, "which", return_value=None):
            code, out, err = self.run_cmd(["rethink"])
        self.assertEqual(code, 1)
        self.assertIn("rethink: gbrain not installed", out)
        self.assertIn("fix:", err)

    def test_refuses_while_service_running(self):
        self.write_fake_gbrain(TABLE)
        services = self.home / "services"
        services.mkdir(parents=True, exist_ok=True)
        (services / "gbrain.pid").write_text(f"{os.getpid()}\n")
        with unittest.mock.patch.object(doctor, "health_check", return_value=(True, "ok at url")):
            code, out, err = self.run_cmd(["rethink"])
        self.assertEqual(code, 1)
        self.assertIn("single-writer", out)
        self.assertIn("stop gbrain", err)
        self.assertFalse(self.rethink_dir().exists())

    def test_parse_real_renderer_tsv_row(self):
        row = "deep/nested/page\tresearch\t2020-06-01\tTitle With Spaces"
        self.assertEqual(cli._parse_gbrain_list(row), [("deep/nested/page", "2020-06-01")])

    def test_request_files_for_real_renderer_tsv(self):
        self.write_fake_gbrain(TSV_REAL)
        code, out, _err = self.run_cmd(["rethink", "--stale-days", "30", "--limit", "10"])
        self.assertEqual(code, 0)
        self.assertIn("rethink: 2 stale pages (queued 2 request files in", out)
        old = self.rethink_dir() / "old-guide.md"
        self.assertTrue(old.exists())
        self.assertIn("# rethink: old-guide", old.read_text())
        nested = self.rethink_dir() / "deep__nested__page.md"
        self.assertTrue(nested.exists())
        text = nested.read_text()
        self.assertIn("# rethink: deep/nested/page", text)
        self.assertIn("stale_since: 2020-06-01", text)
        self.assertFalse((self.rethink_dir() / "fresh-guide.md").exists())

    def test_gbrain_list_failure_is_reported_not_zero_pages(self):
        bin_dir = self.home / "node_modules" / ".bin"
        bin_dir.mkdir(parents=True, exist_ok=True)
        fake = bin_dir / "gbrain"
        fake.write_text(
            "#!/bin/sh\n"
            "echo 'UPGRADE_AVAILABLE' >&2\n"
            "echo 'gbrain 0.54.1 -> https://example.invalid/upgrade' >&2\n"
            'echo "GBrain\'s local database is already open through gbrain serve" >&2\n'
            "exit 1\n"
        )
        fake.chmod(0o755)
        code, out, err = self.run_cmd(["rethink"])
        self.assertEqual(code, 1)
        self.assertIn("rethink: FAILED", out)
        self.assertIn("already open through gbrain serve", err)
        self.assertNotIn("0 stale pages", out)
        self.assertIn("fix:", err)


class TestRetain(EnvCase):
    def test_empty_input_is_usage_and_exit_1(self):
        with unittest.mock.patch.object(sys, "stdin", io.StringIO("")):
            code, out, err = self.run_cmd(["retain"])
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("usage:", err)

    def test_missing_mnemosyne_is_clean_error(self):
        missing = {
            "mnemosyne": None,
            "mnemosyne.core": None,
            "mnemosyne.core.banks": None,
            "mnemosyne.core.memory": None,
        }
        with unittest.mock.patch.dict(sys.modules, missing):
            code, out, err = self.run_cmd(["retain", "some fact"])
        self.assertEqual(code, 1)
        self.assertIn("retain: FAILED", out)
        self.assertIn("not importable", err)
        self.assertIn("fix:", err)

    def test_bad_metadata_json_is_exit_1(self):
        code, out, err = self.run_cmd(["retain", "--metadata", "not-json", "fact"])
        self.assertEqual(code, 1)
        self.assertIn("retain: FAILED", out)
        self.assertIn("--metadata is not valid JSON", err)


@unittest.skipUnless(importlib.util.find_spec("mnemosyne"), "mnemosyne not installed")
class TestRetainRoundTrip(EnvCase):
    def test_retain_stores_and_returns_id(self):
        content = f"retain roundtrip fact {uuid.uuid4().hex}"
        code, out, _err = self.run_cmd(
            [
                "retain",
                "--importance",
                "0.7",
                "--source",
                "test",
                "--scope",
                "global",
                "--metadata",
                '{"topic": "releases"}',
                content,
            ]
        )
        self.assertEqual(code, 0)
        match = re.match(r"retain: ok (\S+) \((\d+) chars\)", out.strip())
        self.assertIsNotNone(match, out)
        memory_id, chars = match.group(1), int(match.group(2))
        self.assertTrue(memory_id)
        self.assertEqual(chars, len(content))

        from mnemosyne.core.banks import BankManager
        from mnemosyne.core.memory import Mnemosyne

        data_dir = self.home / "data" / "mnemosyne"
        db_path = BankManager(data_dir).get_bank_db_path("default")
        mem = Mnemosyne(db_path=str(db_path), bank="default")
        stored = mem.get(memory_id)
        self.assertIsInstance(stored, dict)
        self.assertEqual(stored["content"], content)

    def test_mnemosyne_bank_env_selects_bank_db(self):
        content = f"retain bank-scoped fact {uuid.uuid4().hex}"
        os.environ["MNEMOSYNE_BANK"] = "alt"
        code, _out, _err = self.run_cmd(["retain", content])
        self.assertEqual(code, 0)
        from mnemosyne.core.banks import BankManager

        db_path = BankManager(self.home / "data" / "mnemosyne").get_bank_db_path("alt")
        self.assertTrue(db_path.exists())


class TestRecallFloor(unittest.TestCase):
    def test_filter_drops_below_floor_keeps_rest(self):
        items = [
            {"content": "noise", "score": 0.30},
            {"content": "real", "score": 0.50},
            {"content": "unscored"},
        ]
        self.assertEqual(
            ss.above_floor(items, floor=0.35),
            [{"content": "real", "score": 0.50}, {"content": "unscored"}],
        )

    def test_all_below_floor_yields_empty_output_without_header(self):
        items = [{"content": "a", "score": 0.2}, {"content": "b", "score": 0.3}]
        self.assertEqual(ss.format_context(items), "")

    def test_unscored_items_survive_format(self):
        block = ss.format_context([{"content": "User prefers dark mode"}])
        self.assertIn("- User prefers dark mode", block)
        self.assertIn("--- Mnemosyne context", block)

    def test_default_floor_is_env_overridable(self):
        with unittest.mock.patch.dict(os.environ, {"MNEMOSYNE_RECALL_FLOOR": "0.5"}):
            importlib.reload(ss)
            self.assertEqual(ss.SCORE_FLOOR, 0.5)
            self.assertEqual(ss.above_floor([{"content": "mid", "score": 0.4}]), [])
        os.environ.pop("MNEMOSYNE_RECALL_FLOOR", None)
        importlib.reload(ss)
        self.assertEqual(ss.SCORE_FLOOR, 0.35)


if __name__ == "__main__":
    unittest.main()
