"""Exercise the actual Windows batch entry point without opening a browser."""
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import unittest
from unittest.mock import patch

import run_web

ROOT = Path(__file__).resolve().parents[1]


class LauncherTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "Windows batch entry point")
    def test_double_click_entry_requests_browser_open(self):
        # Use the actual batch file and venv launcher; replace only the web app
        # with a recording script so this test cannot touch data or launch a UI.
        with tempfile.TemporaryDirectory(prefix="workbench_launcher_") as temporary:
            folder = Path(temporary)
            scripts = folder / ".venv" / "Scripts"
            scripts.mkdir(parents=True)
            shutil.copy2(ROOT / "start_web.cmd", folder / "start_web.cmd")
            shutil.copy2(ROOT / ".venv" / "Scripts" / "python.exe", scripts / "python.exe")
            shutil.copy2(ROOT / ".venv" / "pyvenv.cfg", folder / ".venv" / "pyvenv.cfg")
            (folder / "run_web.py").write_text(
                "import json,sys\nfrom pathlib import Path\n"
                "Path(__file__).with_name('arguments.json').write_text(json.dumps(sys.argv[1:]))\n",
                encoding="utf-8",
            )
            result = subprocess.run(["cmd.exe", "/d", "/c", str(folder / "start_web.cmd")],
                                    input=b"\n", capture_output=True, cwd=folder, timeout=10)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            arguments = json.loads((folder / "arguments.json").read_text())
            self.assertIn("--open-browser", arguments,
                          "Double-click starts the server but never requests opening its page")

    def test_browser_waits_until_http_ready(self):
        calls = []

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                calls.append(self.path)
                self.send_response(503 if len(calls) == 1 else 200)
                self.end_headers()

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = f"http://127.0.0.1:{server.server_port}/"
        try:
            with patch("run_web.webbrowser.open", return_value=True) as opened:
                self.assertTrue(run_web.open_workbench(url))
                opened.assert_called_once_with(url, new=2)
            self.assertEqual(len(calls), 2)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    @unittest.skipUnless(os.name == "nt", "Windows instance lock")
    def test_already_running_also_opens_browser(self):
        with tempfile.TemporaryDirectory(prefix="workbench_existing_") as temporary:
            with patch.object(run_web, "__file__", str(Path(temporary) / "run_web.py")), \
                 patch.object(sys, "argv", ["run_web.py", "--open-browser"]), \
                 patch("msvcrt.locking", side_effect=OSError("already locked")), \
                 patch.object(run_web, "open_workbench", return_value=True) as opened, \
                 redirect_stdout(io.StringIO()):
                run_web.main()
                opened.assert_called_once_with("http://127.0.0.1:5000/")


if __name__ == "__main__":
    unittest.main()
