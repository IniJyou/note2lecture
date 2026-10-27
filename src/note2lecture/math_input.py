"""为 Markdown 数学保留原始正文；解析副本使用受控原子占位符。"""

import json
import re

from .tools import pandoc


def inline_spans(view, source, *, hide_display):
    """在代码等屏蔽区之外区分同行独立公式与行内公式，行内公式不能跨空段或块边界。"""
    spans = []
    delimiters = re.compile(r"(?<!\\)\\[()]|(?<!\\)\$")
    start = None
    closing = None
    skip_until = 0
    display_end = re.compile(r"(?<!\\)(?:\\\\)*(\$\$)")
    for match in delimiters.finditer(view):
        if match.start() < skip_until:
            continue
        token = match[0]
        if start is None:
            if token == "$" and view[match.end():match.end() + 1] == "$":
                # 段落/列表说明后的完整同行公式由 Pandoc 原生读取，代码已被屏蔽。
                stop = view.find("\n", match.end() + 1)
                end = display_end.search(view, match.end() + 1, len(view) if stop < 0 else stop)
                if end is None:
                    source.error(
                        "STRUCTURE_INVALID", "段落内的独立公式未在本行闭合。",
                        offset=match.start(), block="math",
                        hint="跨行独立公式请放在单独的内容行；同行公式须配对 $$。",
                    )
                if not source.text[match.end() + 1:end.start(1)].strip():
                    source.error(
                        "STRUCTURE_INVALID", "独立公式为空。", offset=match.start(), block="math",
                    )
                hide_display(match.start(), end.end(1))
                skip_until = end.end(1)
                continue
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
    edits = []
    for index, span in reversed(list(enumerate([*doc.inline_math, *doc.title_math_spans]))):
        if body[span["start"] - offset:span["end"] - offset] != doc.source.text[
            span["start"]:span["end"]
        ]:
            continue  # 书名在正文副本中已移出；独立原稿复查时才恢复对应行内公式。
        token = f"NtwoLInline{doc.sha256[:16]}X{index}X"
        replacements[token] = span
        # 原生解析器不接受结束符紧接数字；仅在解析副本加入可移除的边界。
        boundary = "<!--" + token + "-->"
        boundaries.add(boundary)
        edits.append((span["start"], span["end"], r"\(" + token + r"\)" + boundary))
    from .list_input import collect_lists, list_insertions

    markers, list_edits = list_insertions(doc, offset)
    edits.extend(list_edits)
    blank_tokens = {}
    for blank in doc.math_blank_lines:
        blank_tokens[blank["token"]] = blank["offset"]
        edits.append((blank["offset"], blank["offset"], blank["token"]))
    for start, end, replacement in sorted(edits, reverse=True):
        body = body[:start - offset] + replacement + body[end - offset:]
    ast = json.loads(pandoc(quarto, body, doc.reader, "json"))
    collect_lists(doc, ast, markers)
    for node in nodes(ast["blocks"]):
        if node["t"] == "Math":
            for token in list(blank_tokens):
                if token in node["c"][1]:
                    if node["c"][0]["t"] != "DisplayMath" or node["c"][1].count(token) != 1:
                        doc.source.error("STRUCTURE_INVALID", "公式内部空白标记未能安全恢复。",
                                         offset=blank_tokens[token], block="math")
                    node["c"][1] = node["c"][1].replace(token, "")
                    del blank_tokens[token]
        if node["t"] == "Math" and node["c"][0]["t"] == "InlineMath":
            span = replacements.pop(node["c"][1], None)
            if span is not None:
                node["c"][1] = span["text"]
    if blank_tokens:
        doc.source.error("STRUCTURE_INVALID", "后端未将带空行的内容解析为完整独立公式。",
                         offset=next(iter(blank_tokens.values())), block="math")

    def clean(value):
        if isinstance(value, list):
            kept = []
            for item in value:
                if isinstance(item, dict) and item.get("t") in {"RawInline", "RawBlock"}:
                    fmt, text = item["c"]
                    if fmt == "html" and (text in boundaries or text in markers):
                        boundaries.discard(text)
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
