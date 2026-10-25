"""原创公式的原生 TeX 检查：分行边界、数学参数保护与明确拒绝。"""

import json
import re
import shutil
import subprocess

import pytest

from note2lecture.document import nodes, read_document
from note2lecture.exporter import prepare_ast, restore_display_math
from note2lecture.tools import ROOT, pandoc


def compile_tex(tmp_path, body):
    if not shutil.which("xelatex"):
        pytest.skip("需要现有 XeLaTeX；测试不自动安装。")
    preamble = r"""\documentclass{ctexart}
\usepackage{unicode-math,graphicx,etoolbox,needspace,geometry}
\setmainfont{Latin Modern Roman}
\setmathfont{Latin Modern Math}
\geometry{a4paper,left=25mm,right=25mm}
"""
    for name in ("markdown.tex", "math-wrap.tex"):
        preamble += (ROOT / "templates/lecture" / name).read_text(encoding="utf-8") + "\n"
    (tmp_path / "test.tex").write_text(preamble + body, encoding="utf-8")
    result = subprocess.run(
        ["xelatex", "-no-shell-escape", "-halt-on-error", "-interaction=nonstopmode", "test.tex"],
        cwd=tmp_path, capture_output=True, encoding="utf-8", errors="replace", timeout=30,
    )
    return result, (tmp_path / "test.log").read_text(encoding="utf-8", errors="replace")


def test_wrap_boundaries_preserve_groups_arguments_and_evaluation_bar(tmp_path):
    pairs = [
        (r"p=q=r", r"p=q\NtwoLWrapBreak=r"),
        (r"p=\left(q=r\right)=s", r"p=\left(q=r\right)\NtwoLWrapBreak=s"),
        (r"p=\{q=r\}=s", r"p=\{q=r\}\NtwoLWrapBreak=s"),
        ("p=⟨q=r⟩=s", r"p=⟨q=r⟩\NtwoLWrapBreak=s"),
        (r"p=\frac{q=r}{s}=t", r"p=\frac{q=r}{s}\NtwoLWrapBreak=t"),
        (r"p=q\bigg|_0^1=r", r"p=q\bigg|_0^1\NtwoLWrapBreak=r"),
        (r"p=q\Longleftrightarrow r=s", r"p=q\NtwoLWrapBreak\Longleftrightarrow r=s"),
        (r"p\leq q\leq r", r"p\leq q\NtwoLWrapBreak\leq r"),
        (r"p=\overset{!}=q=r", r"p=\overset{!}=q\NtwoLWrapBreak=r"),
        (r"p=\mathbf=q=r", r"p=\mathbf=q\NtwoLWrapBreak=r"),
    ]
    body = [r"\begin{document}\ExplSyntaxOn\tl_new:N\l_test_expected_tl"]
    for original, expected in pairs:
        body.extend([
            r"\__ntwol_plan:n{" + original + "}",
            r"\bool_if:NF\l__ntwol_safe_bool{\errmessage{UNSAFE}}",
            r"\tl_set:Nn\l_test_expected_tl{" + expected + "}",
            r"\tl_if_eq:NNF\l_test_expected_tl\l__ntwol_wrapped_tl{\errmessage{BADBOUNDARY}}",
        ])
    for original in (r"p=|q=r|=s", r"p=\Vert q=r\Vert=s", r"\begin{aligned}p&=q\end{aligned}=s"):
        body.extend([
            r"\__ntwol_plan:n{" + original + "}",
            r"\bool_if:NT\l__ntwol_safe_bool{\errmessage{AMBIGUOUS}}",
        ])
    body.extend([
        r"\bool_set_true:N\l__ntwol_force_first_bool\__ntwol_plan:n{p=q}",
        r"\tl_set:Nn\l_test_expected_tl{p\NtwoLWrapBreak=q}",
        r"\tl_if_eq:NNF\l_test_expected_tl\l__ntwol_wrapped_tl{\errmessage{FIRSTRELATION}}",
    ])
    body.append(r"\ExplSyntaxOff\end{document}")
    result, log = compile_tex(tmp_path, "\n".join(body))
    assert result.returncode == 0, log[-3000:]
    assert "No pages of output" in log


def test_wide_chain_fits_portrait_and_symbols_survive(tmp_path):
    term = r"\frac{t+t^2+t^3+t^4}{1+t^2}+\frac{t^5+t^6+t^7}{1+t^4}"
    formula = "R(t)=" + "=".join([term] * 4)
    body = (r"\begin{document}\NtwoLTextSymbol{①}\textbf{\NtwoLTextSymbol{②}}"
            r"\NtwoLTextSymbol{∎}\NtwoLMathDisplay{" + "a" * 64 + "}{" + formula + "}"
            r"\end{document}")
    result, log = compile_tex(tmp_path, body)
    assert result.returncode == 0, log[-3000:]
    assert "N2LWRAPPED:" in log and "N2LWRAPROWS:4" in log
    assert not re.search(r"Missing character|Overfull", log)
    width, available = map(float, re.search(r"N2LWRAPDIMS:([\d.]+)pt:([\d.]+)pt", log).groups())
    assert width <= available * 1.12


@pytest.mark.parametrize("formula", [
    "P(t)=" + "+".join(f"t^{{{i}}}" for i in range(1, 70)),
    "P(t)=|" + "+".join(f"t^{{{i}}}" for i in range(1, 70)) + "|=Q(t)",
])
def test_unbreakable_or_ambiguous_wide_math_fails_without_landscape(tmp_path, formula):
    body = (r"\begin{document}\NtwoLMathDisplay{" + "b" * 64 + "}{" + formula + "}"
            r"\end{document}")
    result, log = compile_tex(tmp_path, body)
    assert result.returncode != 0
    assert "N2LWIDE:" + "b" * 64 in log
    assert "N2L_MATH_TOO_WIDE" in log


def test_text_symbols_keep_code_literal_and_heading_bookmark(tmp_path, quarto):
    text = "# 原创笔记\n\n## 提示①file_path\n\n**①甲②乙∎**，代码 `①②∎`，数学 $x$。\n"
    path = tmp_path / "note.md"
    path.write_text(text, encoding="utf-8")
    doc = read_document(path, quarto, "markdown")
    ast = prepare_ast(doc, tmp_path)
    assert [x["c"][1] for x in nodes(ast["blocks"]) if x["t"] == "Code"] == ["①②∎"]
    tex = restore_display_math(pandoc(quarto, json.dumps(ast), "json", "latex"), doc)
    assert r"\NtwoLTextSymbol{①}" in tex and r"\NtwoLTextSymbol{∎}" in tex
    assert r"}{提示①file\_path}}" in tex and "NtwoLHeadingBookmark" not in tex
    assert r"\allowbreak" not in tex
    assert path.read_text(encoding="utf-8") == text
