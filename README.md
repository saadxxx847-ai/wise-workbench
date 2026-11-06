<!-- github-archive -->
# GitHub 归档与恢复

本项目已按用户要求归档至 https://github.com/saadxxx847-ai/- 。归档核验后将卸载本机软件、删除 `D:\python_learn` 和桌面快捷方式；不删除原有 Python、PyCharm、WebView2 等共享软件。最终执行结果见仓库中的 `ARCHIVE_CLEANUP.md`。

源码、学习记录、自动测试、界面资源、正式 `tasks.db`、旧 JSON 和数据库备份保存在 Git；完整 Windows 桌面运行包保存在 **Releases / v1.0.0**，不把虚拟环境、浏览器缓存、签名密钥和构建缓存提交到仓库。

**恢复桌面软件（不需要重新安装 Python 依赖）**

1. 从 Releases 下载 `zhe-workbench-windows-v1.0.0.zip`，核对附带的 SHA256，完整解压到你选定的目录。
2. 在该目录的 PowerShell 执行 `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\restore_desktop.ps1`。它只更新本机数据目录记录并创建桌面快捷方式。
3. 双击桌面的“哲店长工作台”。软件有独立窗口、自动分配内部端口，关闭窗口后结束内部服务。首次运行会生成新的本地会话密钥。

程序使用系统已有 Microsoft WebView2 Runtime。需要保留完整解压目录及 `desktop` 内的配套文件；不要只移动 EXE。正式数据仍是解压根目录的 `tasks.db`。恢复后软件不会自行从 GitHub同步后续数据。

**从源码恢复开发环境**

使用 Python 3.11（原验收为 3.11.9）：

```powershell
git clone https://github.com/saadxxx847-ai/-.git python_learn
cd python_learn
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe -B -X utf8 -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -X utf8 build_desktop.py
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\restore_desktop.ps1
```

只运行网页可安装 `requirements.txt`；从 Python 启动桌面宿主可安装 `requirements-desktop.txt` 并运行 `desktop_app.py`；重新打包使用 `requirements-build.txt`。EXE 是本项目生成的 Windows 应用，不是签名的商业安装程序。

**归档验收**

43 项自动测试通过，包含 5 项桌面服务/保存重开/单实例/资源与安装路径测试。打包后的 EXE `--check` 已验证资源和正式数据库。原生窗口实际打开并读到真实任务；用户按 Esc 停止后，关闭重开和重复打开的原生界面验收未继续，不将它们记作已通过。

桌面实现及打包由助手完成，不计作用户掌握前端、Flask、WebView、打包或并发技术。下方保留网页版详细说明与历史交付背景。

---

# 哲店长工作台

真实 SQLite 数据驱动的本地个人任务管理器，2026-11-06 完成网页扩展，保留命令行。深色录像店主题，支持桌面和窄屏；页面资源全部在本机，无需外部字体、图片或前端构建工具。

**打开、启动与停止**

网页版需要启动服务后打开 **http://127.0.0.1:5000/**，仅允许本机访问。关闭网页不会停止服务；电脑重启后需要重新启动，不会开机自启。

- 下次启动：在资源管理器中双击本目录的 `start_web.cmd`，脚本会在服务就绪后自动用默认浏览器打开工作台；服务已运行时也会打开网页。首次启动的黑色窗口负责运行服务，需要保留，关闭它也会停止这次运行。
- 停止当前后台服务：双击 `stop_web.cmd`。自己用运行窗口启动时，也可在该窗口按 **Ctrl+C**。
- 提示“工作台已经运行”时直接打开地址；重启先停止再启动。系统文件锁阻止重复实例。
- 若端口被其他程序占用，可运行 `.\.venv\Scripts\python.exe -X utf8 run_web.py --port 5001`，再打开 `http://127.0.0.1:5001/`。

在本目录的 PowerShell 中也可以手动启动：

```powershell
.\.venv\Scripts\python.exe -X utf8 run_web.py
```

