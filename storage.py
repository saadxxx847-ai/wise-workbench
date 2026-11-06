"""Shared SQLite storage: CLI snapshots and atomic, versioned web commands."""
import hashlib
import json
import sqlite3
import uuid
from contextlib import closing, contextmanager
from datetime import datetime
from pathlib import Path

from task_actions import Task

DATABASE_FILE = Path(__file__).resolve().parent / "tasks.db"
LEGACY_FILE = Path(__file__).resolve().parent / "tasks.json"
# CLI-only. Web requests use TaskStore and row versions.
_loaded_revision = None


class StorageError(Exception):
    """读取、迁移或保存任务失败。"""


class ConflictError(StorageError):
    """A stale page or conflicting repeated command must be refreshed."""


def _read_legacy_tasks(path=None):
    path = Path(path or LEGACY_FILE)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError("旧任务文件格式有误，请检查 tasks.json") from error
    if not isinstance(data, list):
        raise ValueError("旧任务文件应当包含任务列表")
    tasks = []
    for number, item in enumerate(data, start=1):
        if not isinstance(item, dict) or "name" not in item or "done" not in item:
            raise ValueError(f"旧任务文件的第 {number} 条任务缺少名称或状态")
        tasks.append(Task(item["name"], item["done"], item.get("due_date", "")))
    return tasks


def _task_rows(task_list):
    rows = []
    for position, task in enumerate(task_list):
        if not isinstance(task, Task):
            raise ValueError("保存的数据必须是 Task 对象")
        item = task.to_dict()
        rows.append((position, item["name"], int(item["done"]), item["due_date"]))
    return rows


def _upgrade(connection, path):
    columns = {row[1] for row in connection.execute("PRAGMA table_info(tasks)")}
    if "uid" in columns:
        return
    # The caller already excludes writers; backup reads the pre-migration commit.
    folder = path.parent / "backups"
    folder.mkdir(exist_ok=True)
    backup = folder / f"{path.stem}-before-web-{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:8]}.db"
    with closing(sqlite3.connect(path)) as source, closing(sqlite3.connect(backup)) as target:
        source.backup(target)
        if target.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("升级前的数据库备份校验失败")
    before = connection.execute("SELECT id,position,name,done,due_date FROM tasks ORDER BY position").fetchall()
    connection.execute("ALTER TABLE tasks ADD COLUMN uid TEXT")
    connection.execute("ALTER TABLE tasks ADD COLUMN version INTEGER NOT NULL DEFAULT 0")
    connection.executemany("UPDATE tasks SET uid=? WHERE id=?", [(uuid.uuid4().hex, r[0]) for r in before])
    after = connection.execute("SELECT id,position,name,done,due_date FROM tasks ORDER BY position").fetchall()
    if before != after:
        raise ValueError("升级数据逐项核对失败，已取消升级")


@contextmanager
def _database(database_file=None, legacy_file=None):
    path = Path(database_file or DATABASE_FILE)
    connection = sqlite3.connect(path, timeout=5)
    try:
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='tasks'").fetchone()
            if existing:
                _upgrade(connection, path)
            connection.execute("""CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY,
                position INTEGER NOT NULL UNIQUE,
                name TEXT NOT NULL CHECK (length(trim(name)) > 0),
                done INTEGER NOT NULL CHECK (done IN (0, 1)),
                due_date TEXT NOT NULL,
                uid TEXT NOT NULL,
                version INTEGER NOT NULL DEFAULT 0
            )""")
            connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS tasks_uid ON tasks(uid)")
            connection.execute("""CREATE TABLE IF NOT EXISTS app_state (
                id INTEGER PRIMARY KEY CHECK (id = 1), revision INTEGER NOT NULL)""")
            connection.execute("""CREATE TABLE IF NOT EXISTS web_commands (
                request_key TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, message TEXT NOT NULL)""")
            state = connection.execute("SELECT revision FROM app_state WHERE id=1").fetchone()
            if state is None:
                legacy_tasks = _read_legacy_tasks(legacy_file)
                connection.executemany(
                    "INSERT INTO tasks (position,name,done,due_date,uid) VALUES (?,?,?,?,?)",
                    [(*row, uuid.uuid4().hex) for row in _task_rows(legacy_tasks)],
                )
                connection.execute("INSERT INTO app_state (id,revision) VALUES (1,0)")
            yield connection
    finally:
        connection.close()


def _read_tasks(connection):
    return [Task(name, bool(done), due, uid, version) for name, done, due, uid, version in connection.execute(
        "SELECT name,done,due_date,uid,version FROM tasks ORDER BY position")]


def load_tasks():
    global _loaded_revision
    try:
        with _database() as connection:
            revision = connection.execute("SELECT revision FROM app_state WHERE id=1").fetchone()[0]
            tasks = _read_tasks(connection)
        _loaded_revision = revision
        return tasks
    except (sqlite3.Error, OSError, ValueError) as error:
        raise StorageError(f"读取任务失败：{error}") from error


