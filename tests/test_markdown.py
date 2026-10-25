"""全部使用原创临时笔记；测试不依赖私人笔记库。"""

import pytest
from PIL import Image

from note2lecture.diagnostics import NoteError
from note2lecture.document import nodes, plain, read_document
from note2lecture.exporter import prepare_ast


def read(tmp_path, quarto, text):
    path = tmp_path / "note.md"
    path.write_text(text, encoding="utf-8")
    return read_document(path, quarto, "markdown")


def test_title_anchors_and_numbered_headings(tmp_path, quarto):
    text = (
        '# 原创学习笔记\n\n[回查](#concept)\n\n<a\u00a0id="concept"></a>\n\n'
        "## 0. 概念\n\n### 0.1 小节\n\n正文。\n"
    )
    doc = read(tmp_path, quarto, text)
    headers = [x for x in nodes(doc.ast["blocks"]) if x["t"] == "Header"]
    assert doc.metadata == {"title": "原创学习笔记", "lang": "zh-CN"}
    assert [x["c"][0] for x in headers] == [1, 2]
    assert [plain(x["c"][2]) for x in headers] == ["0. 概念", "0.1 小节"]
    link = next(x for x in nodes(doc.ast["blocks"]) if x["t"] == "Link")
    assert link["c"][2][0] == "#" + headers[0]["c"][1][0]
    assert doc.labels[headers[0]["c"][1][0]]["line"] == 7
    assert not any(x["t"].startswith("Raw") for x in nodes(doc.ast["blocks"]))
    assert doc.path.read_text(encoding="utf-8") == text


def test_local_documents_remain_text_and_are_never_opened(tmp_path, quarto):
    doc = read(tmp_path, quarto, "# 笔记\n\n[参考](../private/missing.md)\n")
    assert not doc.resources
    assert doc.warnings[0].code == "LOCAL_LINK_NOT_PACKAGED"
    assert doc.warnings[0].line == 3
    assert doc.warnings[0].severity == "warning"
    assert "../private/missing.md" in plain(doc.ast["blocks"])
    assert not any(x["t"] == "Link" for x in nodes(doc.ast["blocks"]))


def test_unlabelled_image_and_table_with_inline_code(tmp_path, quarto):
    Image.new("RGB", (30, 20), "black").save(tmp_path / "图.png")
    doc = read(
        tmp_path,
        quarto,
        ("# 笔记\n\n![原创示意图](图.png)\n\n| 接口 | 含义 |\n|---|---|\n| `small_test` | $x$ |\n"),
    )
    assert len(doc.resources) == 1
    assert len(doc.math) == 1 and doc.math[0]["text"] == "x"
    assert len(doc.labels) == 1
    assert next(iter(doc.labels)).startswith("fig-")


@pytest.mark.parametrize(
    "text,code,line",
    [
        ("# 笔记\n\n[回查](#missing)\n", "REF_UNDEFINED", 3),
        ('# 笔记\n\n<a id="orphan"></a>\n\n正文\n', "UNSUPPORTED_SYNTAX", 3),
        ("# 笔记\n\n<script>danger()</script>\n", "UNSUPPORTED_SYNTAX", 3),
        ("# 笔记\n\n[[其他笔记]]\n", "UNSUPPORTED_SYNTAX", 3),
        ("# 笔记\n\n> [!note] 提醒\n", "UNSUPPORTED_SYNTAX", 3),
        ("# 笔记\n\n![越界](../secret.png)\n", "RESOURCE_PATH", 3),
        ("# 笔记\n\n$$\n\\input{secret}\n$$\n", "UNSUPPORTED_SYNTAX", 4),
    ],
)
def test_markdown_rejects_unsupported_with_source_position(tmp_path, quarto, text, code, line):
    with pytest.raises(NoteError) as error:
        read(tmp_path, quarto, text)
    assert error.value.diagnostic.code == code
    assert error.value.diagnostic.line == line


def test_matrix_line_break_is_not_an_unknown_command(tmp_path, quarto):
    math = r"\begin{bmatrix}x_1\\x_2\end{bmatrix}\longrightarrow y\mid z\odot w"
    doc = read(tmp_path, quarto, "# 笔记\n\n$$\n" + math + "\n$$\n")
    assert doc.math[0]["text"] == "\n" + math + "\n"


def test_command_after_matrix_line_break_still_checked(tmp_path, quarto):
    with pytest.raises(NoteError) as error:
        read(tmp_path, quarto, "# 笔记\n\n$$\n" + r"x\\\input{secret}" + "\n$$\n")
    assert error.value.diagnostic.code == "UNSUPPORTED_SYNTAX"


def test_code_literals_are_not_adapted_or_executed(tmp_path, quarto):
    code = '<a id="fake"></a>\n## 假标题\n[[双链]]\nraise RuntimeError("never run")'
    doc = read(tmp_path, quarto, "# 笔记\n\n```python\n" + code + "\n```\n")
    assert doc.code == [code]
    assert not doc.labels


def test_existing_strict_yaml_stays_supported(tmp_path, quarto):
    doc = read(tmp_path, quarto, "---\ntitle: 标题\nauthor: 作者\n---\n\n# 开始 {#sec-a}\n")
    assert doc.metadata["author"] == "作者"
    assert "sec-a" in doc.labels


def test_duplicate_html_anchor_is_not_silently_retargeted(tmp_path, quarto):
    with pytest.raises(NoteError) as error:
        read(
            tmp_path,
            quarto,
            ('# 笔记\n\n<a id="same"></a>\n\n## 甲\n\n<a id="same"></a>\n\n## 乙\n'),
        )
    assert error.value.diagnostic.code == "LABEL_DUPLICATE"


def test_redundant_anchor_at_same_heading_is_valid(tmp_path, quarto):
    doc = read(tmp_path, quarto, '# 笔记\n\n<a id="start"></a>\n\n## Start\n\n[返回](#start)\n')
    assert len(doc.internal_links) == 1


def test_heading_bookmarks_keep_plain_numbers_and_names(tmp_path, quarto):
    doc = read(tmp_path, quarto, "# 笔记\n\n## 1. Interface run_test\n\nrun_test\n")
    ast = prepare_ast(doc, tmp_path)
    heading = next(x for x in nodes(ast["blocks"]) if x["t"] == "Header")
    assert not any(x["t"] == "RawInline" for x in nodes(heading))
    assert plain(heading["c"][2]) == "1. Interface run_test"
    assert any(x["t"] == "RawInline" for x in nodes(ast["blocks"]))


def test_repeated_prose_maps_forward_instead_of_to_first_occurrence(tmp_path, quarto):
    doc = read(tmp_path, quarto, "# 笔记\n\n这里的第一段正文。\n\n这里的第二段正文。\n")
    ast = prepare_ast(doc, tmp_path)
    markers = [x["c"][1] for x in ast["blocks"] if x["t"] == "RawBlock"]
    assert markers == ["% N2L_SOURCE 3 0", "% N2L_SOURCE 5 1"]


def test_number_reference_to_unnumbered_heading_is_explicitly_rejected(tmp_path, quarto):
    with pytest.raises(NoteError) as error:
        read(tmp_path, quarto, "# 笔记\n\n## 小节 {#sec-a}\n\n@sec-a\n")
    assert error.value.diagnostic.code == "UNSUPPORTED_SYNTAX"
    assert error.value.diagnostic.line == 5
