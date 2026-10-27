"""原创正文字符：同字形字体回退、数学/代码隔离和真实缺字候选位置。"""

import json
import re

import pytest
from test_portrait_math import compile_tex

from note2lecture.diagnostics import Source
from note2lecture.document import Document, nodes, read_document
from note2lecture.exporter import (
    WORKING_MARKDOWN_FORMAT,
    log_diagnostics,
    prepare_ast,
    restore_display_math,
)
from note2lecture.text_glyphs import GLYPHS, adapt_text_glyphs, glyph_inlines, monochrome_text
from note2lecture.tools import pandoc


def read(tmp_path, quarto, text, profile="markdown"):
    path = tmp_path / "original.md"
    path.write_text(text, encoding="utf-8")
    return read_document(path, quarto, profile)


@pytest.mark.parametrize("profile", ["markdown", "obsidian"])
def test_text_fallback_leaves_math_code_and_link_destination_unchanged(tmp_path, quarto, profile):
    text = ("# 字形\n\n## ✓检查\n\n正文λ与⚠️、❌、💡。*λ* **λ** "
            "[✓](https://example.com/λ)。`λ✓` 与 $\\lambda+λ$。\n\n```text\nλ✓\n```\n")
    doc = read(tmp_path, quarto, text, profile)
    before = json.dumps(doc.ast, ensure_ascii=False)
    ast = prepare_ast(doc, tmp_path)
    assert json.dumps(doc.ast, ensure_ascii=False) == before
    assert any(n["t"] == "RawInline" and "NtwoLGreekText{λ}" in n["c"][1]
               for n in nodes(ast["blocks"]))
    assert any(n["t"] == "RawInline" and "NtwoLUnicodeSymbol{⚠️}" in n["c"][1]
               for n in nodes(ast["blocks"]))
    assert next(n for n in nodes(ast["blocks"]) if n["t"] == "Code")["c"][1] == "λ✓"
    assert next(n for n in nodes(ast["blocks"]) if n["t"] == "CodeBlock")["c"][1] == "λ✓"
    link = next(n for n in nodes(ast["blocks"]) if n["t"] == "Link")
    assert link["c"][2][0].endswith("/λ")
    tex = restore_display_math(pandoc(quarto, json.dumps(ast), "json", "latex"), doc)
    assert r"\(\lambda+λ\)" in tex
    assert doc.path.read_text(encoding="utf-8") == text


@pytest.mark.parametrize("title", ["💡字形λ", "$\\lambda$与✓", "⚠️提醒"])
def test_title_glyphs_have_controlled_display_and_plain_bookmark(tmp_path, quarto, title):
    doc = read(tmp_path, quarto, "# " + title + "\n\n正文。\n")
    assert doc.title_token
    assert r"\texorpdfstring" in doc.title_tex
    assert "NtwoLUnicodeSymbol" in doc.title_tex
    assert not GLYPHS.search("".join(n["c"] for n in nodes(prepare_ast(doc, tmp_path)["blocks"])
                                    if n["t"] == "Str"))


def test_yaml_title_stays_literal_even_when_it_uses_a_glyph(tmp_path, quarto):
    doc = read(tmp_path, quarto, '---\ntitle: "λ*字面*"\nauthor: 原创\n'
               'date: "2026-10-27"\n---\n\n正文。\n')
    assert r"\NtwoLGreekText{λ}" in doc.title_tex
    assert "*字面*" in doc.title_tex and r"\emph" not in doc.title_tex


@pytest.mark.parametrize("chars", ["λ", "✓⚠❌", "💡⚠️⚠︎", "ΑβϑΩᾠ", "中✓、⚠️、❌、💡。文"])
def test_native_text_glyphs_compile_and_extract_in_styles(tmp_path, quarto, chars):
    ast = json.loads(pandoc(quarto, "", "markdown", "json"))
    ast["blocks"] = [{"t": "Para", "c": glyph_inlines(chars)}]
    tex = pandoc(quarto, json.dumps(ast), "json", "latex")
    body = (r"\begin{document}" + tex + r"\par\textit{" + tex.strip() + "}"
            r"\par\textbf{" + tex.strip() + r"}\end{document}")
    result, log = compile_tex(tmp_path, body)
    assert result.returncode == 0, log[-2000:]
    assert not re.search("Missing character|Overfull|font shape.*undefined", log, re.I)
    from note2lecture.tools import run

    extracted = run(["pdftotext", tmp_path / "test.pdf", "-"]).stdout
    for char in chars.replace("\ufe0f", "").replace("\ufe0e", ""):
        assert char in extracted
    assert monochrome_text(chars) in re.sub(r"\s", "", extracted)


