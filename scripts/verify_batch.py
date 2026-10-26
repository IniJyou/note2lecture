"""原创公开样例的批处理验收；只创建新目录，页面状态仍须实际查看后补记。"""

import contextlib
import io
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from verify_markdown import verify  # noqa: E402
from verify_n1 import EXPECTED, checked, labels_in_aux  # noqa: E402

from note2lecture.document import digest  # noqa: E402
from note2lecture.exporter import write_json  # noqa: E402
from note2lecture.tools import ROOT  # noqa: E402


def snapshots(root):
    return {str(path.relative_to(root)): digest(path.read_bytes())
            for path in root.rglob("*") if path.is_file()}


def check_numbering(output, sample):
    labels = labels_in_aux(output / "_build/main.aux")
    assert all(labels.get(key) == value for key, value in EXPECTED[sample].items()), labels


def main():
    root = Path(sys.argv[1]).absolute()
    root.mkdir(parents=True)  # 已有目录直接失败，不清理历史产物。
    inputs = root / "inputs"
    first, last = inputs / "甲 空格/讲义.md", inputs / "乙 空格/讲义.md"
    for path in (first, last):
        (path.parent / "assets").mkdir(parents=True)
    pairs = [
        (ROOT / "examples/01-mean.md", first),
        (ROOT / "examples/assets/mean-flow.png", first.parent / "assets/mean-flow.png"),
        (ROOT / "examples/03-online-mean.md", last),
        (ROOT / "examples/assets/批次 示意.jpg", last.parent / "assets/批次 示意.jpg"),
    ]
    for source, target in pairs:
        shutil.copyfile(source, target)
    bad = inputs / "错误.md"
    bad.write_text(
        "---\ntitle: 原创失败样例\nauthor: Note2Lecture 示例\n---\n\n"
        "故意保留未闭合公式：$x+1。\n", encoding="utf-8",
    )
    (inputs / "未选定.md").write_text("本文件没有被选定，不应参与转换。\n", encoding="utf-8")
    originals = {str(path): digest(path.read_bytes()) for path, _ in pairs}
    before = snapshots(inputs)
    output = root / "批量 输出"
    command = [sys.executable, str(ROOT / "note2lecture.py"), "batch",
               str(first), str(bad), str(last), "-o", str(output)]
    result = subprocess.run(command, capture_output=True, encoding="utf-8", errors="replace",
                            timeout=600, check=False)
    (root / "cli-stdout.json").write_text(result.stdout, encoding="utf-8")
    (root / "cli-stderr.log").write_text(result.stderr, encoding="utf-8")
    report = json.loads(result.stdout)
    assert result.returncode == 2 and report["status"] == "failed", report
    assert report["summary"] == {
        "total": 3, "converted": 2, "failed": 1, "pending": 0, "review_pending": 2,
    }, report
    assert [item["input"] for item in report["items"]] == [str(first), str(bad), str(last)]
    assert [item["output"] for item in report["items"]] == ["001", "002", "003"]
    error = report["items"][1]["diagnostics"][0]
    assert error["code"] == "STRUCTURE_INVALID" and error["line"] == 6, error
    assert not (output / "002/lecture.pdf").exists()
    assert json.loads((output / "batch-summary.json").read_text(encoding="utf-8")) == report
    details = {}
    for folder, path in (("001", first), ("003", last)):
        item = report["items"][int(folder) - 1]
        assert item["status"] == "partial"
        assert item["checks"]["structure"] and item["checks"]["compile"]
        assert all(not item["checks"][key]
                   for key in ("content_review", "page_review", "style_approved"))
        stored = json.loads((output / folder / "diagnostics.json").read_text(encoding="utf-8"))
        assert item["checks"] == stored["checks"] and item["diagnostics"] == stored["diagnostics"]
        with contextlib.redirect_stdout(io.StringIO()):
            verify(path, output / folder, root / "review" / folder, "strict")
        detail = json.loads(
            (root / "review" / folder / "validation.json").read_text(encoding="utf-8")
        )
        check_numbering(output / folder, "01-mean" if folder == "001" else "03-online-mean")
        detail["numbering"] = True
        pages = root / "review" / folder / "pages"
        pages.mkdir()
        checked(["pdftoppm", "-scale-to", "1450", "-png", output / folder / "lecture.pdf",
                 pages / "page"])
        details[folder] = detail
    # 同一命令再次运行必须拒绝覆盖，逐文件摘要也须保持。
    exported = snapshots(output)
    again = subprocess.run(command, capture_output=True, encoding="utf-8", errors="replace",
                           timeout=30, check=False)
    assert again.returncode == 2
    assert json.loads(again.stdout)["diagnostics"][0]["code"] == "OUTPUT_EXISTS"
    assert snapshots(output) == exported
    assert snapshots(inputs) == before
    assert all(digest(Path(path).read_bytes()) == sha for path, sha in originals.items())
    validation = {
        "summary": report["summary"], "exit_code": result.returncode,
        "failed_item_code": error["code"], "failed_item_line": error["line"],
        "selected_only": True, "same_name_and_chinese_spaces": True,
        "input_and_resources_unchanged": True, "public_examples_unchanged": True,
        "existing_batch_unchanged": True, "samples": details, "page_review": False,
    }
    write_json(root / "validation.json", validation)
    print(json.dumps(validation, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
