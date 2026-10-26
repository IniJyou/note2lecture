"""真实 Markdown 的确定性适配；只改结构，不补写作者或改写正文。"""

import re
from urllib.parse import unquote, urlsplit

from .diagnostics import Diagnostic
from .document import metadata_and_body, nodes, plain
from .math_input import parse_ast

ANCHOR = re.compile(r'^<a\s+id="([A-Za-z][A-Za-z0-9_-]*)"\s*></a>\s*$')
HEADING = re.compile(r"(?m)^(#{1,6})[ \t]+(.+)$")
INDENTED_HEADING = re.compile(r"(?m)^ {1,3}(#{1,6})[ \t]+(.+)$")


def markdown_input(source, fallback_title):
    text = source.text
    adaptations = []
    if text.startswith("---\n"):
        meta, body, offset = metadata_and_body(source)
    else:
        # 只取首个非空行的 H1；其余 H1 仍作为章节，不猜测作者。
        first = re.search(r"\S", text)
        heading = HEADING.match(text, first.start()) if first else None
        title = heading[2] if heading and heading[1] == "#" else fallback_title
        if any(x in title for x in ("\\", "{", "}", "$", "<", ">")):
            source.error("INPUT_METADATA", "文档标题仅支持普通文本。", title)
        meta = {"title": title, "lang": "zh-CN"}
        body, offset = text, 0
        if heading and heading[1] == "#":
            body = " " * heading.end() + text[heading.end() :]
        adaptations.append(
            {
                "kind": "metadata",
                "title_from": "h1" if heading and heading[1] == "#" else "filename",
            }
        )
    return meta, body, offset, adaptations


