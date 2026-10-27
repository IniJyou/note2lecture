"""在原生列表解析前保留源编号；跳号必须由用户显式选择保留，不能静默重排。"""

import re

from .diagnostics import Diagnostic

MARKER = re.compile(r"(?:\(([0-9]+|[A-Za-z]|[ivxlcdmIVXLCDM]+)\)|"
                    r"([0-9]+|[A-Za-z]|[ivxlcdmIVXLCDM]+)[.)]|[-+*])(?:[ \t]+|(?=\n|$))")


def list_insertions(doc, body_offset):
    markers, edits = {}, []
    body = doc.source.text[body_offset:]
    for line in re.finditer(r"(?m)^[ \t]*(?:>[ \t]*)?([^\n]*)", body):
        pos = line.start(1)
        while match := MARKER.match(body, pos):
            raw = match[0].rstrip()
            start = body_offset + match.start()
            if doc.visible[start:start + len(raw)] != raw:
                break  # 代码/数学中的字面编号已在定位副本屏蔽。
            if match[1] or match[2]:
                token = f"<!--NtwoLList{doc.sha256[:16]}X{len(markers)}X-->"
                markers[token] = {"marker": raw, "offset": body_offset + match.start()}
                prefix = " " if match[0] == raw else ""
                # 注释不能挡住条目首行的块记号，否则代码/标题/子列表会退化为正文。
                tail = body[match.end():]
                suffix = ""
                if re.match(r"```|#{1,6}[ \t]|>", tail) or MARKER.match(body, match.end()):
                    line_start = body.rfind("\n", 0, match.start()) + 1
                    continuation = re.sub(r"[^ \t>]", " ", body[line_start:match.end()])
                    suffix = "\n" + continuation
                edits.append((body_offset + match.end(), body_offset + match.end(),
                              prefix + token + suffix))
            pos = match.end()
    return markers, edits


def marker_number(marker, style):
    value = marker.strip("().")
    if style == "Decimal":
        return int(value)
    if style in {"LowerAlpha", "UpperAlpha"}:
        return ord(value.lower()) - ord("a") + 1
    roman = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}
    values = [roman[char] for char in value.lower()]
    return sum(-a if a < b else a for a, b in zip(values, values[1:] + [0]))


def collect_lists(doc, ast, markers):
    from .document import nodes

    def own(value):
        if isinstance(value, list):
            return [token for item in value for token in own(item)]
        if not isinstance(value, dict):
            return []
        if value.get("t") in {"OrderedList", "BulletList"}:
            return []
        if value.get("t") in {"RawInline", "RawBlock"} and value["c"][0] == "html":
            return [markers[value["c"][1]]] if value["c"][1] in markers else []
        return own(value.get("c"))

    doc.list_numbers = {}
    for node in nodes(ast["blocks"]):
        if node["t"] != "OrderedList":
            continue
        records = [own(item) for item in node["c"][1]]
        if any(not item for item in records):
            doc.source.error("LIST_NUMBERING", "无法核验此有序列表的源编号。", block="list")
        records = [item[0] for item in records]
        start, style, _ = node["c"][0]
        values = [marker_number(item["marker"], style["t"]) for item in records]
        automatic = values == list(range(start, start + len(values))) or len(set(values)) == 1
        padded = any(re.match(r"\(?0[0-9]", item["marker"]) for item in records)
        if not automatic or padded:
            if doc.list_numbering != "preserve":
                doc.source.error(
                    "LIST_NUMBERING", "有序列表包含跳号、重复混用或带前导零的题号。",
                    offset=records[0]["offset"], block="list",
                    hint="确认这些是原题号后，使用 --list-numbering preserve 原样保留；"
                         "默认只接受连续编号或统一重复起始编号。",
                    related=[{"marker": item["marker"],
                              "line": doc.source.position(item["offset"])[0]} for item in records],
                )
            line, column = doc.source.position(records[0]["offset"])
            if not any(x.code == "LIST_NUMBERING_PRESERVED" and (x.line, x.column) == (line, column)
                       for x in doc.warnings):
                doc.warnings.append(Diagnostic(
                    "LIST_NUMBERING_PRESERVED", "按显式选项保留此列表的源题号。", doc.path.name,
                    line, column, severity="warning", block="list",
                ))
        doc.list_numbers[id(node)] = records
