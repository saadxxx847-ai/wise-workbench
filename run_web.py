"""Run the local workbench with a Windows-compatible WSGI server."""
import argparse
import os
from pathlib import Path
import threading
import time
import urllib.error
import urllib.request
import webbrowser

from waitress import create_server
from web_app import create_app


def open_workbench(url):
    """Open the default browser only after the local HTTP server is ready."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        try:
            with opener.open(url, timeout=0.4) as response:
                ready = response.status == 200
        except (urllib.error.URLError, OSError):
            ready = False
        if ready:
            try:
                if webbrowser.open(url, new=2):
                    print(f"已打开默认浏览器：{url}", flush=True)
                    return True
            except (OSError, webbrowser.Error):
                pass
            break
        time.sleep(0.1)
    print(f"未能自动打开页面，请在浏览器地址栏输入：{url}", flush=True)
    return False


def main():
    parser = argparse.ArgumentParser(description="哲店长工作台（仅本机访问）")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--open-browser", action="store_true", help="服务就绪后自动打开浏览器")
    args = parser.parse_args()
    url = f"http://127.0.0.1:{args.port}/"
    root = Path(__file__).resolve().parent
    # Windows venv launchers may spawn base Python. An OS lock, rather than a
    # process-name guess or a stale PID file, enforces a single local instance.
    import msvcrt
    lock_file = (root / ".web.lock").open("a+b")
    if lock_file.seek(0, 2) == 0:
        lock_file.write(b"0")
        lock_file.flush()
    lock_file.seek(0)
    try:
        msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        lock_file.close()
        print("工作台已经运行，请打开 http://127.0.0.1:5000；如需重启先运行 stop_web.cmd。", flush=True)
        if args.open_browser:
            open_workbench(url)
        return
    # Session/form signatures survive ordinary restarts. This file is local-only.
    secret_path = root / ".web-secret"
    try:
        with secret_path.open("x", encoding="ascii") as file:
            import secrets
            file.write(secrets.token_hex(32))
    except FileExistsError:
        pass
    app = create_app({"SECRET_KEY": secret_path.read_text(encoding="ascii").strip()})
    app.extensions["task_store"].snapshot()
    server = create_server(app, host="127.0.0.1", port=args.port, threads=4,
                           max_request_body_size=16384, clear_untrusted_proxy_headers=True)
    pid_path = root / ".web.pid"
    pid_path.write_text(str(os.getpid()), encoding="ascii")
    print(f"哲店长工作台已启动：http://127.0.0.1:{args.port}", flush=True)
    print("本窗口按 Ctrl+C，或双击 stop_web.cmd 停止。任务操作成功后立即保存。", flush=True)
    if args.open_browser:
        threading.Thread(target=open_workbench, args=(url,), daemon=True).start()
    try:
        server.run()
    except KeyboardInterrupt:
        pass
    finally:
        server.close()
        if pid_path.exists() and pid_path.read_text(encoding="ascii").strip() == str(os.getpid()):
            pid_path.unlink()
        lock_file.close()


if __name__ == "__main__":
    main()