def adapt_markdown(doc, quarto):
    # HTML 锚点在 Pandoc 之前仅允许完整独占一行的空 a 标签。
    # 预处理重解析保留字符数与换行，诊断位置仍对应只读原稿。
    anchors = []
    chars = list(doc.body)
    body_offset = len(doc.source.text) - len(doc.body)
    pos = body_offset
    for line in doc.body.splitlines(keepends=True):
        hit = ANCHOR.fullmatch(line.rstrip("\n"))
        # visible 已屏蔽代码/数学，避免把示例中的锚点当成结构。
        if hit and "<a" in doc.visible[pos : pos + len(line)]:
            anchors.append((hit[1], pos))
            for index in range(pos - body_offset, pos - body_offset + len(line)):
                if chars[index] != "\n":
                    chars[index] = " "
        pos += len(line)
    if anchors:
        # 复用本次已找到的 Quarto；不另外寻找或读取私人笔记。
        doc.ast = parse_ast(doc, "".join(chars), quarto)
    if doc.profile == "obsidian":
        from .obsidian import adapt_obsidian

        adapt_obsidian(doc)
    # Typora 的独占段落目录占位符映射到模板已有目录，不作为字面正文打印。
    kept = []
    for block in doc.ast["blocks"]:
        if (
            block["t"] == "Para"
            and len(block["c"]) == 1
            and block["c"][0]["t"] == "Str"
            and block["c"][0]["c"].lower() == "[toc]"
        ):
            doc.adaptations.append(
                {"kind": "toc", "from": block["c"][0]["c"], "to": "template-toc"}
            )
        else:
            kept.append(block)
    doc.ast["blocks"] = kept
    headers = [x for x in nodes(doc.ast["blocks"]) if x["t"] == "Header"]
    source_headers = list(HEADING.finditer(doc.body))
    source_headers = [
        x
        for x in source_headers
        if doc.visible[body_offset + x.start(1) : body_offset + x.start(1) + 1] == "#"
    ]
    if len(headers) > len(source_headers):
        # Pandoc 可把列表续行中带缩进的 ATX 解析为标题；只在确有额外标题时匹配。
        # 普通段落里的缩进 # 文本不强行升级；代码/数学中的示例仍由 visible 屏蔽。
        source_headers.extend(
            x for x in INDENTED_HEADING.finditer(doc.body)
            if doc.visible[body_offset + x.start(1) : body_offset + x.start(1) + 1] == "#"
        )
        source_headers.sort(key=lambda x: x.start())
    if len(source_headers) != len(headers):
        doc.source.error("UNSUPPORTED_SYNTAX", "Markdown 模式仅适配 # 形式的标题。")
    shift = headers[0]["c"][0] - 1 if headers else 0
    targets = {}
    header_positions = []
    used = set(re.findall(r"\{#([^} ]+)\}", doc.visible))

    def generated(kind, index, position):
        ident = f"{kind}-n2l-{index}"
        while ident in used:
            ident += "-auto"
        used.add(ident)
        doc.generated_labels[ident] = position
        return ident

    for index, (node, source_header) in enumerate(zip(headers, source_headers), 1):
        c = node["c"]
        position = body_offset + source_header.start(1)
        old = c[1][0]
        if not re.search(r"\{#[^}]+\}", source_header[0]):
            c[1][0] = generated("sec", index, position)
        c[0] -= shift
        if c[0] < 1:
            doc.source.error("STRUCTURE_INVALID", "正文标题层级低于起始层级。", offset=position)
        if old in targets:
            doc.source.error("LABEL_DUPLICATE", f"重复标题锚点：{old}", offset=position)
        targets[old] = c[1][0]
        header_positions.append((position, c[1][0]))
    anchor_names = set()
    for name, position in anchors:
        following = next(((p, ident) for p, ident in header_positions if p > position), None)
        end = doc.source.text.find("\n", position)
        if following is None or doc.source.text[end : following[0]].strip():
            doc.source.error(
                "UNSUPPORTED_SYNTAX", "空 HTML 锚点必须紧接下一标题。", offset=position
            )
        if name in anchor_names or (name in targets and targets[name] != following[1]):
            doc.source.error("LABEL_DUPLICATE", f"重复锚点：{name}", offset=position)
        anchor_names.add(name)
        targets[name] = following[1]
        doc.adaptations.append({"kind": "anchor", "from": name, "to": following[1]})
    figures = [x for x in nodes(doc.ast["blocks"]) if x["t"] == "Figure"]
    for index, figure in enumerate(figures, 1):
        if not figure["c"][0][0]:
            image = next(x for x in nodes(figure) if x["t"] == "Image")
            target = unquote(image["c"][2][0])
            figure["c"][0][0] = generated("fig", index, doc.source.text.find(target))
    for node in list(nodes(doc.ast["blocks"])):
        if node["t"] != "Link":
            continue
        c = node["c"]
        target = c[2][0]
        if target.startswith("#"):
            old = unquote(target[1:])
            if old not in targets:
                doc.source.error("REF_UNDEFINED", f"页内链接目标不存在：{old}", target)
            c[2][0] = "#" + targets[old]
            doc.internal_links.append({"from": old, "to": targets[old]})
        elif not urlsplit(target).scheme and not target.startswith(("/", "\\")):
            # 本地文档引用只显式保留文字和相对路径；不打开、不递归、不打包。
            line, column = doc.source.position(doc.source.text.find(target))
            doc.warnings.append(
                Diagnostic(
                    "LOCAL_LINK_NOT_PACKAGED",
                    f"本地引用仅保留文字与路径，未读取或打包：{target}",
                    doc.path.name,
                    line,
                    column,
                    severity="warning",
                    block="reference",
                    approximate=doc.source.text.count(target) != 1,
                )
            )
            suffix = [{"t": "Str", "c": "（本地引用）"}]
            if plain(c[1]) != target:
                suffix = [
                    {"t": "Str", "c": "（本地引用："},
                    {"t": "Code", "c": [["", [], []], target]},
                    {"t": "Str", "c": "）"},
                ]
            node.update(t="Span", c=[["", [], []], [*c[1], *suffix]])
    doc.adaptations.append(
        {
            "kind": "structure",
            "heading_shift": shift,
            "number_sections": False,
            "generated_labels": list(doc.generated_labels),
            "internal_links": doc.internal_links,
            "uncaptioned_tables": "preserved",
            "author": "only_if_explicit",
            "table_columns": "equal",
            "inline_breaks": "ascii_separators_outside_headings",
            "display_fit": {
                "max_width_ratio": 1.12,
                "text_unchanged": True,
                "overflow": "portrait_outer_relation_wrap",
                "ambiguous_or_still_wide": "error",
                "tagged_equations": "native",
                "numbered_equations": "native",
            },
        }
    )
    if doc.obsidian:
        resolved = {x["from"]: x["to"] for x in doc.internal_links}
        for link in doc.obsidian["links"]:
            if link["kind"] == "heading":
                link["target"] = resolved[link["target"]]
