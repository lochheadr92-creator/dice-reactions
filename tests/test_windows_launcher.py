"""Launcher contracts; no live services or provider calls."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from unittest.mock import MagicMock

spec = importlib.util.spec_from_file_location(
    "windows_launcher", Path(__file__).resolve().parents[1] / "scripts/windows_launcher.py"
)
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


class LauncherTests(unittest.TestCase):
    def test_http_probe_requests_and_decodes_complete_gzip_body(self):
        response = MagicMock()
        response.headers = {"Content-Encoding": "gzip"}
        response.read.return_value = launcher.gzip.compress(b'{"status":"ok"}')
        with patch.object(launcher, "urlopen") as open_url:
            open_url.return_value.__enter__.return_value = response
            self.assertEqual(launcher.fetch("http://localhost:8000/api/health"), '{"status":"ok"}')
            self.assertEqual(open_url.call_args.args[0].get_header("Accept-encoding"), "gzip")

    def test_only_default_local_database_can_be_created_automatically(self):
        self.assertTrue(launcher.can_start_mongo("mongodb://127.0.0.1:27017/?replicaSet=rs0"))
        for uri in (
            "mongodb://remote:27017/?replicaSet=rs0",
            "mongodb://127.0.0.1:27928/?replicaSet=diceReliability",
            "mongodb://127.0.0.1:27017/",
            "mongodb://user:password@127.0.0.1:27017/?replicaSet=rs0",
        ):
            self.assertFalse(launcher.can_start_mongo(uri))

    def test_healthy_service_is_reused_without_spawning(self):
        with patch.object(launcher, "start_process") as start:
            self.assertFalse(launcher.ensure_service("Engine", 8000, lambda: True, [], Path.cwd(), {}, lambda _: None))
        start.assert_not_called()

    def test_unrecognized_occupied_port_is_not_killed_or_reused(self):
        with patch.object(launcher, "port_open", return_value=True), patch.object(launcher, "start_process") as start:
            with self.assertRaisesRegex(RuntimeError, "8000"):
                launcher.ensure_service("Engine", 8000, lambda: False, [], Path.cwd(), {}, lambda _: None)
        start.assert_not_called()

    def test_failed_child_is_reported_without_waiting_for_full_timeout(self):
        with patch.object(launcher, "port_open", return_value=False), patch.object(launcher, "start_process") as start:
            start.return_value.poll.return_value = 1
            with self.assertRaisesRegex(RuntimeError, "exited"):
                launcher.ensure_service("Engine", 8000, lambda: False, [], Path.cwd(), {}, lambda _: None)

    def test_environment_preserves_inherited_key_and_sets_frontend_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / ".env"
            p.write_text("OPENAI_API_KEY=\nDEFAULT_MODEL=openai-direct/gpt-4o\n")
            with patch.dict(launcher.os.environ, {"OPENAI_API_KEY": "test-only"}, clear=True):
                env = launcher.service_environment(p)
            self.assertEqual(env["OPENAI_API_KEY"], "test-only")
            self.assertEqual(env["DEFAULT_MODEL"], "openai-direct/gpt-4o")
            self.assertEqual(env["EXPO_PUBLIC_BACKEND_URL"], "http://localhost:8000")
            self.assertEqual(env["BROWSER"], "none")
            self.assertEqual(env["EXPO_OFFLINE"], "1")

    def test_frontend_rejects_wrong_project_or_wrong_backend(self):
        root = launcher.json.dumps(str(launcher.ROOT / "frontend"))[1:-1]
        good = root + ' EXPO_PUBLIC_BACKEND_URL "http://localhost:8000"'
        for bundle, expected in ((good, True), (good.replace(root, "other-project"), False), (good.replace(":8000", ":9000"), False)):
            with patch.object(launcher, "fetch", side_effect=["packager-status:running", bundle]):
                self.assertEqual(launcher.frontend_ready(), expected)

    def test_dropped_bundle_connection_is_not_reported_as_ready(self):
        with patch.object(launcher, "fetch", side_effect=["packager-status:running", ConnectionResetError()]):
            self.assertFalse(launcher.frontend_ready())

    def test_backend_rejects_unrelated_healthy_http_service(self):
        with patch.object(launcher, "fetch", side_effect=['{"status":"ok"}', '{"paths":{}}']):
            self.assertFalse(launcher.backend_ready())


if __name__ == "__main__":
    unittest.main()
