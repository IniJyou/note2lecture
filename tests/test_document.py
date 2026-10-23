"""固定原创样例与临时变体；不读取私人笔记，不运行样例代码。"""

from pathlib import Path

import pytest
from PIL import Image

from note2lecture.diagnostics import NoteError, Source
from note2lecture.document import Document, lexical_scan, metadata_and_body, read_document
from note2lecture.exporter import adapt_preamble, export_document, ref_tex
from note2lecture.tools import ROOT

FRONT = '---\ntitle: "测试"\nauthor: "示例"\n---\n'


def check_text(tmp_path, quarto, body, front=FRONT):
    path = tmp_path / "note.md"
    path.write_text(front + body, encoding="utf-8")
    return read_document(path, quarto)


@pytest.mark.parametrize(
    "name,labels,refs,code",
    [
        ("01-mean.md", 6, 3, 1),
        ("02-projection.md", 8, 8, 0),
        ("03-online-mean.md", 9, 5, 1),
    ],
)
def test_original_samples(quarto, name, labels, refs, code):
    doc = read_document(ROOT / "examples" / name, quarto)
    assert (len(doc.labels), len(doc.references), len(doc.code)) == (labels, refs, code)


@pytest.mark.parametrize(
    "front",
    [
        "---\ntitle: 3\nauthor: x\n---\n",
        "---\ntitle: a\ntitle: b\nauthor: x\n---\n",
        "---\ntitle: a\nauthor: x\nexecute: true\n---\n",
        "---\ntitle: &t a\nauthor: *t\n---\n",
        '---\ntitle: x\nauthor: x\ndate: "2026-02-30"\n---\n',
        "---\ntitle: !thing x\nauthor: x\n---\n",
        "没有元数据\n",
    ],
)
def test_metadata_rejected(front):
    with pytest.raises(NoteError) as error:
        metadata_and_body(Source("note.md", front))
    assert error.value.diagnostic.code == "INPUT_METADATA"


@pytest.mark.parametrize(
    "body,code",
    [
        ("```python\nprint(1)\n", "STRUCTURE_INVALID"),
        ("$$\nx=1\n", "STRUCTURE_INVALID"),
        ("x is $a\n", "STRUCTURE_INVALID"),
        ("::: {#thm-a}\n## T\ntext\n", "STRUCTURE_INVALID"),
        ("```{python}\nraise Exception('must not run')\n```\n", "UNSUPPORTED_SYNTAX"),
        ("[[私有笔记]]\n", "UNSUPPORTED_SYNTAX"),
        ("> [!note] x\n", "UNSUPPORTED_SYNTAX"),
        ("[x][^missing]\n", "FOOTNOTE_INVALID"),
        ("[^unused]: body\n", "FOOTNOTE_INVALID"),
    ],
)
def test_lexical_diagnostics(body, code):
    source = Source("note.md", FRONT + body)
    meta, parsed, offset = metadata_and_body(source)
    doc = Document(Path("note.md"), source, meta, parsed, {}, "")
    with pytest.raises(NoteError) as error:
        lexical_scan(doc, offset)
    assert error.value.diagnostic.code == code
    assert error.value.diagnostic.line >= 1


@pytest.mark.parametrize(
    "body,code",
    [
        ("# A {#sec-a}\n\n@thm-missing\n", "REF_UNDEFINED"),
        ("# A {#sec-a}\n\n# B {#sec-a}\n", "LABEL_DUPLICATE"),
        ("# A\n", "LABEL_INVALID"),
        ("# A {#sec-a .unnumbered}\n", "UNSUPPORTED_SYNTAX"),
        ("# A {#sec-a}\n\n### C {#sec-c}\n", "INPUT_METADATA"),
        ("::: {.proof}\n不是定理的证明\n:::\n", "STRUCTURE_INVALID"),
        ("<script>alert(1)</script>\n", "UNSUPPORTED_SYNTAX"),
        ("$$\n\\input{secret}\n$$\n", "UNSUPPORTED_SYNTAX"),
        ("$$\nx=1\n$$ {#thm-wrong}\n", "LABEL_INVALID"),
        ("![图](missing.png){#fig-missing}\n", "RESOURCE_MISSING"),
        ("![图](../outside.png){#fig-outside}\n", "RESOURCE_PATH"),
        ("![图](https://example.com/a.png){#fig-remote}\n", "RESOURCE_PATH"),
        ("![图](C:/outside.png){#fig-outside}\n", "RESOURCE_PATH"),
    ],
)
def test_structural_diagnostics(tmp_path, quarto, body, code):
    with pytest.raises(NoteError) as error:
        check_text(tmp_path, quarto, body)
    assert error.value.diagnostic.code == code


