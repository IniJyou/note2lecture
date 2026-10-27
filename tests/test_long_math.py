"""长篇数学笔记的常见语法回归；全部使用原创临时正文。"""

import json

import pytest

from note2lecture.diagnostics import NoteError
from note2lecture.document import digest, nodes, read_document
from note2lecture.exporter import bookmark_text, prepare_ast, restore_display_math
from note2lecture.tools import pandoc


def read(tmp_path, quarto, body, profile="markdown"):
    path = tmp_path / "original.md"
    path.write_text("# 原创笔记\n\n" + body + "\n", encoding="utf-8")
    return read_document(path, quarto, profile)


@pytest.mark.parametrize("profile", ["markdown", "obsidian"])
@pytest.mark.parametrize("formula", [" x+y ", "x+\ny", "x+y\n", r"x + \text{\$}"])
def test_inline_spaces_and_soft_wraps_survive_backend(tmp_path, quarto, profile, formula):
    doc = read(tmp_path, quarto, "正文 $" + formula + "$2。", profile)
    assert [x["text"] for x in doc.math] == [formula]
    span = doc.inline_math[0]
    assert doc.source.text[span["start"] + 1 : span["end"] - 1] == formula
    ast = prepare_ast(doc, tmp_path)
    tex = pandoc(quarto, json.dumps(ast), "json", "latex")
    restored = restore_display_math(tex, doc)
    assert formula in restored and "NtwoLMathToken" not in restored


@pytest.mark.parametrize("formula", [" t ", r"\arctan t", r"\frac{p_1}{q_2}"])
def test_math_in_heading_and_after_html_anchor(tmp_path, quarto, formula):
    doc = read(tmp_path, quarto, '<a id="a"></a>\n\n## 边界 $' + formula + '$\n\n[跳转](#a)\n')
    assert doc.math[0]["text"] == formula
    ast = prepare_ast(doc, tmp_path)
    tex = pandoc(quarto, json.dumps(ast), "json", "latex")
    restored = restore_display_math(tex, doc)
    assert formula in restored
    assert "}{边界 " + bookmark_text(formula) + "}}" in restored
    assert "NtwoLHeadingBookmark" not in restored
    assert len(doc.internal_links) == 1


def test_code_that_describes_math_tokens_remains_literal(tmp_path, quarto):
    code = r"\NtwoLMathToken{" + digest(b"x") + "}"
    doc = read(tmp_path, quarto, "代码 `" + code + "`，正文 $x$。")
    tex = pandoc(quarto, json.dumps(prepare_ast(doc, tmp_path)), "json", "latex")
    restored = restore_display_math(tex, doc)
    assert r"NtwoLMathToken\{" + digest(b"x") + r"\}" in restored
    assert r"\(x\)" in restored


@pytest.mark.parametrize("body", ["$x\n\ny$", "$x\n## 下一节\ny$", "$x\n- 条目\ny$", "$   $"])
def test_inline_math_cannot_swallow_document_blocks(tmp_path, quarto, body):
    with pytest.raises(NoteError) as error:
        read(tmp_path, quarto, body)
    assert error.value.diagnostic.code == "STRUCTURE_INVALID"
    assert error.value.diagnostic.line == 3


def test_inline_math_still_validates_commands_and_original_position(tmp_path, quarto):
    with pytest.raises(NoteError) as error:
        read(tmp_path, quarto, "正常段落。\n\n$ \\input{private} $")
    assert error.value.diagnostic.code == "UNSUPPORTED_SYNTAX"
    assert error.value.diagnostic.line == 5


def test_code_is_literal_and_source_is_read_only(tmp_path, quarto):
    body = '`$ unclosed`\n\n```text\n$ x\n\\tag{1}\n```\n\n正文 $ y $'
    doc = read(tmp_path, quarto, body)
    assert doc.math[0]["text"] == " y "
    assert doc.code == ["$ x\n\\tag{1}"]
    assert doc.path.read_text(encoding="utf-8") == "# 原创笔记\n\n" + body + "\n"


