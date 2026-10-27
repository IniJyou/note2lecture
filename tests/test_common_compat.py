"""宽公式、六级标题和源列表编号的综合回归；全部使用原创内容。"""

import json
import re

import pytest
from test_portrait_math import compile_tex

from note2lecture.diagnostics import NoteError
from note2lecture.document import nodes, read_document
from note2lecture.exporter import prepare_ast, restore_display_math
from note2lecture.tools import ROOT, pandoc_command, run


def read(tmp_path, quarto, body, profile="markdown", numbering="auto"):
    path = tmp_path / "original.md"
    path.write_text("# 原创综合回归\n\n" + body + "\n", encoding="utf-8")
    return read_document(path, quarto, profile, list_numbering=numbering)


def latex(doc, tmp_path, quarto):
    result = run([
        *pandoc_command(quarto), "-f", "json", "-t", "latex", "--wrap=none",
        "--lua-filter=" + str(ROOT / "templates/lecture/markdown.lua"),
    ], text=json.dumps(prepare_ast(doc, tmp_path)))
    assert result.returncode == 0, result.stderr
    return restore_display_math(result.stdout, doc)


@pytest.mark.parametrize("profile", ["markdown", "obsidian"])
def test_six_heading_levels_keep_text_links_and_math(tmp_path, quarto, profile):
    body = "\n\n".join("#" * n + f" 第{n}层 $x_{n}$ {{#sec-level-{n}}}" for n in range(1, 7))
    doc = read(tmp_path, quarto, body + "\n\n[返回深层](#sec-level-6)", profile)
    assert [n["c"][0] for n in nodes(doc.ast["blocks"]) if n["t"] == "Header"] == list(range(1, 7))
    tex = latex(doc, tmp_path, quarto)
    for n in range(4, 7):
        assert f"\\NtwoLDeepHeading{{{n}}}{{sec-level-{n}}}" in tex
        assert f"\\label{{sec-level-{n}}}" in tex
    assert all(x["text"] in tex for x in doc.math)
    assert "NtwoLHeadingBookmark" not in tex
    assert len(doc.internal_links) == 1


def test_deep_heading_native_bookmarks_have_levels_and_destinations(tmp_path, quarto):
    doc = read(tmp_path, quarto, "\n\n".join("#" * n + f" Level{n}" for n in range(1, 7)))
    tex = latex(doc, tmp_path, quarto)
    result, log = compile_tex(
        tmp_path, r"\usepackage{hyperref}\begin{document}" + tex + r"\end{document}",
    )
    assert result.returncode == 0, log[-2500:]
    outlines = (tmp_path / "test.out").read_text(encoding="utf-8")
    assert all(f"\\BOOKMARK [{n}]" in outlines for n in (4, 5, 6))
    assert all(f"n2l-deep-sec-n2l-{n}" in outlines for n in (4, 5, 6))
    aux = (tmp_path / "test.aux").read_text(encoding="utf-8")
    assert all("}{Level" + str(n) + "}{" in aux for n in (4, 5, 6))
    assert not re.search(r"Missing character|Overfull|Undefined control sequence", log)


@pytest.mark.parametrize("marker,next_marker,style", [
    ("a.", "b.", "LowerAlpha"), ("A)", "B)", "UpperAlpha"),
    ("(i)", "(ii)", "LowerRoman"), ("I.", "II.", "UpperRoman"),
    ("3.", "4.", "Decimal"), ("1.", "1.", "Decimal"),
])
def test_list_styles_and_automatic_numbers_survive(tmp_path, quarto, marker, next_marker, style):
    doc = read(tmp_path, quarto, marker + "  甲\n" + next_marker + "  乙")
    ordered = next(n for n in nodes(doc.ast["blocks"]) if n["t"] == "OrderedList")
    assert ordered["c"][0][1]["t"] == style
    assert [x["marker"] for x in doc.list_numbers[id(ordered)]] == [marker, next_marker]
    assert "NtwoLList" not in latex(doc, tmp_path, quarto)


