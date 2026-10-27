"""普通代码语言兼容：只排版原文，不把语言标签作为后端执行指令。"""

import json

import pytest

from note2lecture.diagnostics import NoteError
from note2lecture.document import digest, nodes, read_document
from note2lecture.exporter import WORKING_MARKDOWN_FORMAT, prepare_ast, render_config
from note2lecture.tools import pandoc


@pytest.mark.parametrize("profile", ["markdown", "obsidian"])
@pytest.mark.parametrize("language", [
    "json", "powershell", "bash", "javascript", "c++", "c#", "mermaid", "ojs", "new-lang.v1",
])
def test_plain_language_is_literal_through_working_copy(tmp_path, quarto, profile, language):
    code = '\t$ unmatched @thm-none [[literal]]\n\\end{Verbatim}\nraise RuntimeError("never run")'
    text = f"# 原创代码\n\n```{language}\n{code}\n```\n\n末尾正文。\n"
    path = tmp_path / "note.md"
    path.write_text(text, encoding="utf-8")
    doc = read_document(path, quarto, profile)
    assert doc.code == [code] and not doc.math and not doc.references
    original = next(x for x in nodes(doc.ast["blocks"]) if x["t"] == "CodeBlock")
    # Pandoc 对 c++ 的标准别名规范化不改变代码正文。
    expected_language = "cpp" if language == "c++" else language
    assert original["c"][0] == ["", [expected_language], []]
    ast = prepare_ast(doc, tmp_path)
    markdown = pandoc(quarto, json.dumps(ast), "json", WORKING_MARKDOWN_FORMAT)
    restored = json.loads(pandoc(quarto, markdown, doc.reader, "json"))
    block = next(x for x in nodes(restored["blocks"]) if x["t"] == "CodeBlock")
    target = "code/" + digest(code.encode()) + ".txt"
    assert block["c"] == [["", [], [["n2l-code", target]]], code]
    assert (tmp_path / target).read_bytes() == code.encode()
    assert original["c"][0] == ["", [expected_language], []]
    assert render_config(doc.metadata)["execute"] == {"enabled": False}
    assert path.read_text(encoding="utf-8") == text


@pytest.mark.parametrize("profile", ["markdown", "obsidian"])
@pytest.mark.parametrize("info", [
    "{python}", "{r}", "{=latex}", "json eval=true", "json {#code-a}", "{.json}",
])
def test_execution_units_and_extra_attributes_still_rejected(tmp_path, quarto, profile, info):
    path = tmp_path / "note.md"
    path.write_text(f"# 原创\n\n```{info}\nnever run\n```\n", encoding="utf-8")
    with pytest.raises(NoteError) as error:
        read_document(path, quarto, profile)
    diagnostic = error.value.diagnostic
    assert diagnostic.code == "UNSUPPORTED_SYNTAX"
    assert (diagnostic.line, diagnostic.block) == (3, "code")
    assert "语言标签" in diagnostic.message


def test_strict_keeps_n0_language_boundary(tmp_path, quarto):
    path = tmp_path / "note.md"
    path.write_text('---\ntitle: 原创\nauthor: 测试\n---\n```json\n{}\n```\n', encoding="utf-8")
    with pytest.raises(NoteError) as error:
        read_document(path, quarto, "strict")
    assert error.value.diagnostic.code == "UNSUPPORTED_SYNTAX"
    assert "strict" in error.value.diagnostic.message
