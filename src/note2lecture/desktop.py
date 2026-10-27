"""pywebview 仅承载本地界面；向页面暴露有限的会话操作。"""

import argparse
import json
import sys
import threading
from pathlib import Path

from .gui_session import GuiError, Session
from .tools import ROOT

ASSETS = Path(__file__).with_name("gui_assets")


def render_html():
    html = (ASSETS / "index.html").read_text(encoding="utf-8")
    return html.replace("/* APP_CSS */", (ASSETS / "app.css").read_text(encoding="utf-8")).replace(
        "/* APP_JS */", (ASSETS / "app.js").read_text(encoding="utf-8"))


class DesktopAPI:
    def __init__(self, session, webview):
        self._session, self._webview = session, webview
        self._window = None
        self._dialog_lock = threading.Lock()

    def _call(self, action):
        try:
            return {"ok": True, "value": action()}
        except (GuiError, OSError, ValueError, TypeError) as exc:
            message = str(exc) if isinstance(exc, GuiError) else "无法完成操作，请检查路径和权限。"
            return {"ok": False, "message": message}

    def get_state(self):
        return self._call(self._session.snapshot)

    def choose_files(self):
        def choose():
            with self._dialog_lock:
                self._session._idle()
                paths = self._window.create_file_dialog(
                    self._webview.FileDialog.OPEN, allow_multiple=True,
                    file_types=("Markdown (*.md)",),
                )
                return self._session.add_files(paths or [])
        return self._call(choose)

    def choose_path(self, kind):
        def choose():
            with self._dialog_lock:
                self._session._idle()
                if kind == "output_parent":
                    paths = self._window.create_file_dialog(self._webview.FileDialog.FOLDER)
                elif kind == "quarto":
                    paths = self._window.create_file_dialog(
                        self._webview.FileDialog.OPEN, file_types=("Quarto (quarto.exe)",))
                else:
                    raise GuiError("未知的路径选择类型。")
                return self._session.update_options({kind: str(paths[0])}) if paths else (
                    self._session.snapshot())
        return self._call(choose)

    def remove_file(self, identity):
        return self._call(lambda: self._session.remove_file(identity))

    def update_options(self, values):
        return self._call(lambda: self._session.update_options(values))

    def start(self, kind):
        return self._call(lambda: self._session.start(kind))

    def stop_after_current(self):
        return self._call(self._session.stop_after_current)

    def open_result(self, job_id, item_index, kind):
        return self._call(lambda: self._session.open_result(job_id, item_index, kind))


def create_app(webview, session=None, *, hidden=False):
    session = session or Session()
    api = DesktopAPI(session, webview)
    window = webview.create_window(
        "Note2Lecture · 笔记转讲义", html=render_html(), js_api=api,
        width=1280, height=940, min_size=(1000, 720), text_select=True,
        background_color="#ffffff", hidden=hidden,
    )
    api._window = window

    def on_closing():
        if session.snapshot()["active"] is not None:
            # 原生窗口保持打开，不强杀正在生成的源包和 TeX 子进程。
            if window.create_confirmation_dialog(
                "转换仍在进行", "是否在当前文件完成后停止后续文件？\n"
                "已有结果会保留；任务结束后可关闭窗口。",
            ):
                session.stop_after_current()
            return False
        return True

    window.events.closing += on_closing
    return window, api, session


def main(argv=None):
    parser = argparse.ArgumentParser(description="Note2Lecture 本地桌面界面")
    parser.add_argument("--debug", action="store_true", help="显示界面调试工具")
    args = parser.parse_args(argv)
    if sys.platform != "win32":
        print("当前桌面版仅验收 Windows；其他系统请使用命令行入口。", file=sys.stderr)
        return 2
    try:
        import webview
    except ImportError:
        print("缺少可选 GUI 依赖。请在本项目环境执行：\n"
              r".\.venv\Scripts\python.exe -m pip install -r requirements-gui.txt",
              file=sys.stderr)
        return 2
    try:
        # 窗口只装入本地 HTML，不提供笔记浏览服务器或下载入口。
        webview.settings["ALLOW_DOWNLOADS"] = False
        webview.settings["ALLOW_FILE_URLS"] = False
        create_app(webview)
        storage = ROOT / ".cache/gui/webview"
        storage.mkdir(parents=True, exist_ok=True)
        webview.start(gui="edgechromium", debug=args.debug, private_mode=True,
                      storage_path=str(storage))
    except Exception as exc:
        print(json.dumps({"status": "failed", "message": "桌面窗口未能启动，请确认 WebView2 "
                          "与 GUI 依赖可用。", "error_type": type(exc).__name__},
                         ensure_ascii=False), file=sys.stderr)
        return 2
    return 0
