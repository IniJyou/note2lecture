"""固定 N1 验收：新目录、真实编译、源包移植与内容核对。页面仍需实际查看。"""

import json
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from note2lecture.document import digest, read_document  # noqa: E402
from note2lecture.exporter import export_document, write_json  # noqa: E402
from note2lecture.tools import ROOT, find_quarto, run  # noqa: E402

EXPECTED = {
    "01-mean": {
        "sec-mean": "1",
        "sec-steps": "1.1",
        "sec-check": "1.1.1",
        "sec-code": "2",
        "eq-mean": "1",
        "fig-mean-flow": "1",
    },
    "02-projection": {
        "sec-direction": "1",
        "sec-nearest": "2",
        "def-projection": "1",
        "lem-orthogonal": "1",
        "thm-nearest": "1",
        "exm-two-dimensional": "1",
        "eq-projection": "1",
        "eq-distance": "2",
    },
    "03-online-mean": {
        "sec-update": "1",
        "sec-trace": "1.1",
        "sec-merge": "2",
        "sec-state": "2.1",
        "sec-review": "3",
        "eq-online-mean": "1",
        "eq-merge-mean": "2",
        "tbl-mean-trace": "1",
        "fig-batches": "1",
    },
}


def checked(command, cwd=None):
    result = run(command, cwd=cwd)
    if result.returncode:
        raise RuntimeError(f"验收命令失败：{command[0]}\n{result.stderr[-500:]}")
    return result.stdout


def labels_in_aux(path):
    return dict(re.findall(r"\\newlabel\{([^}]+)\}\{\{([^}]*)\}", path.read_text(encoding="utf-8")))


def prose_tokens(value):
    if isinstance(value, list):
        for child in value:
            yield from prose_tokens(child)
    elif isinstance(value, dict) and "t" in value:
        if value["t"] in {"Math", "Code", "CodeBlock", "Cite"}:
            return
        if value["t"] == "Str":
            text = value["c"]
            if len(text) >= 3 and not text.startswith("{#"):
                yield text
        else:
            yield from prose_tokens(value.get("c"))


def content_check(doc, folder):
    package = folder / "lecture-source"
    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    tex = (package / "main.tex").read_text(encoding="utf-8")
    assert digest(doc.path.read_bytes()) == doc.sha256, "原笔记被修改"
    assert all(x["text"] in tex for x in doc.math), "公式正文发生变化"
    for code in doc.code:
        assert (package / "code" / (digest(code.encode()) + ".txt")).read_bytes() == code.encode()
    for resource in doc.resources:
        assert digest((package / resource["packed"]).read_bytes()) == resource["sha256"]
        assert digest((doc.path.parent / resource["original"]).read_bytes()) == resource["sha256"]
    assert manifest["model_enabled"] is False and manifest["code_execution"] is False
    text = checked(["pdftotext", "-layout", folder / "lecture.pdf", "-"])
    normalized = re.sub(r"\s+", "", text)
    missing = [
        x for x in prose_tokens(doc.ast["blocks"]) if re.sub(r"\s+", "", x) not in normalized
    ]
    assert not missing, f"PDF 缺少正文词段：{missing[:5]}"
    assert not re.search(r"N2L_SOURCE|\?\?|@(?:thm|eq|sec)-|\{#", text)
    assert not re.search(r"(?<![A-Za-z0-9])[A-Za-z]:[/\\]", tex), "源包依赖私人绝对路径"
    pages = int(re.search(r"Pages:\s+(\d+)", checked(["pdfinfo", folder / "lecture.pdf"]))[1])
    return {
        "pages": pages,
        "math_exact": len(doc.math),
        "code_exact": len(doc.code),
        "prose_tokens": len(list(prose_tokens(doc.ast["blocks"]))),
        "input_unchanged": True,
    }


def recompile(package, target):
    # target 必须是新目录；此脚本不清理或覆盖旧目录。
    if target.exists():
        raise RuntimeError("重编译目录已存在，拒绝覆盖")
    shutil.copytree(package, target)
    previous = None
    for _ in range(4):
        checked(
            [
                "xelatex",
                "-no-shell-escape",
                "-halt-on-error",
                "-interaction=nonstopmode",
                "-recorder",
                "main.tex",
            ],
            cwd=target,
        )
        # 新目录的目录页数可能改变正文页码；等待辅助文件稳定，不能只算编译次数。
        current = tuple(
            (target / ("main" + suffix)).read_bytes()
            if (target / ("main" + suffix)).exists() else None
            for suffix in (".aux", ".toc", ".out")
        )
        log = (target / "main.log").read_text(encoding="utf-8", errors="replace")
        if current == previous and not re.search(r"Rerun to get|Label\(s\) may have changed", log):
            break
        previous = current
    else:
        raise AssertionError("源包重编译四轮后目录与引用仍未收敛。")
    assert not re.search(
        r"Missing character:|Overfull \\[hv]box|undefined references",
        (target / "main.log").read_text(encoding="utf-8", errors="replace"),
    )
    recorder = (target / "main.fls").read_text(encoding="utf-8", errors="replace")
    for forbidden in (str(ROOT / "examples"), str(package)):
        assert forbidden.replace("\\", "/").lower() not in recorder.replace("\\", "/").lower()
    return labels_in_aux(target / "main.aux")