def save_tasks(task_list):
    """CLI all-or-nothing save, preserving surviving task identities."""
    global _loaded_revision
    try:
        rows = _task_rows(task_list)
        identities = [task.uid or uuid.uuid4().hex for task in task_list]
        if len(set(identities)) != len(identities):
            raise ValueError("任务身份重复")
        with _database() as connection:
            revision = connection.execute("SELECT revision FROM app_state WHERE id=1").fetchone()[0]
            if _loaded_revision is not None and revision != _loaded_revision:
                raise StorageError("任务已被另一个程序更新。请保留当前窗口的任务信息，重新启动后核对，避免覆盖新数据。")
            existing = {r[0]: r[1:] for r in connection.execute("SELECT uid,name,done,due_date,version FROM tasks")}
            for task in task_list:
                if task.uid and task.uid not in existing:
                    raise ConflictError("任务已不存在，请重新读取后核对。")
            connection.execute("UPDATE tasks SET position=-position-1")
            for uid in existing.keys() - set(identities):
                connection.execute("DELETE FROM tasks WHERE uid=?", (uid,))
            versions = []
            for row, uid in zip(rows, identities):
                position, name, done, due = row
                if uid in existing:
                    old_name, old_done, old_due, version = existing[uid]
                    version += int((name, done, due) != (old_name, old_done, old_due))
                    connection.execute("UPDATE tasks SET position=?,name=?,done=?,due_date=?,version=? WHERE uid=?",
                                       (position, name, done, due, version, uid))
                else:
                    version = 0
                    connection.execute("INSERT INTO tasks (position,name,done,due_date,uid) VALUES (?,?,?,?,?)", (*row, uid))
                versions.append(version)
            connection.execute("UPDATE app_state SET revision=revision+1 WHERE id=1")
        for task, uid, version in zip(task_list, identities, versions):
            task.uid, task.version = uid, version
        _loaded_revision = revision + 1
    except (sqlite3.Error, OSError, ValueError) as error:
        raise StorageError(f"保存任务失败：{error}") from error


class TaskStore:
    """Each request owns its connection, transaction and expected row version."""
    def __init__(self, database_file=None, legacy_file=None):
        self.path = Path(database_file or DATABASE_FILE)
        self.legacy = Path(legacy_file or LEGACY_FILE)

    def snapshot(self):
        try:
            with _database(self.path, self.legacy) as connection:
                tasks = _read_tasks(connection)
                revision = connection.execute("SELECT revision FROM app_state WHERE id=1").fetchone()[0]
                return tasks, revision
        except (sqlite3.Error, OSError, ValueError) as error:
            raise StorageError("读取任务失败，请检查数据库是否可用。") from error

    def apply(self, request_key, action, uid="", version=0, name="", due_date=""):
        fingerprint = hashlib.sha256(json.dumps([action, uid, version, name, due_date], ensure_ascii=False).encode()).hexdigest()
        try:
            with _database(self.path, self.legacy) as connection:
                previous = connection.execute("SELECT fingerprint,message FROM web_commands WHERE request_key=?", (request_key,)).fetchone()
                if previous:
                    if previous[0] != fingerprint:
                        raise ConflictError("重复请求内容发生变化，请刷新后重新提交。")
                    return previous[1]
                if action == "add":
                    task = Task(name, False, due_date)
                    position = connection.execute("SELECT COALESCE(MAX(position),-1)+1 FROM tasks").fetchone()[0]
                    connection.execute("INSERT INTO tasks (position,name,done,due_date,uid) VALUES (?,?,?,?,?)",
                                       (position, task.name, 0, task.due_date, uuid.uuid4().hex))
                    message = "新任务已收录，开始行动吧。"
                elif action in {"complete", "restore", "delete"}:
                    row = connection.execute("SELECT version FROM tasks WHERE uid=?", (uid,)).fetchone()
                    if row is None or row[0] != version:
                        raise ConflictError("这条任务已在其他窗口更新或删除。请刷新后再操作。")
                    if action == "delete":
                        connection.execute("DELETE FROM tasks WHERE uid=?", (uid,))
                        message = "任务已删除。"
                    else:
                        connection.execute("UPDATE tasks SET done=?,version=version+1 WHERE uid=?", (int(action == "complete"), uid))
                        message = "委托完成，辛苦了，店长。" if action == "complete" else "任务已恢复为未完成。"
                else:
                    raise ValueError("无效操作")
                connection.execute("UPDATE app_state SET revision=revision+1 WHERE id=1")
                connection.execute("INSERT INTO web_commands VALUES (?,?,?)", (request_key, fingerprint, message))
                return message
        except (sqlite3.Error, OSError, ValueError) as error:
            raise StorageError("保存失败，本次操作未写入。请稍后重试。") from error