def test_literals_in_code_are_not_interpreted(tmp_path, quarto):
    code = '@thm-missing [[双链]] $ unmatched \\end{Verbatim}\nprint("never run")'
    doc = check_text(tmp_path, quarto, "```python\n" + code + "\n```\n")
    assert doc.code == [code]
    assert not doc.labels and not doc.references


def test_code_tabs_are_preserved(tmp_path, quarto):
    code = 'if True:\n\tprint("keep the tab")'
    doc = check_text(tmp_path, quarto, "```python\n" + code + "\n```\n")
    assert doc.code == [code]


def test_resource_spaces_and_collision(tmp_path, quarto):
    for folder, color in (("甲 目录", "black"), ("乙目录", "white")):
        directory = tmp_path / folder
        directory.mkdir()
        Image.new("RGB", (20, 10), color).save(directory / "same.png")
    body = (
        "![甲](<甲 目录/same.png>){#fig-a}\n\n"
        "![乙](乙目录/same.png){#fig-b}\n\n![甲再用](<甲 目录/same.png>){#fig-c}\n"
    )
    doc = check_text(tmp_path, quarto, body)
    assert doc.resources[0]["packed"] != doc.resources[1]["packed"]
    assert doc.resources[0]["packed"] == doc.resources[2]["packed"]


def test_corrupt_image(tmp_path, quarto):
    (tmp_path / "bad.jpg").write_bytes(b"not an image")
    with pytest.raises(NoteError) as error:
        check_text(tmp_path, quarto, "![坏图](bad.jpg){#fig-bad}\n")
    assert error.value.diagnostic.code == "RESOURCE_INVALID"


def test_duplicate_label_reports_both_positions(tmp_path, quarto):
    with pytest.raises(NoteError) as error:
        check_text(tmp_path, quarto, "# A {#sec-a}\n\n# B {#sec-a}\n")
    diag = error.value.diagnostic
    assert diag.code == "LABEL_DUPLICATE"
    assert diag.line == 7 and diag.related[0]["line"] == 5


def test_never_overwrites_existing_output(tmp_path):
    sentinel = tmp_path / "user.txt"
    sentinel.write_text("用户编辑结果", encoding="utf-8")
    with pytest.raises(NoteError) as error:
        export_document("unused.md", tmp_path)
    assert error.value.diagnostic.code == "OUTPUT_EXISTS"
    assert sentinel.read_text(encoding="utf-8") == "用户编辑结果"


def test_latex_adaptation_leaves_body_unchanged():
    preamble = "\\theoremstyle{plain}\n\\newtheorem{lemma}{引理}[section]\n"
    body = "\n\\newtheorem{lemma}{正文不可改}[section]\nx^2 >= 0\n"
    tex = adapt_preamble(preamble + "\\begin{document}" + body)
    assert "\\newtheorem{lemma}{引理}\n" in tex
    assert tex.partition("\\begin{document}")[2] == body
    assert "theoremstyle{plain}" not in tex.partition("\\begin{document}")[0]


def test_reference_uses_latex_counter_instead_of_hardcoded_number():
    assert ref_tex("sec-a") == r"\hyperref[sec-a]{第~\ref*{sec-a}~节}"
    assert ref_tex("eq-a") == r"\hyperref[eq-a]{式~(\ref*{eq-a})}"
