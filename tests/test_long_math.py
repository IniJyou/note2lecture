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
