"""PDF 字形核对：已知 TeX 引号映射不应误报漏文，文字差异仍须检出。"""

import importlib
import re
import shutil
import subprocess

import pytest

from note2lecture.tools import ROOT


@pytest.fixture
def compact(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    return importlib.import_module("verify_markdown").compact


@pytest.mark.parametrize("source,pdf", [
    ("Reader's observation", "Reader’s observation"),
    ("说明``quoted''文字", "说明“quoted”文字"),
    ("结束标点)``", "结束标点)“"),
])
def test_tex_quote_glyphs_are_equivalent(compact, source, pdf):
    assert compact(source) == compact(pdf)


@pytest.mark.parametrize("source,pdf", [
    ("存在唯一解", "不存在唯一解"),
    ("尚需连续条件", "条件已被删除"),
    ("`literal`", "literal"),
    ("'word'", "word"),
])
def test_missing_or_changed_content_still_fails(compact, source, pdf):
    assert compact(source) != compact(pdf)


def test_relocated_toc_page_numbers_converge(tmp_path, monkeypatch):
    if not shutil.which("xelatex") or not shutil.which("pdftotext"):
        pytest.skip("需要现有 XeLaTeX 与 pdftotext；不自动安装。")
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    recompile = importlib.import_module("verify_n1").recompile
    package = tmp_path / "package"
    package.mkdir()
    text = (r"\documentclass{article}\usepackage[a4paper,textheight=13cm]{geometry}"
            r"\usepackage{hyperref}\begin{document}\tableofcontents\clearpage")
    for i in range(1, 41):
        text += rf"\section{{Section{i:02d}}}\label{{sec-{i:02d}}}Original paragraph."
    text += r"\end{document}"
    (package / "main.tex").write_text(text, encoding="utf-8")
    target = tmp_path / "relocated"
    labels = recompile(package, target)
    result = subprocess.run(
        ["pdftotext", "-layout", str(target / "main.pdf"), "-"],
        capture_output=True, check=True, encoding="utf-8", errors="replace", timeout=30,
    )
    # 目录从空白长成多页后，首节移到后面；目录不能仍显示第一轮的 2。
    first_toc_page = result.stdout.split("\f")[0]
    shown = re.search(r"Section01[^\n]*\s(\d+)\s*$", first_toc_page, re.M)
    actual = re.search(
        r"\\newlabel\{sec-01\}\{\{1\}\{(\d+)\}",
        (target / "main.aux").read_text(encoding="utf-8"),
    )
    assert labels["sec-01"] == "1"
    assert actual and int(actual[1]) > 2
    assert shown and shown[1] == actual[1]