@pytest.mark.parametrize("body", ["1. 甲\n3. 乙\n7. 丙", "01. 甲\n02. 乙", "a. 甲\nc. 乙"])
def test_nonautomatic_source_numbers_require_explicit_choice(tmp_path, quarto, body):
    with pytest.raises(NoteError) as error:
        read(tmp_path, quarto, body)
    assert error.value.diagnostic.code == "LIST_NUMBERING"
    assert error.value.diagnostic.line == 3
    assert "--list-numbering preserve" in error.value.diagnostic.hint


@pytest.mark.parametrize("profile", ["markdown", "obsidian"])
def test_literal_numbers_and_nested_formulas_survive_backend(tmp_path, quarto, profile):
    body = (
        "1. 第一题\n\n   $$u=\n   v+w$$\n\n   a. 子题甲\n   c. 子题丙\n\n"
        "3. 第三题\n\n   续段 $z$。\n\n7. 第七题"
    )
    doc = read(tmp_path, quarto, body, profile, "preserve")
    tex = latex(doc, tmp_path, quarto)
    assert all("\\item[" + marker + "]" in tex for marker in ("1.", "3.", "7.", "a.", "c."))
    assert [x["text"] for x in doc.math] == ["u=\nv+w", "z"]
    assert all(x["text"] in tex for x in doc.math)
    assert "NtwoLListLabel" not in tex
    assert len(doc.warnings) == 2
    assert doc.path.read_text(encoding="utf-8") == "# 原创综合回归\n\n" + body + "\n"


def test_list_only_math_code_and_empty_items_keep_numbers(tmp_path, quarto):
    doc = read(tmp_path, quarto, "1. $$x=\n   y$$\n2. `literal`\n3.\n4. 最后项")
    assert [x["text"] for x in doc.math] == ["x=\ny"]
    assert len(next(n for n in nodes(doc.ast["blocks"]) if n["t"] == "OrderedList")["c"][1]) == 4


@pytest.mark.parametrize("body,kind", [
    ("1. ```python\n   raise RuntimeError('never run')\n   ```", "CodeBlock"),
    ("# 正文\n\n1. ## 条目子标题\n\n   原创段落。", "Header"),
    ("1. - 原创子条目\n   - 后续子条目", "BulletList"),
    ("1. > 原创引用", "BlockQuote"),
])
def test_source_number_markers_do_not_change_first_block_type(tmp_path, quarto, body, kind):
    doc = read(tmp_path, quarto, body)
    ordered = next(n for n in nodes(doc.ast["blocks"]) if n["t"] == "OrderedList")
    assert any(n["t"] == kind for n in nodes(ordered["c"][1][0]))
    if kind == "CodeBlock":
        assert doc.code == ["raise RuntimeError('never run')"]


def test_sum_breaks_preserve_unary_signs_groups_and_command_arguments(tmp_path):
    original = r"p=-a+b-(c+d)+\frac{u+v}{w-z}+\mathbf{v+w}"
    expected = (r"p=-a\NtwoLWrapBreak+b\NtwoLWrapBreak-(c+d)"
                r"\NtwoLWrapBreak+\frac{u+v}{w-z}\NtwoLWrapBreak+\mathbf{v+w}")
    body = (r"\begin{document}\ExplSyntaxOn\bool_set_true:N\l__ntwol_sums_bool"
            r"\__ntwol_plan:n{" + original + "}"
            r"\tl_set:Nn\l_tmpa_tl{" + expected + "}"
            r"\tl_if_eq:NNF\l_tmpa_tl\l__ntwol_wrapped_tl{\errmessage{BADSUMBOUNDARY}}"
            r"\bool_if:NF\l__ntwol_safe_bool{\errmessage{UNSAFE}}"
            r"\ExplSyntaxOff\end{document}")
    result, log = compile_tex(tmp_path, body)
    assert result.returncode == 0, log[-2500:]


def test_wide_sum_wraps_at_list_width_before_scaling(tmp_path):
    formula = "R=" + "+".join([r"\frac{x+x^2+x^3}{1+x^2}"] * 8)
    body = (r"\begin{document}\begin{enumerate}\item Original topic."
            r"\NtwoLMathDisplay{" + "c" * 64 + "}{" + formula + r"}\end{enumerate}\end{document}")
    result, log = compile_tex(tmp_path, body)
    assert result.returncode == 0, log[-2500:]
    assert "N2LWRAPPED:" in log
    width, available = map(float, re.search(r"N2LWRAPDIMS:([\d.]+)pt:([\d.]+)pt", log).groups())
    assert width <= available < 455.3
    assert not re.search(r"Missing character|Overfull", log)


