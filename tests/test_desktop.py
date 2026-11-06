"""Desktop backend lifecycle and installation safety, without automating a GUI."""
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
import urllib.parse
import urllib.request

import desktop_app
from storage import TaskStore
from test_web import Forms


class DesktopTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="workbench_desktop_")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / "tasks.json").write_text(json.dumps([dict(name="桌面原任务",done=False,due_date="")]),encoding="utf-8")
        self.store = TaskStore(self.root / "tasks.db", self.root / "tasks.json")
        self.store.snapshot()

    def test_http_lifecycle_random_port_and_resources(self):
        with desktop_app.DesktopBackend(self.root) as backend:
            url = backend.url
            thread = backend.thread
            self.assertNotEqual(urllib.parse.urlsplit(url).port,5000)
            for resource in ["", "static/style.css", "static/app.js"]:
                with urllib.request.urlopen(url+resource,timeout=3) as response:
                    self.assertEqual(response.status,200)
                    self.assertGreater(len(response.read()),100)
        self.assertFalse(thread.is_alive())
        with self.assertRaises(urllib.error.URLError):
            urllib.request.urlopen(url,timeout=1)

    def test_save_survives_desktop_close_and_new_server(self):
        with desktop_app.DesktopBackend(self.root) as backend:
            client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor())
            with client.open(backend.url) as response:
                forms = Forms(response.read().decode()).forms
            data = next(f["data"] for f in forms if "add-form" in f["attrs"].get("class", ""))
            data.update(name="桌面保存任务",due_date="2027-01-02")
            with client.open(backend.url+"tasks",data=urllib.parse.urlencode(data).encode()) as response:
                self.assertEqual(response.status,200)
        with desktop_app.DesktopBackend(self.root) as second:
            with urllib.request.urlopen(second.url) as response:
                self.assertIn("桌面保存任务",response.read().decode())
        tasks,_ = self.store.snapshot()
        self.assertEqual(len(tasks),2)
        self.assertEqual(tasks[-1].due_date,"2027-01-02")

    def test_packaged_app_uses_external_database_and_fails_if_missing(self):
        installation=self.root/"desktop"/"workbench"
        installation.mkdir(parents=True)
        location=installation/"project-location.json"
        with patch.object(sys,"frozen",True,create=True), patch.object(sys,"executable",str(installation/"app.exe")):
            with self.assertRaises(RuntimeError):
                desktop_app.project_root()
            location.write_text(json.dumps(dict(project_root=str(self.root))),encoding="utf-8")
            self.assertEqual(desktop_app.project_root(),self.root.resolve())
            location.write_text(json.dumps(dict(project_root="relative")),encoding="utf-8")
            with self.assertRaises(RuntimeError):
                desktop_app.project_root()

    @unittest.skipUnless(os.name=="nt","Windows instance lock")
    def test_single_instance_and_release_across_processes(self):
        runner=self.root/"check_lock.py"
        project=Path(desktop_app.__file__).resolve().parent
        runner.write_text("import sys\nfrom pathlib import Path\nsys.path.insert(0,"+repr(str(project))+")\n"
                          "from desktop_app import InstanceLock\n"
                          "with InstanceLock(Path(sys.argv[1])) as lock:\n"
                          "    print(int(lock.acquired))\n",encoding="utf-8")
        folder=self.root/"state"
        with desktop_app.InstanceLock(folder) as lock:
            self.assertTrue(lock.acquired)
            result=subprocess.run([sys.executable,str(runner),str(folder)],text=True,capture_output=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(result.stdout.strip(),"0")
        result=subprocess.run([sys.executable,str(runner),str(folder)],text=True,capture_output=True,timeout=10)
        self.assertEqual(result.stdout.strip(),"1")

    def test_self_check_does_not_change_tasks(self):
        before=[t.to_dict() for t in self.store.snapshot()[0]]
        folder=self.root/"state"
        folder.mkdir()
        desktop_app.self_check(self.root,folder)
        result=json.loads((folder/"self-check.json").read_text(encoding="utf-8"))
        self.assertEqual(result["database"],str(self.root/"tasks.db"))
        self.assertTrue(all(r["status"]==200 for r in result["resources"].values()))
        self.assertEqual([t.to_dict() for t in self.store.snapshot()[0]],before)


if __name__=="__main__":
    unittest.main()
