"""Web and cross-interface integration tests; every database is temporary."""
import concurrent.futures
from contextlib import closing
from datetime import date, timedelta
from html.parser import HTMLParser
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from werkzeug.datastructures import MultiDict

import storage
from storage import ConflictError, StorageError, TaskStore
from task_actions import Task
from web_app import create_app


class Forms(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.forms = []
        self.current = None
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "form":
            self.current = {"attrs": attrs, "data": {}}
            self.forms.append(self.current)
        elif tag == "input" and self.current is not None and attrs.get("name"):
            self.current["data"][attrs["name"]] = attrs.get("value", "")

    def handle_endtag(self, tag):
        if tag == "form":
            self.current = None


class WebTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="workbench_tests_")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.db = self.root / "tasks.db"
        self.legacy = self.root / "tasks.json"
        today = date.today()
        self.fixture = [dict(name="录像店·旧约", done=False, due_date=(today-timedelta(days=1)).isoformat()),
                        dict(name="约会·朱鸢", done=False, due_date=today.isoformat()),
                        dict(name="约会·妮可", done=True, due_date="")]
        self.legacy.write_text(json.dumps(self.fixture), encoding="utf-8")
        self.config = dict(TESTING=True, SECRET_KEY="test-secret", DATABASE=self.db, LEGACY=self.legacy)
        self.app = create_app(self.config)
        self.client = self.app.test_client()
        self.store = self.app.extensions["task_store"]

    def get_forms(self, client=None, query="/"):
        response = (client or self.client).get(query)
        self.assertEqual(response.status_code, 200)
        return Forms(response.get_data(as_text=True)).forms

    def form(self, cls="add-form", index=0, client=None, query="/"):
        return [f["data"] for f in self.get_forms(client, query) if cls in f["attrs"].get("class", "").split()][index].copy()

    def post(self, data, expected=303, client=None):
        response = (client or self.client).post("/tasks", data=data)
        self.assertEqual(response.status_code, expected, response.get_data(as_text=True)[:2000])
        return response

    def add(self, name="新任务", due=""):
        data = self.form()
        data.update(name=name, due_date=due)
        return self.post(data)

    def test_dashboard_statistics_filters_and_empty_search(self):
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn("哲店长工作台", html)
        self.assertIn("显示 3 / 3 条任务", html)
        self.assertIn("今天到期", html)
        for status, count in [("all",3),("pending",2),("done",1),("overdue",1)]:
            html = self.client.get(f"/?status={status}").get_data(as_text=True)
            self.assertEqual(html.count('data-task-id='), count)
        html = self.client.get("/?q=朱鸢&status=pending").get_data(as_text=True)
        self.assertEqual(html.count('data-task-id='), 1)
        self.assertIn("没有找到匹配的任务", self.client.get("/?q=不存在").get_data(as_text=True))
        self.assertEqual(self.client.get("/?status=invalid").status_code, 400)

    def test_full_lifecycle_persists_across_new_app_and_reload(self):
        self.add("  验收任务  ", "2027-01-02")
        tasks, _ = self.store.snapshot()
        uid = tasks[-1].uid
        self.assertEqual(tasks[-1].name, "验收任务")
        data = self.form("status-form", query="/?q=验收")
        self.post(data)
        reloaded = create_app(self.config).extensions["task_store"].snapshot()[0]
        self.assertTrue(next(t for t in reloaded if t.uid == uid).done)
        self.post(self.form("status-form", query="/?q=验收&status=done"))
        self.assertFalse(next(t for t in self.store.snapshot()[0] if t.uid == uid).done)
        data = self.form("delete-form", query="/?q=验收")
        self.post(data, 400)
        data["confirm"] = "yes"
        self.post(data)
        self.assertFalse(any(t.uid == uid for t in self.store.snapshot()[0]))

    def test_add_validation_and_preserved_input(self):
        for name, due in [(" ",""),("x"*201,""),("a\nb",""),("valid","2026-02-30"),("valid","20261106"),("valid","0000-01-01")]:
            with self.subTest(name=name[:20], due=due):
                data = self.form()
                data.update(name=name, due_date=due)
                response = self.post(data, 422)
                self.assertIn('role="alert"', response.get_data(as_text=True))
                self.assertEqual(len(self.store.snapshot()[0]), 3)
        self.add("x"*200, "9999-12-31")
        self.assertEqual(len(self.store.snapshot()[0]), 4)

    def test_html_escaping_search_task_attributes_and_sql(self):
        text = '<script>alert("x")</script>\' ; DROP TABLE tasks; --'
        self.add(text)
        html = self.client.get("/").get_data(as_text=True)
        self.assertNotIn('<script>alert(', html)
        self.assertIn('&lt;script&gt;', html)
        self.assertEqual(self.store.snapshot()[0][-1].name, text)
        html = self.client.get("/", query_string={"q": '<img src=x onerror=alert(1)>'}).get_data(as_text=True)
        self.assertNotIn('<img src=x', html)
        self.assertIn('&lt;img', html)

    def test_csrf_signature_origin_and_session_binding(self):
        data = self.form()
        for change in [{"csrf":""},{"csrf":"中文"},{"command":"tampered"}]:
            self.post(dict(data, **change), 403)
        response = self.client.post("/tasks", data=data, headers={"Origin":"https://evil.example"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.client.post("/tasks", data=data, headers={"Sec-Fetch-Site":"cross-site"}).status_code,403)
        other = self.app.test_client()
        other_data = self.form(client=other)
        other_data["command"] = data["command"]
        self.post(other_data, 403, other)
        self.assertEqual(len(self.store.snapshot()[0]), 3)

    def test_expired_command_is_rejected(self):
        data = self.form()
        with patch("time.time", return_value=99999999999):
            self.post(dict(data,name="expired"),403)

    def test_request_limits_methods_hosts_and_duplicate_fields(self):
        self.assertEqual(self.client.get("/tasks").status_code,405)
        self.assertEqual(self.client.post("/tasks", json={}).status_code,415)
        self.assertEqual(self.client.get("/", headers={"Host":"evil.example"}).status_code,400)
        data = self.form()
        duplicated = MultiDict(list(data.items()) + [("csrf",data["csrf"])])
        self.assertEqual(self.client.post("/tasks", data=duplicated).status_code,400)
        self.assertEqual(self.client.post("/tasks",data={"name":"x"*17000}).status_code,413)
        response = self.client.get("/")
        self.assertIn("form-action 'self'", response.headers["Content-Security-Policy"])
        self.assertEqual(response.headers["X-Content-Type-Options"],"nosniff")

    def test_double_submit_add_and_changed_replay(self):
        data = dict(self.form(),name="只添加一次",due_date="")
        self.post(data)
        self.post(data)
        self.assertEqual(len(self.store.snapshot()[0]),4)
        self.post(dict(data,name="改写重复请求"),409)
        self.assertEqual(len(self.store.snapshot()[0]),4)

    def test_stale_tabs_conflict_and_old_replay_cannot_undo_restore(self):
        other = self.app.test_client()
        first = self.form("status-form")
        second = self.form("status-form",client=other)
        self.post(first)
        self.post(second,409,other)
        self.post(self.form("status-form",query="/?q=旧约"))
        self.post(first)  # replay succeeds as acknowledgement, does not mutate
        self.assertFalse(self.store.snapshot()[0][0].done)

    def test_distinct_tasks_update_independently_and_filtered_identity(self):
        a = self.form("status-form",query="/?q=朱鸢")
        b = self.form("status-form",query="/?q=旧约")
        self.post(a)
        self.post(b)
        tasks,_ = self.store.snapshot()
        self.assertTrue(all(t.done for t in tasks))

    def test_concurrent_distinct_adds_and_same_request(self):
        self.store.snapshot()
        def add(i):
            return self.store.apply(str(i),"add",name=f"并发{i}")
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(add,range(12)))
            list(pool.map(lambda _:self.store.apply("same","add",name="一次"),range(8)))
        self.assertEqual(len(self.store.snapshot()[0]),16)
        self.assertEqual(sum(t.name == "一次" for t in self.store.snapshot()[0]),1)

    def test_concurrent_same_row_only_one_wins(self):
        task = self.store.snapshot()[0][0]
        def update(i):
            try:
                self.store.apply(f"update{i}","complete",task.uid,task.version)
                return "ok"
            except ConflictError:
                return "conflict"
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(update,range(8)))
        self.assertEqual(results.count("ok"),1)
        self.assertEqual(results.count("conflict"),7)

    def test_failed_web_write_rolls_back_command_and_revision(self):
        tasks, revision = self.store.snapshot()
        with closing(sqlite3.connect(self.db)) as c:
            c.execute("CREATE TRIGGER reject_update BEFORE UPDATE OF done ON tasks BEGIN SELECT RAISE(ABORT,'blocked'); END")
        self.post(self.form("status-form"),503)
        self.assertEqual(self.store.snapshot()[1],revision)
        self.assertFalse(self.store.snapshot()[0][0].done)
        with closing(sqlite3.connect(self.db)) as c:
            self.assertEqual(c.execute("SELECT count(*) FROM web_commands").fetchone()[0],0)

    def test_cli_preserves_identity_and_stale_snapshot_is_rejected(self):
        self.store.snapshot()
        with patch.multiple(storage,DATABASE_FILE=self.db,LEGACY_FILE=self.legacy,_loaded_revision=None):
            tasks = storage.load_tasks()
            identities = {t.name:t.uid for t in tasks}
            tasks.reverse()
            tasks[0].restore()
            tasks.append(Task("CLI 新任务",False,""))
            storage.save_tasks(tasks)
            updated,_ = self.store.snapshot()
            for t in updated[:-1]:
                self.assertEqual(t.uid,identities[t.name])
            self.store.apply("web","add",name="网页新任务")
            tasks.append(Task("旧 CLI",False,""))
            with self.assertRaises(StorageError):
                storage.save_tasks(tasks)
            self.assertEqual(self.store.snapshot()[0][-1].name,"网页新任务")

    def test_deleted_identity_never_reused_and_cli_invalidates_old_page(self):
        self.store.snapshot()
        old = self.form("delete-form",query="/?q=朱鸢")
        uid = self.store.snapshot()[0][1].uid
        with patch.multiple(storage,DATABASE_FILE=self.db,LEGACY_FILE=self.legacy,_loaded_revision=None):
            tasks = storage.load_tasks()
            tasks.pop(1)
            tasks.append(Task("替代任务",False,""))
            storage.save_tasks(tasks)
        self.post(dict(old,confirm="yes"),409)
        self.assertNotEqual(self.store.snapshot()[0][-1].uid,uid)

    def test_cli_content_update_conflicts_with_old_web_form(self):
        old = self.form("status-form")
        with patch.multiple(storage,DATABASE_FILE=self.db,LEGACY_FILE=self.legacy,_loaded_revision=None):
            tasks = storage.load_tasks()
            tasks[0].name = "CLI 改名"
            storage.save_tasks(tasks)
        self.post(old,409)

    def test_empty_database_does_not_reimport(self):
        tasks,_ = self.store.snapshot()
        for i,t in enumerate(tasks):
            self.store.apply(f"delete{i}","delete",t.uid,t.version)
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn("这里暂时没有任务",html)
        self.assertIn("显示 0 / 0 条任务",html)
        self.assertEqual(self.store.snapshot()[0],[])

    def test_old_schema_backup_migration_and_idempotent_restart(self):
        with closing(sqlite3.connect(self.db)) as c:
            c.execute("CREATE TABLE tasks(id INTEGER PRIMARY KEY,position INTEGER NOT NULL UNIQUE,name TEXT NOT NULL,done INTEGER NOT NULL,due_date TEXT NOT NULL)")
            c.execute("CREATE TABLE app_state(id INTEGER PRIMARY KEY,revision INTEGER NOT NULL)")
            c.execute("INSERT INTO app_state VALUES(1,9)")
            c.execute("INSERT INTO tasks VALUES(41,0,'真实旧数据',1,'2026-11-06')")
            c.commit()
        tasks, revision = self.store.snapshot()
        self.assertEqual(revision,9)
        self.assertEqual(tasks[0].to_dict(),dict(name="真实旧数据",done=True,due_date="2026-11-06"))
        backups = list((self.root / "backups").glob("*.db"))
        self.assertEqual(len(backups),1)
        with closing(sqlite3.connect(backups[0])) as c:
            self.assertEqual(c.execute("SELECT * FROM tasks").fetchall(),[(41,0,"真实旧数据",1,"2026-11-06")])
            self.assertEqual(c.execute("PRAGMA integrity_check").fetchone()[0],"ok")
        self.assertEqual(self.store.snapshot()[0][0].uid,tasks[0].uid)
        self.assertEqual(len(list((self.root / "backups").glob("*.db"))),1)

    def test_unavailable_database_renders_recoverable_error(self):
        self.db.write_bytes(b"corrupted database")
        response = self.client.get("/")
        self.assertEqual(response.status_code,503)
        self.assertIn("返回工作台",response.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