@pytest.mark.parametrize(
    "marker,style", [("1.", "Period"), ("1)", "OneParen"), ("(1)", "TwoParens")]
)
def test_decimal_list_delimiter_is_preserved(tmp_path, quarto, marker, style):
    doc = read(tmp_path, quarto, marker + " 第一项\n" + marker.replace("1", "2") + " 第二项")
    node = next(n for n in nodes(doc.ast["blocks"]) if n["t"] == "OrderedList")
    assert node["c"][0][2]["t"] == style


def test_hard_break_and_common_math_commands(tmp_path, quarto):
    text = (
        "首行。  \n次行。\n\n$$\n"
        r"\arcsin x+\arccos x+\arctan x+\cot x+\iiint_\Omega f+\oiint_\Sigma g"
        r"+\bigl(x\bigr)+\Bigl(y\Bigr)+\boxed{z}+\square"
        r"\uparrow\downarrow\therefore\Longleftrightarrow t"
        "\n$$"
    )
    doc = read(tmp_path, quarto, text)
    assert len(doc.math) == 1
    assert any(n["t"] == "LineBreak" for n in nodes(doc.ast["blocks"]))


def test_common_math_aliases_survive_backend_exactly(tmp_path, quarto):
    formula = r"a\lt b\gt 0,\quad A^\dagger\xrightarrow{f}B,\quad\arg z,\bigcup_i U_i,\checkmark"
    doc = read(tmp_path, quarto, "$$\n" + formula + "\n$$")
    tex = restore_display_math(
        pandoc(quarto, json.dumps(prepare_ast(doc, tmp_path)), "json", "latex"), doc
    )
    assert doc.math[0]["text"] == "\n" + formula + "\n"
    assert formula in tex


@pytest.mark.parametrize("profile", ["markdown", "obsidian"])
def test_compact_displays_keep_whitespace_labels_lists_and_literal_code(tmp_path, quarto, profile):
    formula = r"  u_2 = u_1 + \text{\$}  "
    body = (
        "$$" + formula + "$$ {#eq-original}\n\n- 原创条目\n"
        "  $$v = \\frac{w}{2}.$$\n"
        + "  续文 $z$。\n\n代码 `$$not math$$`。\n\n```text\n$$unclosed\n```"
    )
    doc = read(tmp_path, quarto, body, profile)
    assert [x["kind"] for x in doc.math] == ["DisplayMath", "DisplayMath", "InlineMath"]
    assert [x["text"] for x in doc.math] == [formula, r"v = \frac{w}{2}.", "z"]
    assert "eq-original" in doc.labels
    assert doc.code == ["$$unclosed"]
    tex = restore_display_math(
        pandoc(quarto, json.dumps(prepare_ast(doc, tmp_path)), "json", "latex"), doc
    )
    assert all(x["text"] in tex for x in doc.math)
    assert doc.path.read_text(encoding="utf-8") == "# 原创笔记\n\n" + body + "\n"


@pytest.mark.parametrize("body,code,column", [
    ("  $$$$", "STRUCTURE_INVALID", 3),
    ("$$   $$", "STRUCTURE_INVALID", 1),
    ("  $$x+1", "STRUCTURE_INVALID", 3),
    ("$$x$$ $$y", "STRUCTURE_INVALID", 7),
    ("正文 $$x 续文", "STRUCTURE_INVALID", 4),
])
def test_compact_display_errors_are_not_reported_as_empty_inline(
    tmp_path, quarto, body, code, column,
):
    with pytest.raises(NoteError) as error:
        read(tmp_path, quarto, body)
    diagnostic = error.value.diagnostic
    assert diagnostic.code == code
    assert (diagnostic.line, diagnostic.column, diagnostic.block) == (3, column, "math")
    assert "行内公式为空" not in diagnostic.message


def test_adjacent_inline_formulas_are_not_mistaken_for_display_delimiters(tmp_path, quarto):
    doc = read(tmp_path, quarto, "相邻公式 $x$$y$ 保持两个数学节点。")
    assert [x["text"] for x in doc.math] == ["x", "y"]
    assert all(x["kind"] == "InlineMath" for x in doc.math)


