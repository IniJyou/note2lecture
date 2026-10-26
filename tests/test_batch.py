"""批次编排边界；真实转换与页面另以原创样例端到端验收。"""

import json
from pathlib import Path

import pytest

from note2lecture import batch, cli
from note2lecture.diagnostics import Diagnostic, NoteError
from note2lecture.exporter import write_json


def note(root, name="note.md"):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# 原创笔记\n\n正文与 $x+1$。\n", encoding="utf-8")
    return path


def converted(path, output, quarto, profile):
    output.mkdir()
    (output / "lecture.pdf").write_bytes(b"test artifact")
    (output / "lecture-source.zip").write_bytes(b"test archive")
    result = {
        "status": "partial",
        "checks": {"structure": True, "compile": True, "content_review": False,
                   "page_review": False, "style_approved": False},
        "diagnostics": [],
    }
    write_json(output / "diagnostics.json", result)
    return result


def test_failure_between_same_names_continues_and_preserves_sources(tmp_path, monkeypatch):
    first = note(tmp_path / "甲 空格", "笔记.md")
    invalid = note(tmp_path / "乙", "错误.md")
    last = note(tmp_path / "丙", "笔记.md")
    inputs = [first, invalid, last]
    original = [path.read_bytes() for path in inputs]
    calls = []

    def export(path, output, quarto, profile):
        calls.append((path, quarto, profile))
        # 每项开始前，可查到已完成项；汇总尚未宣称整批完成。
        previous = json.loads((output.parent / "batch-summary.json").read_text(encoding="utf-8"))
        assert previous["status"] == "running"
        assert len(previous["items"]) == len(calls) - 1
        if path == invalid:
            raise NoteError(Diagnostic("STRUCTURE_INVALID", "原创错误定位。", path.name, line=3))
        result = converted(path, output, quarto, profile)
        result["diagnostics"].append(Diagnostic(
            "LOCAL_LINK_NOT_PACKAGED", "仅保留文字。", path.name, severity="warning"
        ).to_dict())
        write_json(output / "diagnostics.json", result)
        return result

    monkeypatch.setattr(batch, "export_document", export)
    output = tmp_path / "导出 批次"
    report = batch.export_batch(inputs, output, "existing-quarto", "markdown")
    assert report["status"] == "failed"
    assert report["summary"] == {
        "total": 3, "converted": 2, "failed": 1, "pending": 0, "review_pending": 2,
    }
    assert [x["status"] for x in report["items"]] == ["partial", "failed", "partial"]
    assert [x["output"] for x in report["items"]] == ["001", "002", "003"]
    assert [x["input"] for x in report["items"]] == [str(x) for x in inputs]
    assert calls == [(path, "existing-quarto", "markdown") for path in inputs]
    for item in report["items"]:
        stored = json.loads((output / item["artifacts"]["diagnostics"]).read_text(encoding="utf-8"))
        assert stored["checks"] == item["checks"]
        assert stored["diagnostics"] == item["diagnostics"]
    assert report["items"][1]["diagnostics"][0]["line"] == 3
    assert report["items"][2]["artifacts"]["pdf"] == "003/lecture.pdf"
    assert [path.read_bytes() for path in inputs] == original
    assert json.loads((output / "batch-summary.json").read_text(encoding="utf-8")) == report


@pytest.mark.parametrize("kind", ["empty_directory", "nonempty_directory", "file"])
def test_existing_batch_output_is_never_reused(tmp_path, monkeypatch, kind):
    path = note(tmp_path)
    output = tmp_path / "existing"
    if kind == "file":
        output.write_bytes(b"keep")
    else:
        output.mkdir()
        if kind == "nonempty_directory":
            (output / "batch-summary.json").write_bytes(b"keep")
    monkeypatch.setattr(batch, "export_document", lambda *args: pytest.fail("不能开始转换"))
    with pytest.raises(NoteError) as error:
        batch.export_batch([path], output)
    assert error.value.diagnostic.code == "OUTPUT_EXISTS"
    if kind == "file":
        assert output.read_bytes() == b"keep"
    elif kind == "nonempty_directory":
        assert (output / "batch-summary.json").read_bytes() == b"keep"
    else:
        assert not list(output.iterdir())


def test_invalid_inputs_and_duplicate_do_not_scan_or_abort(tmp_path, monkeypatch):
    path = note(tmp_path / "selected")
    other = note(tmp_path / "not-selected")
    calls = []

    def export(path, *args):
        calls.append(path)
        return converted(path, *args)

    monkeypatch.setattr(batch, "export_document", export)
    report = batch.export_batch([
        path, path.parent / "." / path.name, tmp_path / "missing.md",
        other.parent, tmp_path / "*.md", note(tmp_path, "wrong.txt"),
    ], tmp_path / "batch")
    assert calls == [path]
    assert report["summary"]["converted"] == 1 and report["summary"]["failed"] == 5
    assert [x["diagnostics"][0]["code"] for x in report["items"][1:]] == [
        "INPUT_DUPLICATE", "RESOURCE_MISSING", "INPUT_INVALID", "RESOURCE_MISSING", "INPUT_INVALID",
    ]
    assert other.read_text(encoding="utf-8").startswith("# 原创")


def test_empty_selection_does_not_create_output(tmp_path):
    output = tmp_path / "batch"
    with pytest.raises(NoteError) as error:
        batch.export_batch([], output)
    assert error.value.diagnostic.code == "BATCH_INPUT_EMPTY"
    assert not output.exists()


