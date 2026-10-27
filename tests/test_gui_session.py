"""桌面任务的内容保护、失败隔离、忙碌状态和结果打开边界。"""

import json
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from note2lecture.batch import export_batch
from note2lecture.desktop import DesktopAPI
from note2lecture.diagnostics import Diagnostic, NoteError
from note2lecture.exporter import write_json
from note2lecture.gui_session import GuiError, Session


def note(root, name="original.md"):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# 原创笔记\n\n内容与 $x$。\n", encoding="utf-8")
    return path


def result(path, output, quarto, profile, **kwargs):
    output.mkdir(parents=True)
    (output / "lecture.pdf").write_bytes(b"fixture artifact")
    (output / "lecture-source").mkdir()
    (output / "lecture-source/main.tex").write_text("fixture source", encoding="utf-8")
    report = {"status": "partial", "checks": {"structure": True, "compile": True,
              "content_review": False, "page_review": False, "style_approved": False},
              "diagnostics": []}
    write_json(output / "diagnostics.json", report)
    return report


def session(tmp_path, **kwargs):
    return Session(tmp_path, opener=kwargs.pop("opener", lambda _: None),
                   quarto_finder=kwargs.pop("quarto_finder", lambda _: "existing-quarto"), **kwargs)


def test_selection_only_stats_selected_files_and_deduplicates_resolved_paths(tmp_path):
    first, second = note(tmp_path / "甲", "原稿.md"), note(tmp_path / "乙", "原稿.md")
    other = note(tmp_path / "未选目录")
    app = session(tmp_path, reader=lambda *args, **kw: pytest.fail("选择时不得读取正文"))
    state = app.add_files([first, first.parent / "." / first.name, second])
    assert [item["path"] for item in state["files"]] == [str(first), str(second)]
    assert other.read_text(encoding="utf-8").startswith("# 原创")
    assert state["jobs"] == [] and not app._settings_path.exists()
    state["files"].clear()
    assert len(app.snapshot()["files"]) == 2


@pytest.mark.parametrize("kind", ["directory", "missing", "extension"])
def test_invalid_selection_does_not_scan_or_partly_add_files(tmp_path, kind):
    valid = note(tmp_path)
    bad = {"directory": tmp_path, "missing": tmp_path / "missing.md",
           "extension": note(tmp_path, "wrong.txt")}[kind]
    app = session(tmp_path)
    with pytest.raises(GuiError):
        app.add_files([valid, bad])
    assert not app.snapshot()["files"]


def test_check_failure_continues_and_keeps_warnings_and_originals(tmp_path):
    paths = [note(tmp_path, name) for name in ("first.md", "bad.md", "last.md")]
    originals = [path.read_bytes() for path in paths]
    calls = []

    def reader(path, quarto, profile, **kwargs):
        calls.append(path)
        if path == paths[1]:
            raise NoteError(Diagnostic("STRUCTURE_INVALID", "原创错误。", path.name, 7, 3))
        return SimpleNamespace(warnings=[Diagnostic("LOCAL_LINK_NOT_PACKAGED", "保留文字。",
                                                    path.name, severity="warning")])

    app = session(tmp_path, reader=reader)
    app.add_files(paths)
    app.start("check")
    assert app.wait(3)
    job = app.snapshot()["jobs"][-1]
    assert calls == paths and job["status"] == "failed" and job["completed"] == 3
    assert [item["status"] for item in job["items"]] == ["checked", "failed", "checked"]
    assert job["items"][1]["diagnostics"][0]["line"] == 7
    assert job["items"][0]["diagnostics"][0]["severity"] == "warning"
    assert [path.read_bytes() for path in paths] == originals
    assert not (tmp_path / "output").exists()


def test_single_export_keeps_partial_and_opens_only_recorded_results(tmp_path):
    path = note(tmp_path)
    opened = []
    app = session(tmp_path, exporter=result, opener=opened.append)
    app.update_options({"open_after": False})
    app.add_files([path])
    identity = app.start("export")
    assert app.wait(3)
    job = app.snapshot()["jobs"][-1]
    assert job["status"] == "partial"
    assert job["items"][0]["checks"]["content_review"] is False
    assert opened == []
    app.open_result(identity, 0, "pdf")
    app.open_result(identity, 0, "source")
    app.open_result(identity, 0, "input")
    assert opened == [str(Path(job["output"]) / "lecture.pdf"),
                      str(Path(job["output"]) / "lecture-source"), str(path)]
    first_output = Path(job["output"])
    app.start("export")
    assert app.wait(3)
    assert app.snapshot()["jobs"][-1]["output"] != str(first_output)
    assert (first_output / "lecture.pdf").read_bytes() == b"fixture artifact"


