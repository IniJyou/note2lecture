"""桌面会话与任务编排；原生窗口和转换器之间不共享可变界面对象。"""

import copy
import json
import os
import secrets
import threading
from datetime import datetime
from pathlib import Path

from .batch import export_batch, failed_report
from .diagnostics import Diagnostic, NoteError
from .document import read_document
from .exporter import export_document
from .tools import ROOT, find_quarto

DEFAULTS = {
    "profile": "markdown", "list_numbering": "auto", "quarto": "", "theme": "light",
    "open_after": True,
}


class GuiError(ValueError):
    """可直接向用户解释的操作错误。"""


class Session:
    def __init__(self, root=ROOT, *, reader=read_document, exporter=export_document,
                 batch_exporter=export_batch, opener=None, quarto_finder=find_quarto):
        self._root = Path(root).absolute()
        self._lock = threading.RLock()
        self._reader, self._exporter, self._batch = reader, exporter, batch_exporter
        self._find_quarto = quarto_finder
        self._opener = opener or os.startfile
        self._files, self._jobs = [], []
        self._active = None
        self._thread = None
        self._stop = threading.Event()
        self._options = dict(DEFAULTS, output_parent=str(self._root / "output"))
        self._settings_path = self._root / ".cache/gui/settings.json"
        self._notice = ""
        try:
            saved = json.loads(self._settings_path.read_text(encoding="utf-8"))
            self._options.update(self._validate_options(saved))
        except FileNotFoundError:
            pass
        except (OSError, ValueError, TypeError):
            self._notice = "上次的界面设置无法读取，已使用默认值。"

    @staticmethod
    def _validate_options(values):
        if not isinstance(values, dict):
            raise GuiError("设置格式无效。")
        clean = {}
        choices = {"profile": {"strict", "markdown", "obsidian"},
                   "list_numbering": {"auto", "preserve"}, "theme": {"light", "dark"}}
        for key, value in values.items():
            if key not in DEFAULTS and key != "output_parent":
                raise GuiError("设置中包含未知选项。")
            if key in choices and (not isinstance(value, str) or value not in choices[key]):
                raise GuiError("请选择有效的笔记格式、编号方式与主题。")
            if key == "open_after" and type(value) is not bool:
                raise GuiError("完成后打开目录选项应为布尔值。")
            if key in {"quarto", "output_parent"} and (
                not isinstance(value, str) or "\x00" in value or len(value) > 4096
            ):
                raise GuiError("工具或输出路径无效。")
            if key == "output_parent" and (not value or not Path(value).is_absolute()):
                raise GuiError("输出位置应为完整的本地目录路径。")
            clean[key] = value
        return clean

    def _idle(self):
        if self._active is not None:
            raise GuiError("当前任务尚未结束，请等待完成或停止后续文件。")

    def snapshot(self):
        with self._lock:
            return copy.deepcopy({"files": self._files, "options": self._options,
                                  "jobs": self._jobs, "active": self._active,
                                  "notice": self._notice})

    def update_options(self, values):
        clean = self._validate_options(values)
        with self._lock:
            self._idle()
            updated = dict(self._options, **clean)
            if updated["profile"] == "strict" and updated["list_numbering"] != "auto":
                raise GuiError("严格规范模式仅接受自动编号，请先切换编号选项。")
            # 只保存界面设置，不保存笔记正文或会话中的文件清单。
            self._settings_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self._settings_path.with_suffix(".tmp")
            temporary.write_text(json.dumps(updated, ensure_ascii=False, indent=2),
                                 encoding="utf-8")
            temporary.replace(self._settings_path)
            self._options = updated
            return self.snapshot()

    def add_files(self, paths):
        with self._lock:
            self._idle()
            candidates = [Path(path).absolute() for path in paths]
            if any(path.suffix.lower() != ".md" or not path.is_file() for path in candidates):
                raise GuiError("请选择存在的 Markdown（.md）文件；不扫描文件夹。")
            seen = {Path(item["path"]).resolve() for item in self._files}
            for path in candidates:
                if path.resolve() in seen:
                    continue
                seen.add(path.resolve())
                self._files.append({"id": secrets.token_hex(8), "path": str(path),
                                    "name": path.name, "bytes": path.stat().st_size})
            return self.snapshot()

    def remove_file(self, identity):
        with self._lock:
            self._idle()
            self._files = [item for item in self._files if item["id"] != identity]
            return self.snapshot()

    def start(self, kind):
        if kind not in {"check", "export"}:
            raise GuiError("未知任务类型。")
        with self._lock:
            self._idle()
            if not self._files:
                raise GuiError("请先添加一篇或多篇 Markdown 笔记。")
            options = copy.deepcopy(self._options)
            files = copy.deepcopy(self._files)
            output = None
            if kind == "export":
                parent = Path(options["output_parent"])
                if parent.exists() and not parent.is_dir():
                    raise GuiError("输出位置不是文件夹，请重新选择。")
                output = parent / (datetime.now().strftime("lecture-%Y%m%d-%H%M%S-")
                                   + secrets.token_hex(3))
            job = {"id": secrets.token_hex(8), "kind": kind, "status": "running",
                   "started": datetime.now().isoformat(timespec="seconds"),
                   "total": len(files), "completed": 0, "current": files[0]["name"],
                   "message": "正在检查笔记…" if kind == "check" else "正在检查与转换笔记…",
                   "output": str(output) if output else None, "items": [], "diagnostics": [],
                   "files": files, "stop_requested": False}
            self._jobs = (self._jobs + [job])[-10:]
            self._active = job["id"]
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, args=(job, files, options, output),
                                            name="note2lecture-convert", daemon=False)
            try:
                self._thread.start()
            except RuntimeError:
                self._active = None
                self._jobs.remove(job)
                raise
            return job["id"]

    def stop_after_current(self):
        with self._lock:
            if self._active is not None:
                self._stop.set()
                job = next(job for job in self._jobs if job["id"] == self._active)
                job["stop_requested"] = True
                job["message"] = "当前文件处理完成后停止；已生成的结果会保留。"
            return self.snapshot()

    def wait(self, timeout=None):
        """供应用退出和工程验证等待；界面通过 snapshot 轮询，不阻塞窗口。"""
        thread = self._thread
        if thread:
            thread.join(timeout)
        return not thread or not thread.is_alive()

    def _progress(self, job, files, index, total, name, output):
        if self._stop.is_set():
            raise KeyboardInterrupt
        items = []
        if output:
            # 只读当前批次自己的已落盘汇总，用于显示完成项；不扫描输入目录。
            try:
                report = json.loads((output / "batch-summary.json").read_text(encoding="utf-8"))
                items = self._batch_items(report, files, output)
            except (OSError, ValueError):
                pass
        with self._lock:
            job.update(current=name, completed=index - 1)
            if items:
                job["items"] = items

    @staticmethod
    def _batch_items(report, files, output):
        result = []
        for item in report["items"]:
            index = item["index"] - 1
            result.append({"source_id": files[index]["id"], "name": files[index]["name"],
                           "status": item["status"], "diagnostics": item["diagnostics"],
                           "checks": item["checks"],
                           "artifacts": {key: str(output / value)
                                         for key, value in item["artifacts"].items()}})
        return result

    @staticmethod
    def _single_item(file, report, output=None):
        artifacts = {}
        if output:
            for key, relative in (("pdf", "lecture.pdf"), ("source_zip", "lecture-source.zip"),
                                  ("source_tex", "lecture-source/main.tex"),
                                  ("diagnostics", "diagnostics.json")):
                if (output / relative).is_file():
                    artifacts[key] = str(output / relative)
        return {"source_id": file["id"], "name": file["name"], "status": report["status"],
                "checks": report.get("checks", {}), "diagnostics": report["diagnostics"],
                "artifacts": artifacts}

    def _run(self, job, files, options, output):
        try:
            quarto = self._find_quarto(options["quarto"] or None)
            if job["kind"] == "check":
                for index, file in enumerate(files, 1):
                    self._progress(job, files, index, len(files), file["name"], None)
                    try:
                        doc = self._reader(Path(file["path"]), quarto, options["profile"],
                                           list_numbering=options["list_numbering"])
                        report = {"status": "checked", "diagnostics": [x.to_dict()
                                  for x in doc.warnings], "checks": {"structure": True}}
                    except NoteError as exc:
                        report = failed_report(exc.diagnostic)
                    except OSError:
                        report = failed_report(Diagnostic(
                            "RESOURCE_MISSING", "无法读取所选笔记或必要资源。", file["name"]))
                    with self._lock:
                        job["items"].append(self._single_item(file, report))
                        job["completed"] = index
                with self._lock:
                    job["status"] = ("failed" if any(x["status"] == "failed"
                                                   for x in job["items"]) else "checked")
            elif len(files) == 1:
                try:
                    report = self._exporter(Path(files[0]["path"]), output, quarto,
                                            options["profile"],
                                            list_numbering=options["list_numbering"])
                except NoteError as exc:
                    report = failed_report(exc.diagnostic)
                with self._lock:
                    job.update(items=[self._single_item(files[0], report, output)],
                               completed=1, status=report["status"])
            else:
                report = self._batch(
                    [Path(file["path"]) for file in files], output, quarto, options["profile"],
                    list_numbering=options["list_numbering"],
                    progress=lambda i, n, name: self._progress(job, files, i, n, name, output),
                )
                with self._lock:
                    job.update(items=self._batch_items(report, files, output),
                               completed=len(report["items"]), status=report["status"],
                               diagnostics=report["diagnostics"])
        except KeyboardInterrupt:
            with self._lock:
                job["status"] = "interrupted"
        except NoteError as exc:
            with self._lock:
                job.update(status="failed", diagnostics=[exc.diagnostic.to_dict()])
        except Exception as exc:
            with self._lock:
                job.update(status="failed", diagnostics=[Diagnostic(
                    "GUI_TASK_FAILED", f"任务未能完成（{type(exc).__name__}）。",
                    "<task>", hint="请查看已有输出；也可用命令行在新目录复现。",
                ).to_dict()])
        finally:
            with self._lock:
                job["current"] = ""
                job["message"] = {"failed": "存在错误，请查看下面的诊断。",
                                  "checked": "输入检查完成，可继续转换。",
                                  "partial": "已生成，待阅读检查。",
                                  "interrupted": "已停止后续文件，已有结果已保留。"}.get(
                                      job["status"], "任务结束。")
                job["finished"] = datetime.now().isoformat(timespec="seconds")
                self._active = None
            if output and output.is_dir() and options["open_after"]:
                try:
                    self._opener(str(output))
                except OSError:
                    with self._lock:
                        job["diagnostics"].append(Diagnostic(
                            "GUI_OPEN_FAILED", "结果已保留，但未能自动打开目录。", "<task>",
                            severity="warning").to_dict())

    def open_result(self, job_id, item_index, kind):
        with self._lock:
            job = next((job for job in self._jobs if job["id"] == job_id), None)
            if job is None:
                raise GuiError("任务已不在当前会话中。")
            if kind == "output":
                target = Path(job["output"]) if job["output"] else None
            else:
                if type(item_index) is not int or not 0 <= item_index < len(job["items"]):
                    raise GuiError("结果条目无效。")
                item = job["items"][item_index]
                if kind == "input":
                    target = Path(next(f["path"] for f in job["files"]
                                       if f["id"] == item["source_id"]))
                    if target.suffix.lower() != ".md" or not target.is_file():
                        raise GuiError("原笔记已移动或无法打开。")
                    self._opener(str(target))
                    return
                if kind == "pdf" and item["status"] == "failed":
                    raise GuiError("此项未通过转换检查，请先查看错误和输出目录。")
                key = {"pdf": "pdf", "source": "source_tex", "diagnostics": "diagnostics"}.get(
                    kind)
                value = item["artifacts"].get(key)
                target = Path(value) if value else None
                if target and kind in {"source", "diagnostics"}:
                    target = target.parent
            if target is None or not target.exists() or not job["output"]:
                raise GuiError("此结果尚未生成，或已被移动。")
            if not target.resolve().is_relative_to(Path(job["output"]).resolve()):
                raise GuiError("结果路径已经指向任务目录之外，拒绝打开。")
            self._opener(str(target))
