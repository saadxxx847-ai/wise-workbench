import concurrent.futures
from contextlib import closing
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest

PROJECT = Path(__file__).resolve().parents[1]
FIXTURE = [
    {"name": "约会·朱鸢", "done": False, "due_date": "2026-11-05"},
    {"name": "约会·妮可", "done": False, "due_date": "2026-11-06"},
    {"name": "约会·格莉丝", "done": True, "due_date": "2026-11-04"},
]
RUNNER = '''from datetime import date as RealDate
from unittest.mock import patch
import runpy
from pathlib import Path
class FixedDate(RealDate):
    @classmethod
    def today(cls):
        return cls(2026, 11, 6)
with patch("datetime.date", FixedDate):
    runpy.run_path(str(Path(__file__).with_name("main.py")), run_name="__main__")
'''


class ProjectTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="python_learn_tests_")
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        self.outside = self.folder / "outside"
        self.outside.mkdir()
        for name in ["main.py", "task_actions.py", "storage.py"]:
            shutil.copy2(PROJECT / name, self.folder / name)
        (self.folder / "runner.py").write_text(RUNNER, encoding="utf-8")
        self.json_file = self.folder / "tasks.json"
        self.database = self.folder / "tasks.db"
        self.seed(FIXTURE)

    def seed(self, tasks):
        self.json_file.write_text(json.dumps(tasks, ensure_ascii=False), encoding="utf-8")

    def command(self, arguments, inputs="", cwd=None):
        return subprocess.run(
            [sys.executable, "-B"] + arguments,
            input=inputs, text=True, encoding="utf-8", capture_output=True,
            cwd=cwd or self.folder,
            env=dict(os.environ, PYTHONIOENCODING="utf-8"), timeout=12,
        )

    def app(self, inputs, expected_code=0):
        result = self.command([str(self.folder / "runner.py")], inputs, self.outside)
        self.assertEqual(result.returncode, expected_code, result.stdout + result.stderr)
        self.assertNotIn("Traceback", result.stdout + result.stderr)
        return result.stdout

    def rows(self):
        with closing(sqlite3.connect(self.database)) as connection:
            rows = connection.execute(
                "SELECT name, done, due_date FROM tasks ORDER BY position"
            ).fetchall()
        return [dict(name=name, done=bool(done), due_date=due) for name, done, due in rows]

    def test_task_objects_and_independent_methods(self):
        code = '''from task_actions import Task
from datetime import date as RealDate
from unittest.mock import patch
class FixedDate(RealDate):
    @classmethod
    def today(cls): return cls(2026,11,6)
with patch("task_actions.date", FixedDate):
    old=Task("过去",False,"2026-11-05")
    today=Task("今天",False,"2026-11-06")
    future=Task("未来",False,"2026-11-07")
    blank=Task("无日期",False,"")
    assert old.is_overdue() and not today.is_overdue()
    assert not future.is_overdue() and not blank.is_overdue()
    old.complete()
    assert old.done and not today.done and not old.is_overdue()
    old.restore()
    assert old.is_overdue()
    assert old.to_dict()==dict(name="过去",done=False,due_date="2026-11-05")
for args in [("",False,""),("x",1,""),("x",False,"2026-02-30")]:
    try: Task(*args)
    except ValueError: pass
    else: raise AssertionError(args)
'''
        result = self.command(["-c", code])
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_first_migration_and_restart_preserve_json(self):
        original = self.json_file.read_bytes()
        output = self.app("2\n7\n")
        self.assertIn("共 3 条，已完成 1 条，未完成 2", output)
        self.assertIn("已逾期 约会·朱鸢", output)
        self.assertIn("未完成 约会·妮可", output)
        self.assertIn("已完成 约会·格莉丝", output)
        self.assertEqual(self.rows(), FIXTURE)
        self.app("2\n7\n")
        self.assertEqual(self.rows(), FIXTURE)
        self.assertEqual(self.json_file.read_bytes(), original)

    def test_database_is_authoritative_after_import(self):
        self.app("7\n")
        self.seed([dict(name="外部旧数据", done=False)])
        self.app("7\n")
        self.assertEqual(self.rows(), FIXTURE)

    def test_delete_all_does_not_reimport_json(self):
        self.app("3\n1\n3\n1\n3\n1\n7\n")
        self.assertEqual(self.rows(), [])
        self.assertIn("暂无任务", self.app("2\n7\n"))
        self.assertEqual(self.rows(), [])

    def test_empty_start_and_missing_json(self):
        self.json_file.unlink()
        output = self.app("2\n3\n4\n5\n6\nabc\n7\n")
        self.assertIn("暂无任务可搜索", output)
        self.assertIn("无效选择", output)
        self.assertEqual(self.rows(), [])
        self.assertFalse(self.json_file.exists())

    def test_legacy_tasks_without_dates(self):
        self.seed([dict(name="旧约会", done=False)])
        self.assertIn("截止日期 未设置", self.app("2\n7\n"))
        self.assertEqual(self.rows(), [dict(name="旧约会", done=False, due_date="")])

    def test_bad_json_and_records_can_be_fixed_and_retried(self):
        invalid = ["{bad", "{}", "[null]", '[{"name":"x"}]',
                   '[{"name":"x","done":false,"due_date":"2026-02-30"}]']
        for text in invalid:
            with self.subTest(text=text):
                self.json_file.write_text(text, encoding="utf-8")
                self.assertIn("读取任务失败", self.app("7\n", expected_code=1))
                self.assertEqual(self.json_file.read_text(encoding="utf-8"), text)
        self.seed(FIXTURE)
        self.app("7\n")
        self.assertEqual(self.rows(), FIXTURE)

    def test_operations_numbers_dates_and_reload(self):
        output = self.app("4\n1\n5\n3\n3\n2\n1\n约会·简\n2026-02-30\n2026-11-08\n2\n7\n")
        self.assertIn("日期无效", output)
        self.assertIn("已删除任务 约会·格莉丝", output)
        expected = [FIXTURE[1], dict(name="约会·简", done=False, due_date="2026-11-08"),
                    dict(name="约会·朱鸢", done=True, due_date="2026-11-05")]
        self.assertEqual(self.rows(), expected)
        self.assertIn("共 3 条，已完成 1 条，未完成 2", self.app("2\n7\n"))

    def test_search_combinations_and_original_numbers(self):
        for keyword in ["", "约会", "朱鸢", "不存在"]:
            for status in ["1", "2", "3"]:
                with self.subTest(keyword=keyword, status=status):
                    output = self.app("6\n" + keyword + "\n" + status + "\n7\n")
                    expected = [i for i, task in enumerate(FIXTURE, 1)
                                if keyword in task["name"] and
                                (status == "1" or (status == "2" and not task["done"]) or
                                 (status == "3" and task["done"]))]
                    numbers = [int(n) for n in re.findall(r"(\d+) (?:未完成|已完成|已逾期) ", output)]
                    self.assertEqual(numbers, expected)
                    self.assertEqual("没有符合条件的任务" in output, not expected)
        self.assertIn("无效的状态选项", self.app("6\n约会\n0\n7\n"))

    def test_invalid_numbers_repeated_states_and_long_number(self):
        inputs = "4\n3\n5\n1\n3\n0\n3\n-1\n3\nabc\n3\n" + "9" * 5000 + "\n7\n"
        output = self.app(inputs)
        self.assertIn("这条任务已经完成", output)
        self.assertIn("这条任务本来就是未完成", output)
        self.assertEqual(self.rows(), FIXTURE)

    def test_empty_name_optional_date_and_sql_parameters(self):
        name = "约会'); DROP TABLE tasks; --"
        self.app("1\n   \n1\n" + name + "\n\n7\n")
        self.assertIn(dict(name=name, done=False, due_date=""), self.rows())
        self.app("2\n7\n")
        self.assertEqual(len(self.rows()), 4)

    def test_failed_save_rolls_back_and_keeps_memory(self):
        self.app("7\n")
        with closing(sqlite3.connect(self.database)) as connection:
            revision = connection.execute("SELECT revision FROM app_state").fetchone()[0]
            connection.execute("""CREATE TRIGGER reject_task BEFORE INSERT ON tasks
                WHEN NEW.name = '拒绝保存'
                BEGIN SELECT RAISE(ABORT, 'blocked'); END""")
        output = self.app("1\n拒绝保存\n\n7\n2\n", expected_code=1)
        self.assertIn("保存未完成", output)
        self.assertIn("共 4 条", output)
        self.assertEqual(self.rows(), FIXTURE)
        with closing(sqlite3.connect(self.database)) as connection:
            self.assertEqual(connection.execute("SELECT revision FROM app_state").fetchone()[0], revision)

    def test_stale_save_is_rejected(self):
        code = '''import importlib.util
from pathlib import Path
from task_actions import Task

def instance(name):
    spec=importlib.util.spec_from_file_location(name,Path("storage.py"))
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
first=instance("first_storage")
second=instance("second_storage")
a=first.load_tasks()
b=second.load_tasks()
a.append(Task("新窗口",False,""))
first.save_tasks(a)
b.append(Task("旧窗口",False,""))
try: second.save_tasks(b)
except second.StorageError: pass
else: raise AssertionError("stale save accepted")
assert [t.name for t in second.load_tasks()][-1]=="新窗口"
'''
        result = self.command(["-c", code])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.rows()), 4)
        self.assertNotIn("旧窗口", [task["name"] for task in self.rows()])

    def test_concurrent_first_reads_import_once(self):
        def read_once(index):
            return self.command(["-c", "from storage import load_tasks; assert len(load_tasks()) == 3"])
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(read_once, range(6)))
        for result in results:
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.rows(), FIXTURE)

    def test_corrupt_database_reports_error(self):
        original = b"not a sqlite database"
        self.database.write_bytes(original)
        self.assertIn("读取任务失败", self.app("7\n", expected_code=1))
        self.assertEqual(self.database.read_bytes(), original)

    def test_imports_are_quiet_and_do_not_create_database(self):
        result = self.command(["-c", "import main, storage, task_actions"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertFalse(self.database.exists())
        self.assertFalse((self.outside / "tasks.db").exists())


if __name__ == "__main__":
    unittest.main()
