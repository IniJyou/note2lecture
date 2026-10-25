"""为 Markdown 数学保留原始正文；解析副本使用受控原子占位符。"""

import json
import re

from .tools import pandoc


def inline_spans(view, source):
    """代码与独立公式已屏蔽；行内公式可软换行，但不能跨越空段或块边界。"""
    spans = []
    delimiters = re.compile(r"(?<!\\)\\[()]|(?<!\\)\$")
    start = None
    closing = None
    for match in delimiters.finditer(view):
        token = match[0]
        if start is None:
            if token == r"\)":
                source.error("STRUCTURE_INVALID", "多余的行内公式结束符。", offset=match.start())
            start = match
            closing = "$" if token == "$" else r"\)"
            continue
        if token != closing:
            # 公式中的其他分隔记号作为数学原文，仍由后续命令与编译检查处理。
            continue
        content = source.text[start.end() : match.start()]
        if not content.strip() or re.search(
            r"\n[ \t]*\n|\n[ \t]*(?:#{1,6}[ \t]|[-+*][ \t]|>[ \t]|```)", content
        ):
            source.error(
                "STRUCTURE_INVALID",
                "行内公式为空或跨越段落/块边界。",
                offset=start.start(),
                hint="行内公式可在同一段内软换行；空行之前必须闭合。",
            )
        spans.append({"start": start.start(), "end": match.end(), "text": content})
        start = None
    if start is not None:
        source.error(
            "STRUCTURE_INVALID",
            "行内公式分隔符未闭合。",
            offset=start.start(),
            hint="检查配对的 $ 或 \\(…\\)；公式结束的 $ 前不要误写反斜线。",
        )
    return spans


def parse_ast(doc, body, quarto):
    """原稿与定位文本不变；占位符经原生 Math 节点解析后恢复全部空格和换行。"""
    from .document import nodes

    offset = len(doc.source.text) - len(body)
    replacements = {}
    boundaries = set()
    for index, span in reversed(list(enumerate(doc.inline_math))):
        token = f"NtwoLInline{doc.sha256[:16]}X{index}X"
        replacements[token] = span
        # 原生解析器不接受结束符紧接数字；仅在解析副本加入可移除的边界。
        boundary = "<!--" + token + "-->"
        boundaries.add(boundary)
        body = (
            body[: span["start"] - offset] + r"\(" + token + r"\)" + boundary
            + body[span["end"] - offset :]
        )
    ast = json.loads(pandoc(quarto, body, doc.reader, "json"))
    for node in nodes(ast["blocks"]):
        if node["t"] == "Math" and node["c"][0]["t"] == "InlineMath":
            span = replacements.pop(node["c"][1], None)
            if span is not None:
                node["c"][1] = span["text"]

    def clean(value):
        if isinstance(value, list):
            kept = []
            for item in value:
                if isinstance(item, dict) and item.get("t") in {"RawInline", "RawBlock"}:
                    fmt, text = item["c"]
                    if fmt == "html" and text in boundaries:
                        boundaries.remove(text)
                        continue
                clean(item)
                kept.append(item)
            value[:] = kept
        elif isinstance(value, dict):
            clean(value.get("c"))

    clean(ast["blocks"])
    if boundaries and not replacements:
        doc.source.error("UNSUPPORTED_SYNTAX", "行内公式解析边界未完整恢复。")
    if replacements:
        span = next(iter(replacements.values()))
        doc.source.error(
            "UNSUPPORTED_SYNTAX",
            "此位置的行内公式不能安全解析为数学节点。",
            offset=span["start"],
        )
    return ast