def test_slight_overflow_wraps_before_shrinking_and_atomic_fallback_still_works(tmp_path):
    formula = r"p=\frac{x+x^2+x^3}{1+x^2}=\frac{y+y^2+y^3}{1+y^2}"
    atomic = r"\begin{matrix}a&b&c&d\end{matrix}"
    body = (r"\begin{document}\sbox{\NtwoLMathBox}{$\displaystyle " + formula + " $}"
            r"\linewidth=.96\wd\NtwoLMathBox"
            r"\NtwoLMathDisplay{" + "d" * 64 + "}{" + formula + "}"
            r"\sbox{\NtwoLMathBox}{$\displaystyle " + atomic + "$}"
            r"\linewidth=.96\wd\NtwoLMathBox"
            r"\NtwoLMathDisplay{" + "e" * 64 + "}{" + atomic + r"}\end{document}")
    result, log = compile_tex(tmp_path, body)
    assert result.returncode == 0, log[-2500:]
    assert "N2LWRAPPED:" + "d" * 64 in log
    assert "N2LWRAPPED:" + "e" * 64 not in log
    assert not re.search(r"Missing character|Overfull", log)


@pytest.mark.parametrize("formula", [
    r"p=\sqrt[n+m]{x}=q", r"p=\sum x+y", r"p=\stackrel{!}{x}-a+b",
])
def test_ambiguous_optional_arguments_and_operator_scopes_are_not_guessed(tmp_path, formula):
    body = (r"\begin{document}\ExplSyntaxOn\bool_set_true:N\l__ntwol_sums_bool"
            r"\__ntwol_plan:n{" + formula + "}"
            r"\bool_if:NT\l__ntwol_safe_bool{\errmessage{UNSAFESCOPE}}"
            r"\ExplSyntaxOff\end{document}")
    result, log = compile_tex(tmp_path, body)
    assert result.returncode == 0, log[-2500:]


@pytest.mark.parametrize("mode,exit_code", [("auto", 2), ("preserve", 0)])
def test_cli_checks_source_numbering_choice(tmp_path, quarto, capsys, mode, exit_code):
    from note2lecture.cli import main

    path = tmp_path / "original.md"
    path.write_text("# 原创\n\n1. 第一题\n3. 第三题", encoding="utf-8")
    assert main(["check", str(path), "--profile", "markdown", "--quarto", str(quarto),
                 "--list-numbering", mode]) == exit_code
    report = json.loads(capsys.readouterr().out)
    assert report["diagnostics"][0]["code"] == (
        "LIST_NUMBERING" if mode == "auto" else "LIST_NUMBERING_PRESERVED"
    )


def test_batch_forwards_explicit_source_numbering(tmp_path, monkeypatch):
    from note2lecture import batch

    path = tmp_path / "original.md"
    path.write_text("# 原创\n\n1. 第一题\n3. 第三题", encoding="utf-8")
    options = []

    def export(*args, **kwargs):
        options.append(kwargs)
        return {"status": "partial", "checks": {
                    "structure": True, "compile": True, "content_review": False,
                    "page_review": False, "style_approved": False,
                },
                "diagnostics": []}

    monkeypatch.setattr(batch, "export_document", export)
    report = batch.export_batch([path], tmp_path / "batch", profile="markdown",
                                list_numbering="preserve")
    assert options == [{"list_numbering": "preserve"}]
    assert report["summary"]["converted"] == 1


def test_continuous_native_alpha_and_roman_lists_compile(tmp_path, quarto):
    doc = read(tmp_path, quarto, "a.  甲\nb.  乙\n\nI.  丙\nII.  丁\n\n(3) 戊\n(4) 己")
    tex = latex(doc, tmp_path, quarto)
    result, log = compile_tex(
        tmp_path, r"\providecommand{\tightlist}{\setlength{\itemsep}{0pt}}\begin{document}"
        + tex + r"\end{document}",
    )
    assert result.returncode == 0, log[-2500:]
    assert not re.search(r"Missing character|Overfull|Undefined control sequence", log)
