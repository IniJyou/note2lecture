"""Obsidian 规则使用公开样例和原创临时输入，不访问私人笔记库。"""

from pathlib import Path

import pytest
from PIL import Image

from note2lecture.diagnostics import NoteError
from note2lecture.document import nodes, plain, read_document
from note2lecture.tools import ROOT


def read(tmp_path, quarto, text):
    path = tmp_path / "note.md"
    path.write_text(text, encoding="utf-8")
    return read_document(path, quarto, "obsidian")


def test_public_fixture(quarto):
    path = ROOT / "examples/04-obsidian.md"
    before = path.read_bytes()
    doc = read_document(path, quarto, "obsidian")
    assert len(doc.resources) == 1 and len(doc.math) == 12 and len(doc.code) == 1
    assert len(doc.internal_links) == 2
    assert [x["kind"] for x in doc.obsidian["callouts"]] == ["note", "tip", "warning"]
    assert [x["line"] for x in doc.obsidian["callouts"]] == [15, 24, 27]
    assert len(doc.warnings) == 2
    assert all(x.code == "WIKI_NOTE_NOT_PACKAGED" and x.line == 13 for x in doc.warnings)
    assert doc.code == [
        "[[这里不是要读取的笔记]]\n![[这里不是要读取的图片.png]]\n> [!note] 这里只是文字"
    ]
    assert path.read_bytes() == before


def test_target_body_is_never_read_and_alias_stays_visible(tmp_path, quarto, monkeypatch):
    target = tmp_path / "相关.md"
    target.write_bytes(b"invalid-utf8-\xff; must never be parsed")
    original = Path.open

    def guarded(path, *args, **kwargs):
        assert path != target, "跨笔记双链不应读取目标正文"
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded)
    doc = read(tmp_path, quarto, "# 笔记\n\n[[相关|自定义名称]]\n")
    assert "自定义名称" in plain(doc.ast["blocks"])
    assert "相关.md" in plain(doc.ast["blocks"])
    assert not any(x["t"] == "Link" for x in nodes(doc.ast["blocks"]))
    assert doc.obsidian["links"][0]["body_read"] is False


def test_forward_and_backward_heading_links_use_full_title(tmp_path, quarto):
    doc = read(
        tmp_path, quarto, ("# 笔记\n\n[[#A title|向前]]\n\n## A title\n\n[[#A title|返回]]\n")
    )
    assert len(doc.internal_links) == 2
    assert len({x["to"] for x in doc.internal_links}) == 1
    assert all(x["target"] in doc.labels for x in doc.obsidian["links"])


def test_embedded_image_uses_original_bytes_and_explicit_filename_caption(tmp_path, quarto):
    path = tmp_path / "图 片.png"
    Image.new("RGB", (30, 10), "white").save(path)
    doc = read(tmp_path, quarto, "# 笔记\n\n![[图 片.png]]\n\n图示说明保持原样。\n")
    assert doc.resources[0]["original"] == "图 片.png"
    figure = next(x for x in nodes(doc.ast["blocks"]) if x["t"] == "Figure")
    assert plain(figure["c"][1]) == "图 片.png"
    assert "图示说明保持原样。" in plain(doc.ast["blocks"])


def test_same_asset_does_not_overwrite_authored_markdown_caption(tmp_path, quarto):
    Image.new("RGB", (30, 10), "white").save(tmp_path / "image.png")
    doc = read(tmp_path, quarto, ("# 笔记\n\n![用户写的图题](image.png)\n\n![[image.png]]\n"))
    figures = [x for x in nodes(doc.ast["blocks"]) if x["t"] == "Figure"]
    assert [plain(x["c"][1]) for x in figures] == ["用户写的图题", "image.png"]


def test_inline_literals_and_math_are_not_resolved_as_links(tmp_path, quarto):
    doc = read(tmp_path, quarto, "# 笔记\n\n`[[不存在]]` 和 `![[不存在.png]]`，以及 $[[x]]$。\n")
    assert not doc.resources and not doc.obsidian["links"] and not doc.obsidian["embeds"]
    assert doc.math[0]["text"] == "[[x]]"


def test_callout_without_custom_title_keeps_multiple_paragraphs(tmp_path, quarto):
    doc = read(tmp_path, quarto, "# 笔记\n\n> [!note]\n> 第一段。\n>\n> 第二段。\n")
    assert doc.obsidian["callouts"][0]["title"] == ""
    assert all(x in plain(doc.ast["blocks"]) for x in ["笔记", "第一段。", "第二段。"])


