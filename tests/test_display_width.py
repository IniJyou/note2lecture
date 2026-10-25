"""普通公式保持原文，测宽错误回到对应公式；输入均为原创临时内容。"""

import json

from note2lecture.document import nodes, read_document
from note2lecture.exporter import math_width_diagnostic, prepare_ast, restore_display_math
from note2lecture.tools import pandoc


def test_display_does_not_rewrite_formula(tmp_path, quarto):
    formula = "\np+q=r+s+t\n"
    path = tmp_path / "note.md"
    text = "# 原创样例\n\n正文。\n\n$$" + formula + "$$\n\n后文。\n"
    path.write_text(text, encoding="utf-8")
    doc = read_document(path, quarto, "markdown")
    ast = prepare_ast(doc, tmp_path)
    tex = restore_display_math(pandoc(quarto, json.dumps(ast), "json", "latex"), doc)
    assert r"\NtwoLMathDisplay{" in tex
    assert formula in tex
    assert path.read_text(encoding="utf-8") == text


def test_width_error_uses_formula_hash_and_original_line(tmp_path, quarto):
    path = tmp_path / "note.md"
    path.write_text("# 标题\n\n前段。\n\n$$\np+q=r\n$$\n", encoding="utf-8")
    doc = read_document(path, quarto, "markdown")
    log = "N2LWIDE:" + doc.math[0]["sha256"] + "\nN2LDIMS:900.0pt:700.0pt\n"
    result = math_width_diagnostic(log, doc)
    assert result.code == "LAYOUT_OVERFLOW"
    assert result.line == 6
    assert result.approximate is False
    assert "316.3 mm" in result.message and "246.0 mm" in result.message


def test_unknown_width_marker_is_not_mapped_to_a_false_source(tmp_path, quarto):
    path = tmp_path / "note.md"
    path.write_text("# 标题\n\n$x$\n", encoding="utf-8")
    doc = read_document(path, quarto, "markdown")
    assert math_width_diagnostic("N2LWIDE:" + "0" * 64, doc) is None


def test_explicit_equation_label_keeps_native_cross_reference(tmp_path, quarto):
    path = tmp_path / "note.md"
    path.write_text("# 标题\n\n参见 @eq-a。\n\n$$\np+q=r\n$$ {#eq-a}\n", encoding="utf-8")
    doc = read_document(path, quarto, "markdown")
    ast = prepare_ast(doc, tmp_path)
    math = [n for n in nodes(ast["blocks"]) if n["t"] == "Math"]
    assert len(math) == 1
    assert math[0]["c"][0]["t"] == "DisplayMath"
    assert r"\NtwoLDisplay{" in math[0]["c"][1]
    assert "eq-a" in doc.labels and "eq-a" in doc.references
