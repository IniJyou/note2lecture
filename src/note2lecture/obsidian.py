"""只适配样例覆盖的 Obsidian 语法；不扫描库、不合并关联笔记正文。"""

import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .diagnostics import Diagnostic
from .document import nodes, plain

WIKI = re.compile(r"(?<![\\\[])(!?)\[\[([^\[\]\n]+)\]\]")
CALLOUT = re.compile(r"(?m)^>[ \t]*\[!([A-Za-z]+)\]([+-]?)([^\n]*)")
TITLES = {"note": "笔记", "tip": "提示", "warning": "注意"}


def adapt_obsidian(doc):
    s = doc.source
    tokens = list(WIKI.finditer(doc.visible))
    remaining = list(doc.visible)
    for token in tokens:
        parts = token[2].split("|")
        if len(parts) > 2 or not all(x.strip() for x in parts):
            s.error(
                "UNSUPPORTED_SYNTAX",
                "双链目标与别名必须非空，至多一个分隔符。",
                offset=token.start(),
            )
        if token[1] and len(parts) != 1:
            s.error("UNSUPPORTED_SYNTAX", "图片嵌入暂不接受尺寸或别名。", offset=token.start())
        for i in range(*token.span()):
            remaining[i] = " "
    malformed = re.search(r"(?<!\\)(?:!?\[\[|\]\])", "".join(remaining))
    if malformed:
        s.error("UNSUPPORTED_SYNTAX", "双链未闭合或包含嵌套记号。", offset=malformed.start())
    used = set()
    embed_ids = set()
    headers = {}
    for header in nodes(doc.ast["blocks"]):
        if header["t"] == "Header":
            headers.setdefault(plain(header["c"][2]), []).append(header["c"][1][0])
    doc.obsidian = {"links": [], "embeds": [], "callouts": []}

    for node in list(nodes(doc.ast["blocks"])):
        if node["t"] not in {"Link", "Image"} or "wikilink" not in node["c"][0][1]:
            continue
        c = node["c"]
        target = unquote(c[2][0]).strip()
        embedded = node["t"] == "Image"
        index = next(
            (
                i
                for i, t in enumerate(tokens)
                if i not in used
                and bool(t[1]) == embedded
                and t[2].split("|", 1)[0].strip() == target
            ),
            None,
        )
        if index is None:
            s.error("UNSUPPORTED_SYNTAX", "双链写法无法精确定位。", c[2][0])
        token = tokens[index]
        used.add(index)
        c[0][1].remove("wikilink")
        line, column = s.position(token.start())
        record = {
            "original": s.text[token.start() : token.end()],
            "line": line,
            "column": column,
            "text": plain(c[1]),
            "target": target,
        }
        if target.startswith("#") and not embedded:
            matches = headers.get(target[1:], [])
            if target.startswith("#^"):
                s.error("UNSUPPORTED_SYNTAX", "暂不支持块引用。", offset=token.start())
            if len(matches) != 1:
                code = "REF_AMBIGUOUS" if matches else "REF_UNDEFINED"
                s.error(code, f"同篇标题缺失或不唯一：{target[1:]}", offset=token.start())
            c[2][0] = "#" + matches[0]
            record.update(kind="heading", target=matches[0])
            doc.obsidian["links"].append(record)
            continue
        if (
            not target
            or "\\" in target
            or urlsplit(target).scheme
            or target.startswith("/")
            or ".." in Path(target).parts
            or any(x in target for x in "#?%:")
        ):
            s.error(
                "RESOURCE_PATH", "双链及嵌入仅接受输入目录内的明确相对路径。", offset=token.start()
            )
        path = Path(target)
        if embedded:
            if path.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
                s.error(
                    "UNSUPPORTED_SYNTAX",
                    "只嵌入 PNG/JPEG，不嵌入整篇笔记或 PDF。",
                    offset=token.start(),
                )
            # 没有用户图题时明确使用文件名，不猜测图片含义。图片校验由公共资源检查完成。
            c[1] = [{"t": "Str", "c": path.name}]
            c[2][0] = target
            record.update(caption=path.name, caption_from="filename")
            doc.obsidian["embeds"].append(record)
            embed_ids.add(id(node))
        else:
            if not path.suffix:
                path = path.with_suffix(".md")
            if path.suffix.lower() != ".md":
                s.error(
                    "UNSUPPORTED_SYNTAX", "跨笔记双链仅支持 Markdown 文件。", offset=token.start()
                )
            root = doc.path.parent.resolve()
            resolved = (root / path).resolve()
            if not resolved.is_relative_to(root):
                s.error("RESOURCE_PATH", "关联笔记真实路径越过输入目录。", offset=token.start())
            if not resolved.is_file():
                s.error("REF_UNDEFINED", f"找不到关联笔记：{path.as_posix()}", offset=token.start())
            target = path.as_posix()
            record.update(kind="note", target=target, body_read=False, packaged=False)
            doc.obsidian["links"].append(record)
            suffix = [
                {"t": "Str", "c": "（关联笔记："},
                {"t": "Code", "c": [["", [], []], target]},
                {"t": "Str", "c": "）"},
            ]
            node.update(t="Span", c=[["", [], []], [*c[1], *suffix]])
            doc.warnings.append(
                Diagnostic(
                    "WIKI_NOTE_NOT_PACKAGED",
                    f"关联笔记仅保留名称与路径，不读取正文或打包：{target}",
                    doc.path.name,
                    line,
                    column,
                    severity="warning",
                    block="reference",
                )
            )
    if len(used) != len(tokens):
        token = next(t for i, t in enumerate(tokens) if i not in used)
        s.error("UNSUPPORTED_SYNTAX", "此位置不接受双链或图片嵌入。", offset=token.start())

    # Figure 的图题副本与 Image 同步；普通 Markdown 图片仍由公共规则处理。
    for figure in nodes(doc.ast["blocks"]):
        if figure["t"] == "Figure":
            image = next((x for x in nodes(figure["c"][2]) if x["t"] == "Image"), None)
            if image and id(image) in embed_ids:
                figure["c"][1] = [None, [{"t": "Plain", "c": image["c"][1]}]]

    marks = list(CALLOUT.finditer(doc.visible))
    nested = re.search(r"(?m)^>[ \t]*>", doc.visible)
    if nested:
        s.error("UNSUPPORTED_SYNTAX", "暂不支持嵌套引用或提示框。", offset=nested.start())
    for mark in marks:
        if mark[1].lower() not in TITLES or mark[2]:
            s.error(
                "UNSUPPORTED_SYNTAX",
                "仅支持 note/tip/warning 普通提示框，不支持折叠。",
                offset=mark.start(),
            )
    index = 0
    for node in list(nodes(doc.ast["blocks"])):
        if node["t"] != "BlockQuote" or not node["c"] or node["c"][0]["t"] != "Para":
            continue
        content = node["c"]
        first = content[0]["c"]
        if not first or first[0]["t"] != "Str" or not first[0]["c"].startswith("[!"):
            continue
        if index >= len(marks):
            s.error("UNSUPPORTED_SYNTAX", "提示框必须以独占一行的标记开始。", plain(node))
        mark = marks[index]
        index += 1
        if any(x["t"] not in {"Para", "Plain"} for x in content):
            s.error(
                "UNSUPPORTED_SYNTAX",
                "提示框暂仅支持段落与公式，不支持嵌套或列表。",
                offset=mark.start(),
            )
        split = next((i for i, x in enumerate(first) if x["t"] == "SoftBreak"), len(first))
        title = first[1:split]
        if title and title[0]["t"] == "Space":
            title = title[1:]
        body = [{"t": "Para", "c": first[split + 1 :]}] if split < len(first) else []
        body += content[1:]
        if not body:
            s.error("STRUCTURE_INVALID", "提示框正文不能为空。", offset=mark.start())
        kind = mark[1].lower()
        prefix = TITLES[kind] + ("：" if title else "")
        heading = {
            "t": "Para",
            "c": [
                {
                    "t": "Strong",
                    "c": [
                        {"t": "Str", "c": prefix},
                        *title,
                    ],
                }
            ],
        }
        node.update(t="Div", c=[["", ["n2l-callout"], []], [heading, *body]])
        doc.callout_ids.add(id(node))
        doc.obsidian["callouts"].append(
            {"kind": kind, "title": plain(title), "line": s.position(mark.start())[0]}
        )
    if index != len(marks):
        s.error("UNSUPPORTED_SYNTAX", "提示框位置或结构不受支持。", offset=marks[index].start())
    doc.adaptations.append({"kind": "obsidian", **doc.obsidian})