@pytest.mark.parametrize("profile", ["markdown", "obsidian"])
@pytest.mark.parametrize("opening,closing", [
    ("$$", "$$"), ("$$\n", "$$"), ("$$", "\n$$"), ("$$\n", "\n$$"),
])
@pytest.mark.parametrize("in_list", [False, True])
def test_multiline_dollars_keep_all_fence_forms_and_formula_bytes(
    tmp_path, quarto, profile, opening, closing, in_list,
):
    formula = "  A = \\begin{pmatrix}\n1 & 2 \\\\\n3 & 4\n\\end{pmatrix}  "
    body = opening + formula + closing + " {#eq-original}"
    if in_list:
        body = "- 原创矩阵\n\n  " + body.replace("\n", "\n  ")
    doc = read(tmp_path, quarto, body, profile)
    expected = opening[2:] + formula + closing[:-2]
    assert [(x["kind"], x["text"]) for x in doc.math] == [("DisplayMath", expected)]
    assert "eq-original" in doc.labels
    tex = restore_display_math(
        pandoc(quarto, json.dumps(prepare_ast(doc, tmp_path)), "json", "latex"), doc
    )
    assert expected in tex
    assert doc.path.read_text(encoding="utf-8") == "# 原创笔记\n\n" + body + "\n"


@pytest.mark.parametrize("body", [
    "$$x=\n## 后一节\ny$$", "$$x=\n```text\ny$$",
    "$$x=\ny$$ $$z", "$$\nx$$ $$$$", "$$\n$$",
])
def test_multiline_dollars_reject_empty_or_swallowed_document_blocks(tmp_path, quarto, body):
    with pytest.raises(NoteError) as error:
        read(tmp_path, quarto, body)
    assert error.value.diagnostic.code == "STRUCTURE_INVALID"
    assert error.value.diagnostic.block == "math"


def test_multiline_dollars_leave_escaped_dollars_and_code_literal(tmp_path, quarto):
    formula = "x + \\text{\\$\\$}\n+ y"
    doc = read(tmp_path, quarto, "```text\n$$not\nmath$$\n```\n\n$$" + formula + "$$")
    assert doc.code == ["$$not\nmath$$"]
    assert [x["text"] for x in doc.math] == [formula]


@pytest.mark.parametrize("profile", ["markdown", "obsidian"])
@pytest.mark.parametrize("prefix,continuation", [("> ", "> "), ("- ", "  "), ("1. ", "   ")])
@pytest.mark.parametrize("formula", ["u=v", "u=\nv+w"])
def test_dollar_fences_in_existing_quote_and_list_containers(
    tmp_path, quarto, profile, prefix, continuation, formula,
):
    body = prefix + "$$" + formula.replace("\n", "\n" + continuation) + "$$"
    if prefix == "> ":
        body = "> 原创题头\n" + body
    doc = read(tmp_path, quarto, body, profile)
    assert [(x["kind"], x["text"]) for x in doc.math] == [("DisplayMath", formula)]
    tex = restore_display_math(
        pandoc(quarto, json.dumps(prepare_ast(doc, tmp_path)), "json", "latex"), doc
    )
    assert formula in tex


def test_empty_quoted_display_is_not_hidden_by_quote_markers(tmp_path, quarto):
    with pytest.raises(NoteError) as error:
        read(tmp_path, quarto, "> $$\n> $$")
    assert error.value.diagnostic.code == "STRUCTURE_INVALID"
    assert "为空" in error.value.diagnostic.message


@pytest.mark.parametrize("profile", ["markdown", "obsidian"])
def test_display_math_after_paragraph_text_preserves_all_formulas(tmp_path, quarto, profile):
    body = "- 原创说明：$$  x=y  $$，续文 $z$，另一个 $$u=v$$。"
    doc = read(tmp_path, quarto, body, profile)
    assert [x["text"] for x in doc.math] == ["  x=y  ", "z", "u=v"]
    assert [x["kind"] for x in doc.math] == ["DisplayMath", "InlineMath", "DisplayMath"]
    tex = restore_display_math(
        pandoc(quarto, json.dumps(prepare_ast(doc, tmp_path)), "json", "latex"), doc
    )
    assert all(x["text"] in tex for x in doc.math)
    assert all(text in tex for text in ["原创说明", "续文", "另一个"])