def test_symbol_style_comparison_does_not_remove_unknown_or_isolated_selectors():
    assert monochrome_text("⚠️✓︎❌️💡️") == "⚠✓❌💡"
    assert monochrome_text("a️🧪️️") == "a️🧪️️"


def test_unicode_table_boundaries_survive_working_markdown_roundtrip(tmp_path, quarto):
    doc = read(tmp_path, quarto, "# 表格\n\n| 项目 | 标记 | 参数 |\n| --- | --- | --- |\n"
               "| 已核对 | ✓ | λ |\n| 待复核 | ⚠️ | α |\n")
    ast = prepare_ast(doc, tmp_path)
    markdown = pandoc(quarto, json.dumps(ast), "json", WORKING_MARKDOWN_FORMAT)
    restored = json.loads(pandoc(quarto, markdown, "markdown-smart", "json"))
    raw = [n["c"][1] for n in nodes(restored["blocks"]) if n["t"] == "RawInline"]
    assert raw == [r"\NtwoLUnicodeSymbol{✓}", "\\NtwoLGreekText{λ}",
                   "\\NtwoLUnicodeSymbol{⚠️}", "\\NtwoLGreekText{α}"]
    assert not any(n["t"] == "Str" and "{=latex}" in n["c"] for n in nodes(restored["blocks"]))


def test_unknown_emoji_and_selectors_are_not_silently_removed():
    ast = {"t": "Para", "c": [{"t": "Str", "c": "🧪a️⚠️"}]}
    adapt_text_glyphs(ast)
    assert "🧪a️" in json.dumps(ast, ensure_ascii=False)
    assert "NtwoLUnicodeSymbol{⚠️}" in json.dumps(ast, ensure_ascii=False)


def test_missing_glyph_reports_exact_unique_source_position(tmp_path):
    text = "# 标题\n\n在这里🧪。\n"
    doc = Document(tmp_path / "original.md", Source("original.md", text), {}, text, {}, "hash")
    log = "Missing character: There is no 🧪 (U+1F9EA) in font test\n"
    result = log_diagnostics(log, doc, {"markers": []})
    assert len(result) == 1
    assert (result[0].line, result[0].column, result[0].approximate) == (3, 4, False)
    assert result[0].severity == "error"


def test_repeated_glyph_log_is_grouped_without_guessing_each_missing_occurrence(tmp_path):
    text = "# 🧪\n\n再一次🧪\n"
    doc = Document(tmp_path / "original.md", Source("original.md", text), {}, text, {}, "hash")
    log = ("Missing character: There is no 🧪 (U+1F9EA) in font test\n" * 3
           + "Overfull \\hbox at lines 900--901\n")
    result = log_diagnostics(log, doc, {"markers": [{"tex_line": 800, "source_line": 700}]})
    missing = [d for d in result if d.code == "GLYPH_MISSING"]
    assert len(missing) == 1 and missing[0].approximate
    assert (missing[0].line, missing[0].column) == (1, 3)
    assert missing[0].related == [
        {"line": 1, "column": 3, "kind": "source_candidate"},
        {"line": 3, "column": 4, "kind": "source_candidate"},
    ]
    assert "报告 3 次" in missing[0].hint


def test_glyph_not_in_source_stays_approximate(tmp_path):
    doc = Document(tmp_path / "original.md", Source("original.md", "正文"), {}, "正文", {}, "hash")
    result = log_diagnostics("Missing character: There is no 🧪 (U+1F9EA) in font test\n",
                             doc, {"markers": []})
    assert result[0].approximate and result[0].related is None