def test_unexpected_item_exception_is_isolated(tmp_path, monkeypatch):
    first, last = note(tmp_path, "bad.md"), note(tmp_path, "good.md")

    def export(path, *args):
        if path == first:
            raise RuntimeError("private content must not be printed")
        return converted(path, *args)

    monkeypatch.setattr(batch, "export_document", export)
    report = batch.export_batch([first, last], tmp_path / "batch")
    assert report["summary"]["converted"] == report["summary"]["failed"] == 1
    assert report["items"][0]["diagnostics"][0]["code"] == "BATCH_ITEM_FAILED"
    assert "private content" not in json.dumps(report)
    assert report["items"][1]["checks"]["compile"] is True


def test_pdf_with_failed_layout_is_counted_as_failure(tmp_path, monkeypatch):
    first, last = note(tmp_path, "overflow.md"), note(tmp_path, "good.md")

    def export(path, *args):
        result = converted(path, *args)
        if path == first:
            result["status"] = "failed"
            result["diagnostics"].append(Diagnostic(
                "LAYOUT_OVERFLOW", "存在溢出，不能验收。", path.name
            ).to_dict())
            write_json(args[0] / "diagnostics.json", result)
        return result

    monkeypatch.setattr(batch, "export_document", export)
    report = batch.export_batch([first, last], tmp_path / "batch")
    assert report["status"] == "failed"
    assert report["items"][0]["artifacts"]["pdf"] == "001/lecture.pdf"
    assert report["items"][0]["status"] == "failed"
    assert report["summary"]["failed"] == report["summary"]["converted"] == 1


def test_child_output_conflict_preserves_existing_files(tmp_path):
    path = note(tmp_path)
    output = tmp_path / "batch"

    def progress(*args):
        target = output / "001"
        target.mkdir()
        (target / "lecture.pdf").write_bytes(b"keep")
        (target / "diagnostics.json").write_bytes(b"keep report")

    report = batch.export_batch([path], output, progress=progress)
    assert report["items"][0]["diagnostics"][0]["code"] == "OUTPUT_EXISTS"
    assert report["items"][0]["artifacts"] == {}
    assert (output / "001/lecture.pdf").read_bytes() == b"keep"
    assert (output / "001/diagnostics.json").read_bytes() == b"keep report"


def test_diagnostic_write_failure_remains_visible_in_summary(tmp_path, monkeypatch):
    path = note(tmp_path)
    original_open = Path.open

    def fail(*args):
        raise NoteError(Diagnostic("STRUCTURE_INVALID", "原始错误。", path.name))

    def guarded_open(path, *args, **kwargs):
        if path.name == "diagnostics.json":
            raise PermissionError
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(batch, "export_document", fail)
    monkeypatch.setattr(Path, "open", guarded_open)
    output = tmp_path / "batch"
    report = batch.export_batch([path], output)
    assert [x["code"] for x in report["items"][0]["diagnostics"]] == [
        "STRUCTURE_INVALID", "BATCH_DIAGNOSTIC_IO",
    ]
    assert report["summary"]["failed"] == 1
    assert json.loads((output / "batch-summary.json").read_text(encoding="utf-8")) == report


def test_interruption_keeps_completed_and_pending_counts(tmp_path, monkeypatch):
    inputs = [note(tmp_path, name) for name in ("first.md", "stop.md", "pending.md")]
    calls = []

    def export(path, *args):
        calls.append(path)
        if path == inputs[1]:
            raise KeyboardInterrupt
        return converted(path, *args)

    monkeypatch.setattr(batch, "export_document", export)
    report = batch.export_batch(inputs, tmp_path / "batch")
    assert report["status"] == "interrupted"
    assert report["summary"] == {
        "total": 3, "converted": 1, "failed": 0, "pending": 2, "review_pending": 1,
    }
    assert calls == inputs[:2]
    assert len(report["items"]) == 1


@pytest.mark.parametrize("failure", [False, True])
def test_cli_json_and_exit_code_reflect_any_failure(tmp_path, monkeypatch, capsys, failure):
    first, last = note(tmp_path, "first.md"), note(tmp_path, "last.md")

    def export(path, *args):
        if failure and path == first:
            raise NoteError(Diagnostic("STRUCTURE_INVALID", "输入有误。", path.name))
        return converted(path, *args)

    monkeypatch.setattr(batch, "export_document", export)
    code = cli.main(["batch", str(first), str(last), "--profile", "obsidian",
                     "--quarto", "existing-quarto", "-o", str(tmp_path / "batch")])
    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert code == (2 if failure else 0)
    assert report["status"] == ("failed" if failure else "partial")
    assert report["profile"] == "obsidian"
    assert report["summary"]["review_pending"] == (1 if failure else 2)
    assert "[1/2]" in captured.err and "[2/2]" in captured.err
    assert not report["model_enabled"] and not report["code_execution"]


def test_cli_output_error_reports_batch_not_input_list(tmp_path, monkeypatch, capsys):
    def fail(*args, **kwargs):
        raise PermissionError

    monkeypatch.setattr(cli, "export_batch", fail)
    assert cli.main(["batch", "note.md", "-o", str(tmp_path / "batch")]) == 2
    assert json.loads(capsys.readouterr().out)["diagnostics"][0]["code"] == "BATCH_IO_FAILED"
