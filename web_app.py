"""哲店长工作台 — local Flask application; no network assets required."""
import hmac
import re
import secrets
from datetime import date
from pathlib import Path

from flask import Flask, abort, flash, redirect, render_template, request, session, url_for
from itsdangerous import BadSignature, URLSafeTimedSerializer
from werkzeug.exceptions import HTTPException

from storage import ConflictError, StorageError, TaskStore

ROOT = Path(__file__).resolve().parent
FILTERS = {"all": "全部任务", "pending": "未完成", "done": "已完成", "overdue": "已逾期"}


def create_app(config=None):
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=secrets.token_hex(32),
        DATABASE=ROOT / "tasks.db", LEGACY=ROOT / "tasks.json",
        SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Strict",
        MAX_CONTENT_LENGTH=16384, MAX_FORM_MEMORY_SIZE=16384, MAX_FORM_PARTS=20,
        TRUSTED_HOSTS=["127.0.0.1", "localhost", "[::1]"],
    )
    if config:
        app.config.update(config)
    store = TaskStore(app.config["DATABASE"], app.config["LEGACY"])
    app.extensions["task_store"] = store
    signer = URLSafeTimedSerializer(app.secret_key, salt="workbench-commands-v1")

    def csrf():
        if "csrf" not in session:
            session["csrf"] = secrets.token_hex(32)
        return session["csrf"]

    def command(action, task=None):
        return signer.dumps(dict(action=action, uid=task.uid if task else "",
                                 version=task.version if task else 0,
                                 nonce=secrets.token_hex(24), csrf=csrf()))

    @app.before_request
    def protect_form():
        if request.method != "POST":
            return
        if request.mimetype != "application/x-www-form-urlencoded":
            abort(415, "请使用工作台内的表单提交。")
        origin = request.headers.get("Origin")
        if origin and origin != request.host_url.rstrip("/"):
            abort(403, "请求来源不匹配，请返回工作台重试。")
        if request.headers.get("Sec-Fetch-Site") == "cross-site":
            abort(403, "请求来源不匹配。")
        token = request.form.get("csrf", "")
        expected = session.get("csrf", "")
        if not re.fullmatch(r"[a-f0-9]{64}", token) or not expected or not hmac.compare_digest(token, expected):
            abort(403, "表单校验失效，请刷新工作台后重新操作。")
        if any(len(request.form.getlist(key)) != 1 for key in request.form):
            abort(400, "表单含重复字段，请刷新后重新操作。")

    @app.after_request
    def headers(response):
        response.headers.update({
            "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'",
            "X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY",
            "Referrer-Policy": "same-origin", "Cache-Control": "no-store",
        })
        return response

    def render_board(error=None, form=None, status_code=200):
        keyword = request.values.get("q", "").strip()[:200]
        status = request.values.get("status", "all")
        if status not in FILTERS:
            abort(400, "无效的状态筛选。")
        tasks, revision = store.snapshot()
        tasks.sort(key=lambda task: task.done)
        today = date.today()
        counts = dict(all=len(tasks), pending=sum(not t.done for t in tasks),
                      done=sum(t.done for t in tasks), overdue=sum(t.is_overdue() for t in tasks))
        visible = [t for t in tasks if keyword.casefold() in t.name.casefold() and
                   (status == "all" or status == "pending" and not t.done or
                    status == "done" and t.done or status == "overdue" and t.is_overdue())]
        focus = [t for t in tasks if not t.done and t.due_date and date.fromisoformat(t.due_date) == today]
        return render_template("board.html", tasks=visible, total=counts, filters=FILTERS,
                               status=status, q=keyword, today=today, focus=focus,
                               revision=revision, error=error, form=form or {}, csrf=csrf(),
                               command=command, progress=round(counts["done"] / counts["all"] * 100) if tasks else 0), status_code

    @app.get("/")
    def board():
        return render_board()

    @app.post("/tasks")
    def mutate():
        try:
            payload = signer.loads(request.form.get("command", ""), max_age=86400)
        except BadSignature:
            abort(403, "操作凭证已失效，请刷新后重新操作。")
        if not isinstance(payload, dict) or payload.get("csrf") != session.get("csrf"):
            abort(403, "操作凭证不匹配，请刷新后重新操作。")
        action = payload["action"]
        name = request.form.get("name", "").strip()
        due = request.form.get("due_date", "").strip()
        if action == "add":
            error = None
            if not name:
                error = "给任务起个名字吧，不能只输入空格。"
            elif len(name) > 200:
                error = "任务名称最多 200 个字符，请精简后再提交。"
            elif any(ord(c) < 32 for c in name):
                error = "任务名称不能包含换行或控制字符。"
            if due:
                try:
                    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", due):
                        raise ValueError
                    date.fromisoformat(due)
                except ValueError:
                    error = "截止日期无效，请使用真实日期（年-月-日）。"
            if error:
                return render_board(error, dict(name=name, due_date=due), 422)
        elif action == "delete" and request.form.get("confirm") != "yes":
            abort(400, "删除前需要确认。")
        try:
            message = store.apply(payload["nonce"], action, payload["uid"], payload["version"],
                                  name if action == "add" else "", due if action == "add" else "")
        except ConflictError as error:
            return render_board(str(error), status_code=409)
        flash(message)
        status = request.form.get("status", "all")
        if status not in FILTERS:
            status = "all"
        return redirect(url_for("board", status=status, q=request.form.get("q", "")[:200]), code=303)

    @app.errorhandler(StorageError)
    def storage_error(error):
        app.logger.exception("Database operation failed")
        return render_template("error.html", message=str(error), code=503), 503

    @app.errorhandler(HTTPException)
    def request_error(error):
        messages = {404: "这个页面不存在。", 405: "请使用工作台中的按钮操作。", 413: "提交内容过大，请精简任务名称。"}
        return render_template("error.html", message=messages.get(error.code, error.description), code=error.code), error.code

    return app
