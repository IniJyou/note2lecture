"""正文的有限字形回退；不改数学、代码、链接目标或源笔记。"""

import re
import unicodedata

TEXT_SYMBOLS = {"①", "②", "③", "∎"}
SYMBOLS = {"✓", "⚠", "❌", "💡"}
GREEK = "".join(
    chr(code) for start, end in ((0x370, 0x400), (0x1F00, 0x2000))
    for code in range(start, end)
    if unicodedata.category(chr(code)).startswith("L")
    and "GREEK" in unicodedata.name(chr(code), "")
)
GLYPHS = re.compile(
    "[" + "".join(sorted(SYMBOLS)) + "][\ufe0e\ufe0f]?|["
    + "".join(sorted(TEXT_SYMBOLS)) + GREEK + "]"
)
GREEK_FONTS = [
    "FreeSerif.otf", "FreeSerifBold.otf", "FreeSerifItalic.otf", "FreeSerifBoldItalic.otf",
]


def glyph_inlines(text):
    """只把已知字符放进受控宏；原始序列作为参数保留。"""
    result, cursor = [], 0
    for hit in GLYPHS.finditer(text):
        if hit.start() > cursor:
            result.append({"t": "Str", "c": text[cursor:hit.start()]})
        char = hit[0][0]
        macro = ("NtwoLTextSymbol" if char in TEXT_SYMBOLS else
                 "NtwoLGreekText" if char in GREEK else "NtwoLUnicodeSymbol")
        tex = "\\" + macro + "{" + hit[0] + "}"
        result.append({"t": "RawInline", "c": ["latex", tex]})
        cursor = hit.end()
    if cursor < len(text):
        result.append({"t": "Str", "c": text[cursor:]})
    return result


def monochrome_text(text):
    """已支持符号的样式选择符不影响黑白字形；其他字符/孤立选择符原样保留。"""
    return re.sub("([" + "".join(sorted(SYMBOLS)) + "])[\ufe0e\ufe0f]", r"\1", text)


def adapt_text_glyphs(value):
    # Code/CodeBlock/Math 的正文不包含 Str 子节点，因此不会被改写。
    if isinstance(value, list):
        for child in value:
            adapt_text_glyphs(child)
    elif isinstance(value, dict):
        if value.get("t") == "Str" and GLYPHS.search(value["c"]):
            value.update(t="Span", c=[["", [], []], glyph_inlines(value["c"])])
        else:
            adapt_text_glyphs(value.get("c"))


def glyph_usage(doc):
    from .document import nodes

    values = [node["c"] for node in nodes(doc.ast["blocks"]) if node["t"] == "Str"]
    values.extend(node["c"] for node in nodes(doc.title_inlines) if node["t"] == "Str")
    # 未走受控书名通道的纯文本元数据也参与依赖与记录。
    if not doc.title_inlines:
        values.append(doc.metadata["title"])
    values.append(str(doc.metadata.get("author", "")))
    counts = {}
    for value in values:
        for hit in GLYPHS.finditer(value):
            counts[hit[0]] = counts.get(hit[0], 0) + 1
    return counts
