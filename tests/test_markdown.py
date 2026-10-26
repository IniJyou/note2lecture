"""全部使用原创临时笔记；测试不依赖私人笔记库。"""

import pytest
from PIL import Image

from note2lecture.diagnostics import NoteError
from note2lecture.document import nodes, plain, read_document
from note2lecture.exporter import prepare_ast, restore_display_math
from note2lecture.tools import pandoc


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


@pytest.mark.parametrize("profile", ["markdown", "obsidian"])
def test_indented_atx_headings_keep_source_locations(tmp_path, quarto, profile):
    path = tmp_path / "note.md"
    text = ("# 原创标题\n\n## 原创章节\n\n- 条目\n\n  ### 原创子节\n\n"
            "  正文。\n\n  ```python\n  raise RuntimeError('never run')\n  ```\n\n"
            "另一个段落。\n\n```text\n  ## 代码中的字面标题\n```\n")
    path.write_text(text, encoding="utf-8")
    doc = read_document(path, quarto, profile)
    headers = [x for x in nodes(doc.ast["blocks"]) if x["t"] == "Header"]
    assert doc.metadata["title"] == "原创标题"
    assert [x["c"][0] for x in headers] == [1, 2]
    assert [plain(x["c"][2]) for x in headers] == ["原创章节", "原创子节"]
    label = doc.labels[headers[1]["c"][1][0]]
    assert (label["line"], label["column"]) == (7, 3)
    assert doc.code == ["raise RuntimeError('never run')", "  ## 代码中的字面标题"]
    assert path.read_text(encoding="utf-8") == text


@pytest.mark.parametrize("spaces", [1, 2, 3])
def test_indented_literal_hash_text_is_not_promoted(tmp_path, quarto, spaces):
    text = "# 笔记\n\n## 章节\n\n" + " " * spaces + "## 普通缩进文本\n\n正文。\n"
    doc = read(tmp_path, quarto, text)
    headers = [x for x in nodes(doc.ast["blocks"]) if x["t"] == "Header"]
    assert len(headers) == 1
    assert "普通缩进文本" in plain(doc.ast["blocks"])


def test_list_can_compose_supported_blocks_and_preserve_empty_item(tmp_path, quarto):
    Image.new("RGB", (24, 18), "white").save(tmp_path / "original.png")
    text = ("# 原创笔记\n\n## 章节\n\n-\n- 原创条目。\n\n"
            "  > 原创引用与 $x$。\n\n  ![原创图](original.png)\n\n"
            "  | 变量 | 解释 |\n  |---|---|\n  | n | 样本数 |\n\n  条目结尾。\n")
    doc = read(tmp_path, quarto, text)
    found = list(nodes(doc.ast["blocks"]))
    listing = next(x for x in found if x["t"] == "BulletList")
    assert listing["c"][0] == []
    assert {"Table", "Figure", "BlockQuote"} <= {x["t"] for x in listing["c"][1]}
    assert len(doc.resources) == len(doc.math) == 1
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


@pytest.mark.parametrize("profile", ["markdown", "obsidian"])
@pytest.mark.parametrize("opening,closing", [("$$", "$$"), (r"\[", r"\]")])
def test_list_paragraphs_and_indented_math_keep_content(
    tmp_path, quarto, profile, opening, closing
):
    text = (
        "# 原创测试\n\n## 列表公式\n\n- **条目**\n\n"
        "  前段 \\(x_1\\) 与 $x_2$。\n\n"
        f"  {opening}\n  \\dim V = 2\n  {closing}\n\n"
        "  中段。\n\n  - 子条目\n\n"
        f"    {opening}\n    y = x_1 + x_2\n    {closing}\n\n"
        "  后段。\n\n---\n\n结尾。\n"
    )
    path = tmp_path / "note.md"
    path.write_text(text, encoding="utf-8")
    doc = read_document(path, quarto, profile)
    assert [x["kind"] for x in doc.math] == [
        "InlineMath", "InlineMath", "DisplayMath", "DisplayMath"
    ]
    assert [x["text"].strip() for x in doc.math] == ["x_1", "x_2", r"\dim V = 2", "y = x_1 + x_2"]
    assert all(x in plain(doc.ast["blocks"]) for x in ["前段", "中段", "子条目", "后段", "结尾"])
    assert sum(x["t"] == "HorizontalRule" for x in nodes(doc.ast["blocks"])) == 1
    assert path.read_text(encoding="utf-8") == text