@pytest.mark.parametrize("body,expected", [
    ("$$x$$ $$y$$", ["x", "y"]),
    ("$$x=\ny$$ 续文 $z$", ["x=\ny", "z"]),
    ("$$\nx$$ $$y$$", ["\nx", "y"]),
])
def test_closing_display_does_not_hide_following_text_or_math(tmp_path, quarto, body, expected):
    doc = read(tmp_path, quarto, body)
    assert [x["text"] for x in doc.math] == expected
    tex = restore_display_math(
        pandoc(quarto, json.dumps(prepare_ast(doc, tmp_path)), "json", "latex"), doc
    )
    assert all(text in tex for text in expected)
    if "续文" in body:
        assert "续文" in tex


@pytest.mark.parametrize("profile", ["markdown", "obsidian"])
@pytest.mark.parametrize("columns", ["cc|r", "l c || r", "|c|"])
def test_array_keeps_column_rules_and_formula_bytes(tmp_path, quarto, profile, columns):
    row = " & ".join("a_" + str(index) for index, char in enumerate(columns) if char in "lcr")
    formula = r"\left(\begin{array}{" + columns + "}" + row + r"\end{array}\right)"
    doc = read(tmp_path, quarto, "$$" + formula + "$$", profile)
    assert doc.math[0]["text"] == formula
    tex = restore_display_math(
        pandoc(quarto, json.dumps(prepare_ast(doc, tmp_path)), "json", "latex"), doc
    )
    assert formula in tex


@pytest.mark.parametrize("columns", ["", "|||", "p{2cm}", r"@{\quad}c", "*{2}{c}"])
def test_array_rejects_unsupported_column_preambles(tmp_path, quarto, columns):
    with pytest.raises(NoteError) as error:
        read(tmp_path, quarto, "$$\\begin{array}{" + columns + r"}x\end{array}$$")
    assert error.value.diagnostic.code == "UNSUPPORTED_SYNTAX"
    assert "列格式" in error.value.diagnostic.message


@pytest.mark.parametrize("ending", [r"\end{pmatrix}", ""])
def test_array_still_requires_matching_environment_end(tmp_path, quarto, ending):
    with pytest.raises(NoteError) as error:
        read(tmp_path, quarto, r"$$\begin{array}{c}x" + ending + "$$")
    assert error.value.diagnostic.code == "STRUCTURE_INVALID"


@pytest.mark.parametrize("body", ["$$x$$", "$$\n\\begin{array}{c}x\\end{array}\n$$"])
def test_strict_does_not_gain_compact_display_or_array_support(tmp_path, quarto, body):
    path = tmp_path / "strict.md"
    path.write_text("---\ntitle: 原创笔记\nauthor: 原创示例\n---\n\n" + body, encoding="utf-8")
    with pytest.raises(NoteError):
        read_document(path, quarto, "strict")


def test_manual_tags_remain_outside_measuring_box(tmp_path, quarto):
    doc = read(tmp_path, quarto, "$$\nx+y=z \\tag{1}\n$$\n\n$$\nu=v \\tag{1}\n$$")
    ast = prepare_ast(doc, tmp_path)
    maths = [n for n in nodes(ast["blocks"]) if n["t"] == "Math"]
    assert not any("NtwoLDisplay" in n["c"][1] for n in maths)
    tex = restore_display_math(pandoc(quarto, json.dumps(ast), "json", "latex"), doc)
    assert all(m["text"] in tex for m in doc.math)
    assert tex.count(r"\tag{1}") == 2


@pytest.mark.parametrize("formula", [r"x\tag{1}", r"x\tag{1}\tag{2}", r"x\tag{\input{a}}"])
def test_manual_tag_boundaries(tmp_path, quarto, formula):
    with pytest.raises(NoteError):
        read(tmp_path, quarto, "$" + formula + "$")
