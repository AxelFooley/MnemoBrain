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
        self.assertEqual(parsed["mnemosyne_version"], "3.15.1")
        self.assertEqual(parsed["gbrain_ref"], "v0.50.0.0")
        self.assertEqual(parsed["gbrain_url"], "http://127.0.0.1:3131/health")


class TestLauncher(EnvCase):
    def test_launcher_contains_expected_values(self):
        text = cli.render_launcher("/bin/gbrain-fake")
        self.assertTrue(text.startswith("#!/bin/sh"))
        self.assertIn(f'GBRAIN_HOME="{self.home}/data/gbrain"', text)
        self.assertIn('exec "/bin/gbrain-fake" serve --port "3131" --home "$GBRAIN_HOME"', text)

    def test_launcher_port_override(self):
        os.environ["MNEMOBRAIN_GBRAIN_PORT"] = "4711"
        self.assertIn('--port "4711"', cli.render_launcher("/bin/gbrain-fake"))


if __name__ == "__main__":
    unittest.main()