def test_stop_waits_for_current_and_preserves_batch_summary(tmp_path, monkeypatch):
    from note2lecture import batch

    entered, release = threading.Event(), threading.Event()
    calls = []

    def export(path, output, quarto, profile, **kwargs):
        calls.append(path)
        entered.set()
        assert release.wait(3)
        return result(path, output, quarto, profile, **kwargs)

    monkeypatch.setattr(batch, "export_document", export)
    paths = [note(tmp_path, name) for name in ("one.md", "two.md", "three.md")]
    app = session(tmp_path, batch_exporter=export_batch)
    app.update_options({"open_after": False})
    app.add_files(paths)
    app.start("export")
    try:
        assert entered.wait(3)
        assert app.snapshot()["active"] is not None
        for operation in (lambda: app.start("check"), lambda: app.remove_file("any"),
                          lambda: app.update_options({"theme": "dark"}),
                          lambda: app.add_files([paths[0]])):
            with pytest.raises(GuiError):
                operation()
        app.stop_after_current()
        assert not app.wait(.01)
    finally:
        release.set()
        assert app.wait(3)
    job = app.snapshot()["jobs"][-1]
    report = json.loads((Path(job["output"]) / "batch-summary.json").read_text(encoding="utf-8"))
    assert job["status"] == "interrupted" and job["completed"] == 1
    assert calls == paths[:1] and report["summary"]["pending"] == 2
    assert Path(job["items"][0]["artifacts"]["pdf"]).is_file()


def test_profile_and_source_numbering_are_forwarded_to_batch(tmp_path):
    got = []

    def batch(paths, output, quarto, profile, **kwargs):
        got.append((paths, profile, kwargs["list_numbering"]))
        return {"status": "partial", "items": [], "diagnostics": []}

    app = session(tmp_path, batch_exporter=batch)
    paths = [note(tmp_path, "a.md"), note(tmp_path, "b.md")]
    app.add_files(paths)
    app.update_options({"profile": "obsidian", "list_numbering": "preserve"})
    app.start("export")
    assert app.wait(3)
    assert got == [(paths, "obsidian", "preserve")]


@pytest.mark.parametrize("options", [{"profile": "unknown"}, {"theme": []},
                                     {"open_after": "yes"}, {"output_parent": "relative"},
                                     {"unexpected": "value"}])
def test_invalid_preferences_do_not_replace_saved_settings(tmp_path, options):
    app = session(tmp_path)
    app.update_options({"theme": "dark"})
    saved = app._settings_path.read_bytes()
    with pytest.raises(GuiError):
        app.update_options(options)
    assert app._settings_path.read_bytes() == saved


def test_preferences_survive_without_saving_selected_note_list(tmp_path):
    app = session(tmp_path)
    path = note(tmp_path, "private-fixture.md")
    app.add_files([path])
    app.update_options({"theme": "dark", "open_after": False})
    assert path.name not in app._settings_path.read_text(encoding="utf-8")
    loaded = session(tmp_path).snapshot()
    assert loaded["options"]["theme"] == "dark" and not loaded["files"] and not loaded["jobs"]
    with pytest.raises(GuiError):
        app.update_options({"profile": "strict", "list_numbering": "preserve"})


def test_missing_dependency_is_a_finished_error_and_does_not_export(tmp_path):
    def missing(_):
        raise NoteError(Diagnostic("DEPENDENCY_MISSING", "原创缺项。", "<dependencies>"))

    app = session(tmp_path, quarto_finder=missing,
                  exporter=lambda *a, **kw: pytest.fail("不得执行转换"))
    app.add_files([note(tmp_path)])
    app.start("export")
    assert app.wait(3)
    state = app.snapshot()
    assert state["active"] is None and state["jobs"][-1]["status"] == "failed"
    assert state["jobs"][-1]["diagnostics"][0]["code"] == "DEPENDENCY_MISSING"


def test_failed_pdf_and_unknown_or_escaped_artifacts_cannot_be_opened(tmp_path):
    opened = []

    def failed(*args, **kwargs):
        report = result(*args, **kwargs)
        report["status"] = "failed"
        return report

    app = session(tmp_path, exporter=failed, opener=opened.append)
    app.update_options({"open_after": False})
    app.add_files([note(tmp_path)])
    identity = app.start("export")
    assert app.wait(3)
    for args in ((identity, 0, "pdf"), (identity, 0, "executable"),
                 (identity, 9, "source"), ("unknown-job", 0, "output")):
        with pytest.raises(GuiError):
            app.open_result(*args)
    app._jobs[-1]["items"][0]["artifacts"]["source_tex"] = str(note(tmp_path / "outside"))
    with pytest.raises(GuiError):
        app.open_result(identity, 0, "source")
    assert not opened


def test_native_file_picker_cancel_leaves_selection_unchanged(tmp_path):
    app = session(tmp_path)
    app.add_files([note(tmp_path)])
    api = DesktopAPI(app, SimpleNamespace(FileDialog=SimpleNamespace(OPEN=10)))
    api._window = SimpleNamespace(create_file_dialog=lambda *a, **kw: None)
    before = app.snapshot()
    assert api.choose_files() == {"ok": True, "value": before}
