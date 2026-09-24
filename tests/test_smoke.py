import json
import os
import pathlib
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from mnemobrain import cli, config


class EnvCase(unittest.TestCase):
    def setUp(self):
        self._saved = {k: os.environ.get(k) for k in os.environ if k.startswith("MNEMOBRAIN_")}
        self.home = pathlib.Path(tempfile.mkdtemp(prefix="mbtest-"))
        os.environ["MNEMOBRAIN_HOME"] = str(self.home)

    def tearDown(self):
        shutil.rmtree(self.home, ignore_errors=True)
        for k in [k for k in os.environ if k.startswith("MNEMOBRAIN_")]:
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
        self.assertEqual(parsed["mnemosyne_version"], "4.0.0b3")
        self.assertEqual(parsed["gbrain_ref"], "v0.50.0.0")
        self.assertEqual(parsed["gbrain_url"], "http://127.0.0.1:3131/health")


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


if __name__ == "__main__":
    unittest.main()
