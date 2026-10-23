import json

from note2lecture.document import nodes, read_document
from note2lecture.exporter import prepare_ast
from note2lecture.tools import ROOT, pandoc


def test_internal_markers_stay_invisible_after_markdown_roundtrip(tmp_path, quarto):
    doc = read_document(ROOT / "examples/01-mean.md", quarto)
    ast = prepare_ast(doc, tmp_path)
    markdown = pandoc(quarto, json.dumps(ast), "json", "markdown-smart-raw_tex")
    restored = json.loads(pandoc(quarto, markdown, "markdown-smart-latex_macros", "json"))
    found = list(nodes(restored["blocks"]))
    assert any(x["t"] == "RawBlock" and "N2L_SOURCE" in x["c"][1] for x in found)
    assert not any(x["t"] == "Str" and "N2L_SOURCE" in x["c"] for x in found)
