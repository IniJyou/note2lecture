"""H1 书名的受控行内排版；只允许文档内容，不透传任意 LaTeX 元数据。"""

import copy
import json

from .diagnostics import NoteError, Source
from .text_glyphs import GLYPHS, adapt_text_glyphs
from .tools import pandoc


def bookmark_text(text):
    """书签只显示文本，TeX 特殊字符作字面转义。"""
    escapes = {
        "\\": r"\textbackslash{}", "{": r"\{", "}": r"\}", "$": r"\$",
        "&": r"\&", "#": r"\#", "%": r"\%", "_": r"\_",
        "^": r"\textasciicircum{}", "~": r"\textasciitilde{}",
    }
    return "".join(escapes.get(char, char) for char in " ".join(text.split()))


def literal_metadata_tex(text, quarto):
    """YAML 的书名/作者仍是字面文本，不借字形回退启用 Markdown 或 TeX。"""
    from .text_glyphs import glyph_inlines

    ast = json.loads(pandoc(quarto, "", "markdown", "json"))
    ast["blocks"] = [{"t": "Plain", "c": glyph_inlines(text)}]
    display = pandoc(quarto, json.dumps(ast), "json", "latex").rstrip("\n")
    return r"\texorpdfstring{" + display + "}{" + bookmark_text(text) + "}"


def prepare_title(doc, quarto):
    from .document import (
        Document,
        lexical_scan,
        nodes,
        plain,
        validate_math,
        validate_math_commands,
    )
    from .math_input import parse_ast

    metadata = next((item for item in doc.adaptations if item["kind"] == "metadata"), {})
    doc.title_range = metadata.get("title_range", [])
    title = doc.metadata["title"]
    special = any(char in title for char in ("\\", "$", "<", ">", "{"))
    if not doc.title_range and GLYPHS.search(title):
        doc.title_token = "NtwoLTitle" + doc.sha256[:20]
        doc.title_tex = literal_metadata_tex(title, quarto)
        return
    if not doc.title_range or not (special or GLYPHS.search(title)):
        return
    start = metadata["title_text_offset"]
    temp = Document(doc.path, Source(doc.path.name, title), {}, title, {}, doc.sha256,
                    profile=doc.profile)
    try:
        lexical_scan(temp, 0)
        temp.ast = parse_ast(temp, title, quarto)
        blocks = temp.ast["blocks"]
        if len(blocks) != 1 or blocks[0]["t"] not in {"Plain", "Para"}:
            temp.source.error("INPUT_METADATA", "书名仅接受文本、行内数学及基础行内样式。")
        allowed = {"Str", "Space", "Emph", "Strong", "Code", "Math", "InlineMath"}
        for node in nodes(blocks):
            if node["t"] in {"Plain", "Para"}:
                continue
            if node["t"] not in allowed or (
                node["t"] == "Math" and node["c"][0]["t"] != "InlineMath"
            ):
                temp.source.error("INPUT_METADATA", "书名不接受独立公式、链接或原始指令。")
        validate_math_commands(temp)
        for node in nodes(blocks):
            if node["t"] == "Math":
                validate_math(temp, node)
    except NoteError as exc:
        diagnostic = exc.diagnostic
        related = diagnostic.related
        if related:
            mapped = []
            for item in related:
                line, column = doc.source.position(start + item["column"] - 1)
                mapped.append(dict(item, line=line, column=column))
            related = mapped
        doc.source.error(
            diagnostic.code, diagnostic.message, offset=start + diagnostic.column - 1,
            block=diagnostic.block, hint=diagnostic.hint, related=related,
        )
    doc.title_inlines = blocks[0]["c"]
    doc.title_math = temp.math
    doc.math.extend(temp.math)
    doc.title_math_spans = [
        dict(span, start=start + span["start"], end=start + span["end"])
        for span in temp.inline_math
    ]
    doc.title_token = "NtwoLTitle" + doc.sha256[:20]
    title_ast = {
        "pandoc-api-version": temp.ast["pandoc-api-version"], "meta": {},
        "blocks": [{"t": "Plain", "c": copy.deepcopy(doc.title_inlines)}],
    }
    for node in nodes(title_ast["blocks"]):
        if node["t"] == "Math":
            node.update(t="RawInline", c=["latex", r"\(" + node["c"][1] + r"\)"])
    adapt_text_glyphs(title_ast["blocks"])
    display = pandoc(quarto, json.dumps(title_ast), "json", "latex").rstrip("\n")
    doc.title_tex = (r"\texorpdfstring{" + display + "}{"
                     + bookmark_text(plain(doc.title_inlines)) + "}")
    doc.adaptations.append({"kind": "math_title", "math_count": len(temp.math),
                            "bookmark": "plain_source_text", "source_unchanged": True})