需要后台运行时执行以下命令；日志在 `web.stdout.log`、`web.stderr.log`。执行策略选项仅作用于本次脚本进程，不修改系统配置。

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\start_web_background.ps1
```

**网页用法**

1. “下一件小事”填写任务内容，可选截止日期，点“收录任务”。名称最多 200 字，不能空白或换行。无效输入有中文提示，并保留填写内容。
2. 点任务左侧方框完成；再次点已完成方框恢复未完成。
3. 按任务名称搜索，组合“全部、未完成、已完成、已逾期”筛选；点“清除搜索”清空关键词。
4. 点垃圾桶，核对任务名后确认删除；“再想想”或 Esc 可取消。删除后不能在网页内撤销。

**每次成功操作立即保存。** 刷新网页、关闭网页或重启服务后，已保存的操作仍在。任务默认未完成优先，同状态保留原相对顺序。筛选和排序后的按钮按永久身份定位，不依赖显示位置。

统计卡片显示全部任务数量；列表标题和底部显示当前筛选结果数量。未完成且截止日期早于本机当天日期为“已逾期”，当天为“今天到期”，无日期显示“未设截止日期”；完成任务不计入逾期。今日备忘只计算今天到期且未完成的任务。

多标签页修改不同任务互不覆盖；同一任务已被另一页更改，旧页提交会提示刷新。同一次提交连点或刷新重放不会重复添加，也不会把后来恢复的任务重新完成。页面超过一天、密钥重建或表单凭证失效时，刷新再操作。其他标签页的列表需要手动刷新。

**命令行仍可使用**

在 PyCharm 中选择项目 `.venv` 运行 `main.py`，或执行：

```powershell
.\.venv\Scripts\python.exe main.py
```

| 选项 | 功能 |
| --- | --- |
| 1 / 2 / 3 | 添加 / 查看及统计 / 删除任务 |
| 4 / 5 | 完成 / 恢复未完成 |
| 6 | 关键词和状态筛选 |
| 7 | 保存本次改动并退出 |

命令行保持原规则：**选项 7 才保存**；关闭窗口或 Ctrl+C 不保存本次内存修改。网页与命令行使用同一数据库。如果命令行启动后网页写入数据，旧命令行整体保存会被拒绝。请记下旧窗口改动，重新启动核对后处理。更新代码前已启动的旧命令行实例也应关闭重开。

**数据与备份**

- `tasks.db` 是正式数据库，路径固定在项目目录；`tasks.json` 保留为旧迁移备份。仅第一次初始化时导入，清空任务后不会重新导入。
- 升级与浏览器验收基线为 **18 条任务、6 完成、12 未完成**，原 id、顺序、名称、状态、日期逐项一致。工作台开放后已出现新任务和状态操作，收尾为 19 条（8 完成/11 未完成），已全部保留；以后数量随操作变化。
- 本次升级前备份：`backups/tasks-before-web-20261106-180443-8d71f2f4.db`。SQLite 备份接口生成，完整性与全部记录均已核对。`backups/baseline-before-web.json` 是升级前核对快照。
- 数据库新增永久身份 `uid`、行版本 `version` 和 `web_commands` 重复请求记录表，保留 `app_state.revision` 用于命令行保存冲突检查。CLI 保存保留幸存任务身份。网页每次请求独立连接，以短事务更新目标任务、全局版本及提交记录，失败全部回滚。
- 日常备份：先停止网页、正常退出所有命令行实例，再复制 `tasks.db`。恢复也先关闭所有实例，再用备份替换数据库。恢复旧结构备份后，下次运行会再次安全升级；数据回到备份时刻。
- `.web-secret` 是本地签名密钥，不要上传或分享；普通重启复用，删除后会重新生成并使旧页面失效。`.web.pid`、`.web.lock` 是运行辅助文件，服务运行时不要修改。

**环境与依赖**

复用 `D:\python_learn\.venv`，Python 3.11.9、内置 SQLite 3.45.1；未新建虚拟环境或安装系统软件。新增 Flask 3.1.3 处理网页请求，Waitress 3.0.2 运行 Windows 本地服务。所有直接和间接依赖锁定在 `requirements.txt`，已安装并通过 `pip check`。命令行仍只依赖标准库。

重建环境时安装：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

新增包仅位于 `.venv\Lib\site-packages`。继续使用网页时保留；确认停用后可卸载本次新增包，或不再依赖该环境时重建 `.venv`。清理环境前保留源码、数据库和备份。全部版本、来源与清理条件见 `WORKLOG.md`。

**文件与检查**

| 文件 | 用途 |
| --- | --- |
| `main.py` / `task_actions.py` | CLI 入口、Task 与规则 |
| `storage.py` | 共同存储、升级备份、事务和冲突控制 |
| `web_app.py` / `run_web.py` | Flask 应用工厂、请求校验、Waitress 服务与单实例锁 |
| `templates/board.html` / `templates/error.html` | 工作台与中文错误页 |
| `static/style.css` / `static/app.js` / `static/favicon.svg` | 响应式主题、删除确认、按钮保护与图标 |
| `start_web.cmd` / `stop_web.cmd` | 双击启动与停止 |
| `start_web_background.ps1` / `stop_web.ps1` | 后台启动、核对进程身份后停止 |
| `tests/test_project.py` / `tests/test_web.py` | 原有 16 项与新增 19 项隔离测试 |
| `tests/test_launcher.py` | 双击入口、页面就绪等待、已运行实例打开网页的 3 项回归测试 |
| `acceptance/` | 浏览器截图和验收报告 |
| `class_practice.py` / `WORKLOG.md` | 保留的学习代码与记录 |

```powershell
.\.venv\Scripts\python.exe -B -X utf8 -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m pip check
```

**38 项测试全部通过**（原 35 项 + 启动体验回归 3 项），覆盖迁移备份、CLI 兼容、持久化、CSRF/同源/签名/过期校验、页面转义、空白/超长/无效日期、筛选定位、重复提交、并发、回滚与双击启动打开网页。测试使用独立临时数据库。故意注入的数据库故障会打印 ERROR 日志，对应测试仍应为 `ok`，最后结果为 `OK`。

浏览器实际操作完整流程，临时任务已清理。验证刷新及服务重启、双标签冲突、停止及重复启动；检查 1440、768、390、320 像素布局，无横向溢出，控制台无错误。正式数据和备份完整性均为 `ok`。详情见 `acceptance/REPORT.md`。

实现参考：[Flask 安全说明](https://flask.palletsprojects.com/en/stable/web-security/)、[Waitress 官方部署说明](https://flask.palletsprojects.com/en/stable/deploying/waitress/)。非官方同人主题，录像带由本地 CSS 绘制。

本轮代码、环境、整合和验收由助手按用户明确授权交付，不记为用户已经掌握前端、Flask、并发控制或 SQLite。学习情况仍以 `WORKLOG.md` 的练习证据为准。