def extra_checks(root):
    """章节重排与缩短版心的分页副本；只写新目录，保留既有诊断。"""
    variants = root / "variants"
    original = (ROOT / "examples/02-projection.md").read_text(encoding="utf-8")
    front = re.match(r"\A---\n.*?\n---\n", original, re.S)[0]
    first, second = original[len(front) :].split("# 最近点性质", 1)
    changed = variants / "swap.md"
    if changed.exists():
        raise RuntimeError("重排副本已存在，拒绝覆盖")
    changed.write_text(front + "# 最近点性质" + second + "\n" + first, encoding="utf-8")
    report = export_document(changed, variants / "swap-output", find_quarto())
    assert report["status"] == "partial", report
    labels = labels_in_aux(variants / "swap-output/_build/main.aux")
    assert labels["sec-nearest"] == "1" and labels["sec-direction"] == "2"
    assert labels["eq-distance"] == "1" and labels["eq-projection"] == "2"
    boundary = variants / "pagination-source"
    if boundary.exists():
        raise RuntimeError("分页副本已存在，拒绝覆盖")
    shutil.copytree(root / "02-projection/lecture-source", boundary)
    tex = (boundary / "main.tex").read_text(encoding="utf-8")
    tex = tex.replace("bottom=24mm", "bottom=105mm")
    extra = (
        "\\par 这段文字仅用于跨页边界检查。假设仍为 $u\\ne0$，正文与题头应保持连续，"
        "页面不能裁切内容，也不能把下一段证明误放进当前结论中。\n"
    ) * 8
    tex = tex.replace("\\end{theorem}", extra + "\\end{theorem}", 1)
    (boundary / "main.tex").write_text(tex, encoding="utf-8")
    for _ in range(2):
        checked(
            [
                "xelatex",
                "-no-shell-escape",
                "-halt-on-error",
                "-interaction=nonstopmode",
                "main.tex",
            ],
            cwd=boundary,
        )
    log = (boundary / "main.log").read_text(encoding="utf-8", errors="replace")
    assert not re.search(r"Missing character:|Overfull \\[hv]box|undefined references", log)
    for stem in EXPECTED:
        folder = root / stem
        (folder / "pages").mkdir(exist_ok=False)
        checked(["pdftoppm", "-r", "100", "-png", folder / "lecture.pdf", folder / "pages/page"])
    (boundary / "pages").mkdir()
    checked(["pdftoppm", "-r", "90", "-png", boundary / "main.pdf", boundary / "pages/page"])
    return {"reordered_sections_and_references": True, "pagination_compiled_without_overflow": True}


def main():
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "output/n1").absolute()
    if root.exists():
        raise RuntimeError("验收输出已存在，请指定新的根目录。")
    root.mkdir(parents=True)
    quarto = find_quarto()
    results = {}
    for stem, expected in EXPECTED.items():
        source = ROOT / "examples" / (stem + ".md")
        folder = root / stem
        report = export_document(source, folder, quarto)
        assert report["status"] == "partial" and not report["diagnostics"], report
        doc = read_document(source, quarto)
        actual = labels_in_aux(folder / "_build/main.aux")
        assert all(actual.get(k) == v for k, v in expected.items()), actual
        details = content_check(doc, folder)
        relocated = recompile(folder / "lecture-source", root / "relocated" / stem)
        assert all(relocated.get(k) == v for k, v in expected.items())
        details.update(numbering=True, portable_recompile=True, page_review=False)
        results[stem] = details
        print(stem, details, flush=True)
    # 单项变体均在副本中；公式插入验证重排后引用随计数器更新。
    variants = root / "variants"
    variants.mkdir()
    source = (ROOT / "examples/01-mean.md").read_text(encoding="utf-8")
    (variants / "assets").mkdir()
    shutil.copyfile(ROOT / "examples/assets/mean-flow.png", variants / "assets/mean-flow.png")
    changed = source.replace("$$\n", "$$\ny=0.\n$$ {#eq-before}\n\n$$\n", 1)
    (variants / "insert.md").write_text(changed, encoding="utf-8")
    inserted = export_document(variants / "insert.md", variants / "insert-output", quarto)
    assert inserted["status"] == "partial", inserted
    assert labels_in_aux(variants / "insert-output/_build/main.aux")["eq-mean"] == "2"
    # 超宽公式必须给出明确失败状态及位置，而不是只凭 PDF 生成就成功。
    oversized = source + "\n$$\n" + "+".join(["x"] * 160) + "\n$$ {#eq-wide}\n"
    (variants / "wide.md").write_text(oversized, encoding="utf-8")
    wide = export_document(variants / "wide.md", variants / "wide-output", quarto)
    assert wide["status"] == "failed" and any(
        x["code"] == "LAYOUT_OVERFLOW" for x in wide["diagnostics"]
    ), wide
    # 代码中的 TeX 结束记号与不存在的文件名只能显示为字面量。
    literal = (
        '---\ntitle: "字面代码边界"\nauthor: "示例"\n---\n'
        '# 代码 {#sec-literal}\n\n```python\nraise RuntimeError("must-not-run")\n'
        "\\end{Verbatim}\n\\input{this-file-must-not-be-read}\n```\n"
    )
    (variants / "literal.md").write_text(literal, encoding="utf-8")
    code = export_document(variants / "literal.md", variants / "literal-output", quarto)
    assert code["status"] == "partial", code
    text = checked(["pdftotext", variants / "literal-output/lecture.pdf", "-"])
    assert "this-file-must-not-be-read" in text and "must-not-run" in text
    additional = extra_checks(root)
    write_json(
        root / "validation.json",
        {
            "samples": results,
            "variants": {
                "inserted_equation_renumbers": True,
                "overflow_reported": True,
                "code_is_literal": True,
                **additional,
            },
            "style_approved": False,
        },
    )


if __name__ == "__main__":
    main()
