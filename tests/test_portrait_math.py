"""原创公式的原生 TeX 检查：分行边界、数学参数保护与明确拒绝。"""

import json
import re
import shutil
import subprocess
import unicodedata

import pytest

from note2lecture.document import nodes, read_document
from note2lecture.exporter import prepare_ast, restore_display_math
from note2lecture.tools import ROOT, pandoc, pandoc_command, run


def compile_tex(tmp_path, body):
    if not shutil.which("xelatex"):
        pytest.skip("需要现有 XeLaTeX；测试不自动安装。")
    preamble = r"""\documentclass{ctexart}
\usepackage{unicode-math,graphicx,etoolbox,needspace,geometry,fvextra}
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
        (r"p\lt q\gt r", r"p\lt q\NtwoLWrapBreak\gt r"),
        (r"p=\overset{!}=q=r", r"p=\overset{!}=q\NtwoLWrapBreak=r"),
        (r"p=\mathbf=q=r", r"p=\mathbf=q\NtwoLWrapBreak=r"),
        (r"p=q\not=r=s", r"p=q\not=r\NtwoLWrapBreak=s"),
        (r"p=q\stackrel{!}=r=s", r"p=q\stackrel{!}=r\NtwoLWrapBreak=s"),
        (r"p=\mathrel=q=r", r"p=\mathrel=q\NtwoLWrapBreak=r"),
        (r"p=\lfloor q=r\rfloor=s", r"p=\lfloor q=r\rfloor\NtwoLWrapBreak=s"),
        (r"p=\lceil q=r\rceil=s", r"p=\lceil q=r\rceil\NtwoLWrapBreak=s"),
        (r"p=\begin{bmatrix}q=r&s\\t&u\end{bmatrix}=v",
         r"p=\begin{bmatrix}q=r&s\\t&u\end{bmatrix}\NtwoLWrapBreak=v"),
        (r"p=\begin{pmatrix}\begin{smallmatrix}q&r\end{smallmatrix}&s\end{pmatrix}=t",
         r"p=\begin{pmatrix}\begin{smallmatrix}q&r\end{smallmatrix}&s\end{pmatrix}"
         r"\NtwoLWrapBreak=t"),
        (r"p=\left(\begin{array}{lc|r}q=r&s&t\\u&v&w\end{array}\right)=z",
         r"p=\left(\begin{array}{lc|r}q=r&s&t\\u&v&w\end{array}\right)\NtwoLWrapBreak=z"),
    ]
    body = [r"\begin{document}\ExplSyntaxOn\tl_new:N\l_test_expected_tl"]
    for original, expected in pairs:
        body.extend([
            r"\__ntwol_plan:n{" + original + "}",
            r"\bool_if:NF\l__ntwol_safe_bool{\errmessage{UNSAFE}}",
            r"\tl_set:Nn\l_test_expected_tl{" + expected + "}",
            r"\tl_if_eq:NNF\l_test_expected_tl\l__ntwol_wrapped_tl{\errmessage{BADBOUNDARY}}",
        ])
    for original in (
        r"p=|q=r|=s", r"p=\Vert q=r\Vert=s", r"\begin{aligned}p&=q\end{aligned}=s",
        r"p=\begin{bmatrix}q&r\end{pmatrix}=s", r"p=\begin{bmatrix}q&r=s",
    ):
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


def test_common_math_aliases_compile_without_rewriting(tmp_path):
    formula = (r"a\lt b\gt 0,\quad A^\dagger\xrightarrow{f}B,\quad"
               r"\arg z,\bigcup_i U_i,\checkmark")
    body = r"\begin{document}\[" + formula + r"\]\end{document}"
    result, log = compile_tex(tmp_path, body)
    assert result.returncode == 0, log[-3000:]
    assert not re.search(r"Missing character|Overfull|Undefined control sequence", log)


def test_matrix_chain_wraps_only_between_whole_matrices(tmp_path):
    matrix = r"\begin{bmatrix}u_{k-1}&v_{k-1}\\w_{k-1}&z_{k-1}\end{bmatrix}"
    formula = "F=" + matrix + matrix + "=" + matrix + "=" + matrix + "=G"
    body = (r"\begin{document}\begin{minipage}{100mm}\NtwoLMathDisplay{"
            + "c" * 64 + "}{" + formula + r"}\end{minipage}\end{document}")
    result, log = compile_tex(tmp_path, body)
    assert result.returncode == 0, log[-3000:]
    assert "N2LWRAPPED:" in log
    assert not re.search(r"Missing character|Overfull", log)


def test_code_star_and_third_circle_use_existing_glyphs(tmp_path):
    code = 'marker = "★"  # 原创代码，只排版\n'
    (tmp_path / "literal.txt").write_text(code, encoding="utf-8")
    body = (r"\begin{document}\NtwoLTextSymbol{③}\texttt{★}"
            r"\VerbatimInput{literal.txt}\end{document}")
    result, log = compile_tex(tmp_path, body)
    assert result.returncode == 0, log[-3000:]
    assert not re.search(r"Missing character|Overfull", log)
    assert (tmp_path / "literal.txt").read_text(encoding="utf-8") == code


def test_augmented_array_chain_keeps_rules_while_wrapping(tmp_path):
    matrix = (r"\left(\begin{array}{cc|c}a_{k-1}&b_{k-1}&c_{k-1}"
              r"\\d_{k-1}&e_{k-1}&f_{k-1}\end{array}\right)")
    formula = "F=" + "=".join([matrix] * 3) + "=G"
    body = (r"\begin{document}\begin{minipage}{80mm}\NtwoLMathDisplay{"
            + "f" * 64 + "}{" + formula + r"}\end{minipage}\end{document}")
    result, log = compile_tex(tmp_path, body)
    assert result.returncode == 0, log[-3000:]
    assert "N2LWRAPPED:" in log
    assert not re.search(r"Missing character|Overfull", log)


@pytest.mark.parametrize("inline_tail", [False, True])
def test_list_title_colon_and_short_math_tail_stay_on_same_page(tmp_path, quarto, inline_tail):
    if not shutil.which("pdftotext"):
        pytest.skip("需要已有 pdftotext；不自动安装。")
    matrix = r"\begin{bmatrix}1&2\\3&4\\5&6\\7&8\end{bmatrix}"
    first = r"\NtwoLMathDisplay{" + "d" * 64 + "}{P=" + matrix + "}"
    last = r"\NtwoLMathDisplay{" + "e" * 64 + r"}{Q=\begin{bmatrix}1&2\\3&4\\5&6\end{bmatrix}}"
    ending = ("Before formula. `" + last + "`{=latex} Original conclusion.\n" if inline_tail
              else last + "\n\n```{=latex}\n% N2L_SOURCE 20 4\n```\n\nOriginal conclusion.\n")
    source = (r"\vspace*{.87\textheight}" + "\n\n- **Original topic**:\n\n  " + first
              + "\n\n" + r"\clearpage\vspace*{.875\textheight}\par\penalty0" + "\n\n" + ending)
    filtered = run([
        *pandoc_command(quarto), "--from", "markdown-smart-latex_macros", "--to", "latex",
        "--lua-filter", ROOT / "templates/lecture/markdown.lua",
    ], text=source)
    assert filtered.returncode == 0, filtered.stderr
    result, log = compile_tex(tmp_path, r"\begin{document}" + filtered.stdout + r"\end{document}")
    assert result.returncode == 0, log[-3000:]
    assert not re.search(r"Missing character|Overfull", log)
    text = subprocess.run(
        ["pdftotext", "-layout", str(tmp_path / "test.pdf"), "-"],
        capture_output=True, check=True, encoding="utf-8", errors="replace", timeout=30,
    ).stdout
    pages = text.split("\f")
    def page_of(needle):
        return next(i for i, page in enumerate(pages)
                    if needle in re.sub(r"\s+", "", unicodedata.normalize("NFKC", page)))
    assert page_of("Originaltopic:") == page_of("P=")
    assert page_of("Originalconclusion.") == page_of("Q=")


@pytest.mark.parametrize("formula", [
    "P(t)=" + "".join(f"t^{{{i}}}" for i in range(1, 70)),
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