def test_callout_preserves_multiline_body_math_and_link(tmp_path, quarto):
    doc = read(
        tmp_path,
        quarto,
        ("# 笔记\n\n## 目标\n\n> [!tip] 原题头\n> 第一行 $x+1$。\n> 第二行 [[#目标|回查]]。\n"),
    )
    assert doc.obsidian["callouts"][0]["title"] == "原题头"
    assert doc.math[0]["text"] == "x+1"
    assert all(x in plain(doc.ast["blocks"]) for x in ["第一行", "第二行", "回查"])
    assert len(doc.internal_links) == 1


@pytest.mark.parametrize(
    "body,code,line",
    [
        ("[[missing]]\n", "REF_UNDEFINED", 3),
        ("[[../outside]]\n", "RESOURCE_PATH", 3),
        ("[[/absolute]]\n", "RESOURCE_PATH", 3),
        ("[[https://example.com]]\n", "RESOURCE_PATH", 3),
        ("[[name#heading]]\n", "RESOURCE_PATH", 3),
        ("[[#missing]]\n", "REF_UNDEFINED", 3),
        ("[[#^block]]\n", "UNSUPPORTED_SYNTAX", 3),
        ("[[name|]]\n", "UNSUPPORTED_SYNTAX", 3),
        ("[[not-closed\n", "UNSUPPORTED_SYNTAX", 3),
        ("![[missing.png]]\n", "RESOURCE_MISSING", 3),
        ("![[../outside.png]]\n", "RESOURCE_PATH", 3),
        ("![[note.md]]\n", "UNSUPPORTED_SYNTAX", 3),
        ("![[image.png|600]]\n", "UNSUPPORTED_SYNTAX", 3),
        ("正文 ![[missing.png]] 末尾\n", "UNSUPPORTED_SYNTAX", 3),
        ("> [!danger] 标题\n> 正文。\n", "UNSUPPORTED_SYNTAX", 3),
        ("> [!tip]- 标题\n> 正文。\n", "UNSUPPORTED_SYNTAX", 3),
        ("> [!note] 只有题头\n", "STRUCTURE_INVALID", 3),
        ("> [!note] 外层\n> > [!tip] 内层\n> > 正文。\n", "UNSUPPORTED_SYNTAX", 4),
    ],
)
def test_faults_are_located_in_original_input(tmp_path, quarto, body, code, line):
    with pytest.raises(NoteError) as error:
        read(tmp_path, quarto, "# 笔记\n\n" + body)
    assert error.value.diagnostic.code == code
    assert error.value.diagnostic.line == line


def test_duplicate_heading_is_ambiguous_instead_of_silently_using_first(tmp_path, quarto):
    with pytest.raises(NoteError) as error:
        read(tmp_path, quarto, "# 笔记\n\n[[#重复]]\n\n## 重复\n\n正文。\n\n## 重复\n")
    assert error.value.diagnostic.code == "REF_AMBIGUOUS"
    assert error.value.diagnostic.line == 3


def test_html_anchor_and_obsidian_extensions_coexist(tmp_path, quarto):
    doc = read(tmp_path, quarto, ('# 笔记\n\n<a id="start"></a>\n\n## 目标\n\n[[#目标|回查]]\n'))
    assert len(doc.internal_links) == 1
    assert not any(x["t"].startswith("Raw") for x in nodes(doc.ast["blocks"]))


def test_fake_internal_div_is_not_accepted(tmp_path, quarto):
    with pytest.raises(NoteError) as error:
        read(tmp_path, quarto, "# 笔记\n\n::: {.n2l-callout}\n假造环境\n:::\n")
    assert error.value.diagnostic.code == "UNSUPPORTED_SYNTAX"


@pytest.mark.parametrize(
    "body,code",
    [
        ("![[missing.png]]\n", "RESOURCE_MISSING"),
        ("> [!danger] 标题\n> 正文。\n", "UNSUPPORTED_SYNTAX"),
        ("[[#重复]]\n\n## 重复\n\n正文。\n\n## 重复\n", "REF_AMBIGUOUS"),
    ],
)
def test_invalid_input_never_publishes_pdf_or_source_zip(tmp_path, quarto, monkeypatch, body, code):
    from note2lecture import exporter

    path = tmp_path / "bad.md"
    path.write_text("# 笔记\n\n" + body, encoding="utf-8")
    monkeypatch.setattr(exporter, "dependencies", lambda _: ({}, []))
    output = tmp_path / "output"
    result = exporter.export_document(path, output, quarto, "obsidian")
    assert result["status"] == "failed"
    assert result["diagnostics"][0]["code"] == code
    assert not (output / "lecture.pdf").exists()
    assert not (output / "lecture-source.zip").exists()