@pytest.mark.parametrize("opening,closing", [("$$", "$$"), (r"\[", r"\]")])
def test_unclosed_indented_display_reports_opening(tmp_path, quarto, opening, closing):
    with pytest.raises(NoteError) as error:
        read(tmp_path, quarto, f"# 标题\n\n- 条目\n\n  {opening}\n  x = 2\n")
    assert error.value.diagnostic.code == "STRUCTURE_INVALID"
    assert error.value.diagnostic.line == 5
    assert "独立公式未闭合" in error.value.diagnostic.message


@pytest.mark.parametrize("formula", [r"\(x", r"x\)", r"\(x\]", r"\[x\)"])
def test_unpaired_backslash_math_is_not_silently_plain_text(tmp_path, quarto, formula):
    with pytest.raises(NoteError) as error:
        read(tmp_path, quarto, "# 标题\n\n" + formula + "\n")
    assert error.value.diagnostic.code == "STRUCTURE_INVALID"
    assert error.value.diagnostic.line == 3


@pytest.mark.parametrize(
    "body",
    [r"\(\input{secret}\)", "- 条目\n\n  $$\n  \\input{secret}\n  $$"],
)
def test_added_math_syntax_still_rejects_unsafe_commands(tmp_path, quarto, body):
    with pytest.raises(NoteError) as error:
        read(tmp_path, quarto, "# 标题\n\n" + body + "\n")
    assert error.value.diagnostic.code == "UNSUPPORTED_SYNTAX"
    assert r"\input" in error.value.diagnostic.message


def test_toc_placeholder_maps_only_standalone_body_paragraphs(tmp_path, quarto):
    doc = read(
        tmp_path,
        quarto,
        "# 标题\n\n[toc]\n\n[TOC]\n\n正文中的 [toc] 保留。\n\n"
        "`[toc]` 与 `\\(literal\\)`。\n\n```text\n[toc]\n\\(not closed\n$$\n```\n",
    )
    assert [x for x in doc.adaptations if x["kind"] == "toc"] == [
        {"kind": "toc", "from": "[toc]", "to": "template-toc"},
        {"kind": "toc", "from": "[TOC]", "to": "template-toc"},
    ]
    assert "正文中的 [toc] 保留。" in plain(doc.ast["blocks"])
    assert doc.code == ["[toc]\n\\(not closed\n$$"]
    assert not doc.math


@pytest.mark.parametrize("body", [r"\(x\)", "---", "- 条目\n\n  前段。\n\n  后段。"])
def test_strict_profile_does_not_inherit_new_markdown_rules(tmp_path, quarto, body):
    path = tmp_path / "note.md"
    path.write_text("---\ntitle: 测试\nauthor: 示例\n---\n\n" + body + "\n", encoding="utf-8")
    with pytest.raises(NoteError) as error:
        read_document(path, quarto)
    assert error.value.diagnostic.code == "UNSUPPORTED_SYNTAX"


def test_markdown_list_depth_supports_four_levels_and_rejects_five(tmp_path, quarto):
    text = "# 标题\n\n- 第一层\n  - 第二层\n    - 第三层\n      - 第四层\n"
    doc = read(tmp_path, quarto, text)
    assert sum(x["t"] == "BulletList" for x in nodes(doc.ast["blocks"])) == 4
    with pytest.raises(NoteError) as error:
        read(tmp_path, quarto, text + "        - 第五层\n")
    assert error.value.diagnostic.code == "UNSUPPORTED_SYNTAX"


def test_backend_indentation_cannot_change_display_math(tmp_path, quarto):
    formula = "\n  x + y = 3\n"
    doc = read(tmp_path, quarto, "# 标题\n\n- 条目\n\n  $$\n    x + y = 3\n  $$\n")
    assert doc.math[0]["text"] == formula
    ast = prepare_ast(doc, tmp_path)
    import json

    tex = pandoc(quarto, json.dumps(ast), "json", "latex")
    restored = restore_display_math(tex, doc)
    assert formula in restored
    assert "NtwoLMathToken" not in restored
    with pytest.raises(NoteError):
        restore_display_math(tex.replace("NtwoLMathToken", "MissingToken"), doc)
    with pytest.raises(NoteError):
        restore_display_math(tex + tex, doc)
