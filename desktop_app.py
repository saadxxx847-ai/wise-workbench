"""Windows desktop host for the existing, data-compatible workbench."""
import argparse
from contextlib import AbstractContextManager
import ctypes
from ctypes import wintypes
from datetime import datetime
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import secrets
import sys
import threading
import time
import urllib.error
import urllib.request

from waitress import create_server
from web_app import create_app

TITLE = "哲店长工作台"
APP_ID = "RandomPlay.Zhe.Workbench"


def project_root():
    """Keep real data outside the executable/resources and fail on bad installs."""
    if getattr(sys, "frozen", False):
        location = Path(sys.executable).parent / "project-location.json"
        try:
            root = Path(json.loads(location.read_text(encoding="utf-8"))["project_root"])
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise RuntimeError("安装位置记录缺失，请在项目目录重新运行 build_desktop.py。") from error
        if not root.is_absolute():
            raise RuntimeError("安装位置记录必须是完整路径。")
    else:
        root = Path(__file__).resolve().parent
    if not (root / "tasks.db").is_file():
        raise RuntimeError(f"找不到正式任务数据库：{root / 'tasks.db'}。请恢复数据库后重试。")
    return root.resolve()


class InstanceLock(AbstractContextManager):
    """An OS lock is released even if Windows terminates the application."""
    def __init__(self, folder):
        self.folder = Path(folder)
        self.file = None
        self.acquired = False

    def __enter__(self):
        import msvcrt
        self.folder.mkdir(parents=True, exist_ok=True)
        self.file = (self.folder / "app.lock").open("a+b")
        if self.file.seek(0, 2) == 0:
            self.file.write(b"0")
            self.file.flush()
        self.file.seek(0)
        try:
            msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            self.acquired = True
        except OSError:
            self.file.close()
            self.file = None
        return self

    def __exit__(self, *args):
        if self.file:
            self.file.close()
        self.file = None
        self.acquired = False


def activate_existing(folder):
    """Bring this application's existing window to the front, by recorded PID."""
    user32 = ctypes.windll.user32
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsIconic.argtypes = [wintypes.HWND]
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    for _ in range(30):
        try:
            pid = json.loads((Path(folder) / "state.json").read_text(encoding="utf-8"))["pid"]
        except (OSError, ValueError, KeyError):
            time.sleep(0.1)
            continue
        found = []

        @callback_type
        def visit(hwnd, _):
            owner = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
            if owner.value == pid and user32.IsWindowVisible(hwnd):
                found.append(hwnd)
            return True

        user32.EnumWindows(visit, 0)
        if found:
            hwnd = found[0]
            user32.ShowWindow(hwnd, 9 if user32.IsIconic(hwnd) else 5)
            user32.SetForegroundWindow(hwnd)
            return True
        time.sleep(0.1)
    return False


class DesktopBackend(AbstractContextManager):
    """Own a loopback-only server whose lifetime matches the native window."""
    def __init__(self, root):
        self.root = Path(root)
        self.server = None
        self.thread = None
        self.url = None

    def __enter__(self):
        secret_file = self.root / ".web-secret"
        try:
            with secret_file.open("x", encoding="ascii") as file:
                file.write(secrets.token_hex(32))
        except FileExistsError:
            pass
        app = create_app(dict(DATABASE=self.root / "tasks.db", LEGACY=self.root / "tasks.json",
                              SECRET_KEY=secret_file.read_text(encoding="ascii").strip(),
                              SESSION_COOKIE_NAME="zhe_desktop"))
        app.extensions["task_store"].snapshot()
        self.server = create_server(app, host="127.0.0.1", port=0, threads=4, map={},
                                    max_request_body_size=16384, clear_untrusted_proxy_headers=True)
        self.url = f"http://127.0.0.1:{self.server.effective_port}/"
        self.thread = threading.Thread(target=self.server.run, daemon=True, name="workbench-http")
        self.thread.start()
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            try:
                with opener.open(self.url, timeout=0.5) as response:
                    if response.status == 200:
                        logging.info("Desktop backend ready at %s", self.url)
                        return self
            except (urllib.error.URLError, OSError):
                time.sleep(0.05)
        self.__exit__(None, None, None)
        raise RuntimeError("工作台启动超时，请稍后重新打开。")

    def __exit__(self, *args):
        if self.server:
            self.server.close()
        if self.thread:
            self.thread.join(timeout=3)
        self.server = self.thread = None
        logging.info("Desktop backend stopped")


def configure_logging(folder):
    folder.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(folder / "desktop.log", maxBytes=1024*1024, backupCount=2, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logging.getLogger().addHandler(handler)
    logging.getLogger().setLevel(logging.INFO)


def self_check(root, folder):
    with DesktopBackend(root) as backend:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        checks = {}
        for path in ["", "static/style.css", "static/app.js", "static/favicon.svg"]:
            with opener.open(backend.url + path, timeout=5) as response:
                checks[path or "/"] = dict(status=response.status, bytes=len(response.read()))
        result = dict(time=datetime.now().astimezone().isoformat(), database=str(root / "tasks.db"),
                      frozen=bool(getattr(sys,"frozen",False)), resources=checks)
    (folder / "self-check.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=TITLE)
    parser.add_argument("--check", action="store_true", help="检查打包资源与后端后退出")
    args = parser.parse_args()
    folder = None
    try:
        root = project_root()
        folder = root / ".desktop"
        configure_logging(folder)
        if args.check:
            self_check(root, folder)
            return 0
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
        with InstanceLock(folder) as lock:
            if not lock.acquired:
                activate_existing(folder)
                return 0
            with DesktopBackend(root) as backend:
                import webview
                webview.settings["ALLOW_FILE_URLS"] = False
                webview.create_window(TITLE, backend.url, width=1240, height=840,
                                      min_size=(860,600), maximized=True,
                                      background_color="#131513", text_select=True)
                state_file = folder / "state.json"
                state_file.write_text(json.dumps(dict(pid=os.getpid(), url=backend.url)), encoding="utf-8")
                try:
                    webview.start(gui="edgechromium", debug=False, private_mode=False,
                                  storage_path=str(folder / "webview"),
                                  icon=str(Path(__file__).parent / "static" / "app.ico"))
                finally:
                    state_file.unlink(missing_ok=True)
        return 0
    except Exception as error:
        logging.exception("Desktop startup failed")
        detail = f"{TITLE}未能启动。\n\n{error}"
        if folder:
            detail += f"\n\n详细记录：{folder / 'desktop.log'}"
        ctypes.windll.user32.MessageBoxW(None, detail, TITLE, 0x10)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
