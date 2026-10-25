"""源位置扫描与 Pandoc AST 检查分工：扫描定位，结构判断以 AST 为准。"""

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from urllib.parse import unquote, urlsplit

import yaml
from PIL import Image, UnidentifiedImageError

from .diagnostics import Source
from .tools import pandoc

LABEL = re.compile(r"^(sec|eq|fig|tbl|def|thm|lem|exm)-[a-z0-9]+(?:-[a-z0-9]+)*$")
ENV = {"def", "thm", "lem", "exm"}
# 首版是明确的数学命令子集；既不猜写未知宏，也不允许文件/执行命令混入数学。
MATH_COMMANDS = set(
    """
frac dfrac tfrac sqrt sum prod int iint lim min max inf sup log ln exp sin cos tan
mathbb mathrm mathbf mathit mathcal mathsf mathtt operatorname text textrm boldsymbol
bar overline underline hat widehat tilde widetilde vec dot ddot top perp prime
in notin ni subset subseteq supset supseteq cup cap emptyset varnothing setminus
ne neq ge geq le leq approx sim simeq equiv propto ll gg to mapsto rightarrow
leftarrow Rightarrow Leftarrow Leftrightarrow iff implies forall exists neg land lor
alpha beta gamma delta epsilon varepsilon zeta eta theta vartheta iota kappa lambda
mu nu xi pi varpi rho varrho sigma varsigma tau upsilon phi varphi chi psi omega
Gamma Delta Theta Lambda Xi Pi Sigma Upsilon Phi Psi Omega
times cdot div pm mp otimes oplus circ ast star dots ldots cdots vdots ddots
infty partial nabla ell Re Im det trace tr rank diag mod bmod pmod binom dbinom
left right middle big Big bigg Bigg langle rangle lvert rvert lVert rVert vert Vert
lbrace rbrace quad qquad hspace begin end underbrace overbrace underset overset
substack limits nolimits displaystyle textstyle scriptstyle scriptscriptstyle
nonumber notag
""".split()
)
MATH_ENVS = {
    "aligned",
    "gathered",
    "matrix",
    "pmatrix",
    "bmatrix",
    "Bmatrix",
    "vmatrix",
    "Vmatrix",
    "cases",
    "smallmatrix",
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def nodes(value):
    if isinstance(value, list):
        for item in value:
            yield from nodes(item)
    elif isinstance(value, dict):
        if "t" in value:
            yield value
        yield from nodes(value.get("c"))


def plain(value):
    if isinstance(value, list):
        return "".join(plain(x) for x in value)
    if not isinstance(value, dict):
        return ""
    if value["t"] == "Str":
        return value["c"]
    if value["t"] in {"Space", "SoftBreak", "LineBreak"}:
        return " "
    if value["t"] in {"Code", "Math"}:
        return value["c"][1]
    return plain(value.get("c"))


@dataclass
class Document:
    path: Path
    source: Source
    metadata: dict
    body: str
    ast: dict
    sha256: str
    labels: dict = field(default_factory=dict)
    references: list = field(default_factory=list)
    resources: list = field(default_factory=list)
    code: list = field(default_factory=list)
    math: list = field(default_factory=list)
    source_map: list = field(default_factory=list)
    visible: str = ""
    profile: str = "strict"
    generated_labels: dict = field(default_factory=dict)
    adaptations: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    internal_links: list = field(default_factory=list)
    obsidian: dict = field(default_factory=dict)
    callout_ids: set = field(default_factory=set)
    inline_math: list = field(default_factory=list)

    @property
    def markdown_mode(self):
        return self.profile in {"markdown", "obsidian"}

    @property
    def reader(self):
        base = "markdown-smart-latex_macros"
        if self.markdown_mode:
            base += "+tex_math_single_backslash"
        return base + ("+wikilinks_title_after_pipe" if self.profile == "obsidian" else "")


def metadata_and_body(source):
    text = source.text
    match = re.match(r"\A---\n(.*?)\n---(?:\n|$)", text, re.S)
    if not match:
        source.error("INPUT_METADATA", "文档必须以 YAML 元数据开始。")
    front = match[1]
    try:
        for token in yaml.scan(front):
            if isinstance(
                token, (yaml.tokens.AliasToken, yaml.tokens.AnchorToken, yaml.tokens.TagToken)
            ):
                source.error(
                    "INPUT_METADATA",
                    "不支持 YAML 别名、锚点或标签。",
                    offset=4 + token.start_mark.index,
                )
        tree = yaml.compose(front, Loader=yaml.SafeLoader)
        if not isinstance(tree, yaml.MappingNode):
            source.error("INPUT_METADATA", "元数据必须是字段映射。")
        keys = set()
        for key, value in tree.value:
            if key.value in keys or key.value not in {"title", "author", "date", "lang"}:
                source.error(
                    "INPUT_METADATA",
                    f"重复或不支持的元数据字段：{key.value}",
                    offset=4 + key.start_mark.index,
                )
            keys.add(key.value)
            if not isinstance(value, yaml.ScalarNode) or value.tag != "tag:yaml.org,2002:str":
                source.error(
                    "INPUT_METADATA",
                    f"{key.value} 必须为字符串。",
                    offset=4 + value.start_mark.index,
                )
        meta = yaml.safe_load(front)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        source.error("INPUT_METADATA", "YAML 格式错误。", offset=4 + (mark.index if mark else 0))
    for required in ("title", "author"):
        if not meta.get(required, "").strip():
            source.error("INPUT_METADATA", f"缺少非空字段：{required}")
    for key, value in meta.items():
        if re.search(r"[\n\r\\{}<>`$]", value):
            source.error("INPUT_METADATA", f"{key} 仅接受单行普通文本，不接受排版指令。", key)
    if meta.get("lang", "zh-CN") != "zh-CN":
        source.error("INPUT_METADATA", "首版仅支持 lang: zh-CN。", "lang")
    if "date" in meta:
        try:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", meta["date"]):
                raise ValueError
            date.fromisoformat(meta["date"])
        except ValueError:
            source.error("INPUT_METADATA", "日期应为有效的 YYYY-MM-DD 字符串。", "date")
    meta.setdefault("lang", "zh-CN")
    return meta, text[match.end() :], match.end()


def lexical_scan(doc, body_offset):
    """只对明确分隔符做状态扫描；保护代码/数学后再检查扩展记号。"""
    s = doc.source
    text = s.text
    mask = list(text)

    def hide(a, b):
        for i in range(a, b):
            if mask[i] != "\n":
                mask[i] = " "

    hide(0, body_offset)
    fence = math_start = None
    math_end = "$$"
    divs = []
    offset = body_offset
    for line in doc.body.splitlines(keepends=True):
        stripped = line.rstrip("\n")
        # 列表续行中的围栏会缩进；只屏蔽记号，原文和缩进都交给 Pandoc 保留。
        if doc.markdown_mode:
            stripped = stripped.strip(" \t")
        if fence is not None:
            hide(offset, offset + len(line))
            if stripped == "```":
                fence = None
        elif math_start is not None:
            hide(offset, offset + len(line))
            if (math_end == "$$" and re.fullmatch(r"\$\$(?: \{#[-a-z0-9]+\})?", stripped)) or (
                math_end == r"\]" and stripped == math_end
            ):
                math_start = None
        elif stripped.startswith("```"):
            if stripped not in {"```", "```python", "```text"}:
                s.error(
                    "UNSUPPORTED_SYNTAX",
                    "仅接受普通 python/text 代码围栏，不执行代码。",
                    offset=offset,
                    block="code",
                )
            fence = offset
            hide(offset, offset + len(line))
        elif stripped == "$$" or (doc.markdown_mode and stripped == r"\["):
            math_start = offset
            math_end = "$$" if stripped == "$$" else r"\]"
            hide(offset, offset + len(line))
        elif stripped.startswith(":::"):
            if stripped == ":::":
                if not divs:
                    s.error("STRUCTURE_INVALID", "多余的数学环境结束围栏。", offset=offset)
                divs.pop()
            else:
                if divs:
                    s.error("UNSUPPORTED_SYNTAX", "首版不支持嵌套数学环境。", offset=offset)
                divs.append(offset)
        offset += len(line)
    for start, kind in ((fence, "代码围栏"), (math_start, "独立公式")):
        if start is not None:
            s.error("STRUCTURE_INVALID", f"{kind}未闭合。", offset=start)
    if divs:
        s.error("STRUCTURE_INVALID", "数学环境未闭合。", offset=divs[0])
    view = "".join(mask)
    for match in re.finditer(r"(`+)([^\n]*?)\1", view):
        hide(*match.span())
    view = "".join(mask)
    if doc.markdown_mode:
        from .math_input import inline_spans

        doc.inline_math = inline_spans(view, s)
        for span in doc.inline_math:
            hide(span["start"], span["end"])
    else:
        for match in re.finditer(r"(?<!\\)\$([^\n$]+?)(?<!\\)\$", view):
            hide(*match.span())
    view = "".join(mask)
    unmatched = re.search(r"(?<!\\)\$", view)
    if unmatched:
        s.error(
            "STRUCTURE_INVALID", "行内公式分隔符未闭合或写法不受支持。", offset=unmatched.start()
        )
    if doc.markdown_mode:
        unmatched = re.search(r"(?<!\\)\\[()[\]]", view)
        if unmatched:
            s.error(
                "STRUCTURE_INVALID",
                "反斜线公式分隔符未闭合或写法不受支持。",
                offset=unmatched.start(),
            )
    unsupported = r"\{\{[<%]|\\[\[(]|(?m:^[ \t]*- \[[ xX]\])"
    if doc.profile != "obsidian":
        unsupported = r"\[\[|!\[\[|\[![A-Za-z]+\]|" + unsupported
    bad = re.search(unsupported, view)
    if bad:
        s.error("UNSUPPORTED_SYNTAX", f"不支持的记号：{bad[0]}", offset=bad.start())
    # 手写 URI 编码与解析器产生的 %20 区分；仅检查图片目标。
    for match in re.finditer(r"!\[[^\]\n]*\]\((<?[^)\n]+>?)\)", view):
        if "%" in match[1]:
            s.error("RESOURCE_PATH", "源图片路径不支持手写百分号编码。", offset=match.start())
    foot_defs = list(re.finditer(r"(?m)^\[\^([^\]]+)\]:", view))
    seen = set()
    for match in foot_defs:
        key = match[1]
        if key in seen:
            s.error("FOOTNOTE_INVALID", f"重复脚注定义：{key}", offset=match.start())
        seen.add(key)
    uses = re.findall(r"\[\^([^\]]+)\](?!:)", view)
    if set(uses) != seen:
        s.error("FOOTNOTE_INVALID", "脚注引用与定义不一致。", "[^")
    doc.visible = view


def read_document(path, quarto, profile="strict"):
    path = Path(path).absolute()
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8-sig").replace("\r\n", "\n")
    except UnicodeDecodeError:
        Source(path.name, "").error("INPUT_ENCODING", "输入不是有效的 UTF-8。")
    source = Source(path.name, text)
    if path.suffix.lower() != ".md":
        source.error("UNSUPPORTED_SYNTAX", "入口必须为单篇 .md 文件。")
    if profile not in {"strict", "markdown", "obsidian"}:
        source.error("INPUT_METADATA", "未知输入模式。")
    if profile in {"markdown", "obsidian"}:
        from .markdown import markdown_input

        meta, body, offset, adaptations = markdown_input(source, path.stem)
    else:
        meta, body, offset = metadata_and_body(source)
        adaptations = []
    doc = Document(path, source, meta, body, {}, digest(raw), profile=profile)
    doc.adaptations = adaptations
    lexical_scan(doc, offset)
    if doc.markdown_mode:
        from .math_input import parse_ast

        doc.ast = parse_ast(doc, body, quarto)
    else:
        doc.ast = json.loads(pandoc(quarto, body, doc.reader, "json"))
    if doc.markdown_mode:
        from .markdown import adapt_markdown

        adapt_markdown(doc, quarto)
    validate_ast(doc)
    return doc


def validate_math(doc, node):
    text = node["c"][1]
    s = doc.source
    # 两个反斜线是矩阵换行，不能把 \\\\x 的第二个反斜线误判为命令。
    for command in re.finditer(r"(?<!\\)(?:\\\\)*\\([A-Za-z]+)", text):
        extra = {
            "longrightarrow", "Longrightarrow", "mid", "odot", "dim", "arcsin", "arccos",
            "arctan", "cot", "boxed", "bigl", "bigr", "Bigl", "Bigr", "uparrow", "downarrow",
            "therefore", "Longleftrightarrow", "square", "tag", "iiint", "oiint",
        }
        if command[1] not in MATH_COMMANDS | (extra if doc.markdown_mode else set()):
            s.error(
                "UNSUPPORTED_SYNTAX", f"不支持的数学命令：{command[0]}", command[0], block="math"
            )
    stack = []
    for match in re.finditer(r"\\(begin|end)\{([^}]+)\}", text):
        if match[2] not in MATH_ENVS:
            s.error("UNSUPPORTED_SYNTAX", f"不支持的数学子环境：{match[2]}", match[0])
        if match[1] == "begin":
            stack.append(match[2])
        elif not stack or stack.pop() != match[2]:
            s.error("STRUCTURE_INVALID", "数学子环境未正确配对。", match[0])
    if stack:
        s.error("STRUCTURE_INVALID", "数学子环境未闭合。", text)
    if re.search(r"\\tag\b", text):
        if node["c"][0]["t"] != "DisplayMath":
            s.error("UNSUPPORTED_SYNTAX", "手写公式编号仅支持独立公式。", text, block="math")
        tags = re.findall(r"\\tag\{([A-Za-z0-9.()-]+)\}", text)
        if len(tags) != 1 or len(re.findall(r"\\tag\b", text)) != 1:
            s.error("UNSUPPORTED_SYNTAX", "每个独立公式仅支持一个简单的 \\tag{编号}。", text)
    doc.math.append({"kind": node["c"][0]["t"], "text": text, "sha256": digest(text.encode())})


def validate_ast(doc):
    s = doc.source
    previous_heading = 0
    allowed = {
        "Para",
        "Plain",
        "Str",
        "Space",
        "SoftBreak",
        "Emph",
        "Strong",
        "Code",
        "Header",
        "CodeBlock",
        "Math",
        "Div",
        "BulletList",
        "OrderedList",
        "BlockQuote",
        "Note",
        "Table",
        "Figure",
        "Image",
        "Link",
        "Cite",
    }
    if doc.markdown_mode:
        allowed.update({"HorizontalRule", "LineBreak"})

    def label(identifier, kind):
        if not LABEL.fullmatch(identifier) or identifier.split("-", 1)[0] != kind:
            s.error(
                "LABEL_INVALID",
                f"缺少标签或标签类型不符：{identifier or kind}",
                identifier,
                block=kind,
            )
        occurrence = re.search(
            r"\{#[^}\n]*\b" + re.escape(identifier) + r"\b[^}\n]*\}",
            doc.visible if kind != "eq" else s.text,
        )
        generated = doc.generated_labels.get(identifier)
        if not occurrence and generated is None:
            s.error("LABEL_INVALID", f"必须显式声明标签：{identifier}", identifier)
        label_offset = generated if generated is not None else occurrence.start()
        line, column = s.position(label_offset)
        if identifier in doc.labels:
            old = doc.labels[identifier]
            occurrences = list(re.finditer(re.escape("{#" + identifier + "}"), s.text))
            second = occurrences[1].start() if len(occurrences) > 1 else label_offset
            s.error(
                "LABEL_DUPLICATE",
                f"重复标签：{identifier}",
                identifier,
                offset=second,
                related=[old],
            )
        doc.labels[identifier] = {"kind": kind, "line": line, "column": column}

    def walk(value, in_env=False, list_depth=0, in_figure=False):
        nonlocal previous_heading
        if isinstance(value, list):
            for child in value:
                walk(child, in_env, list_depth, in_figure)
            return
        if not isinstance(value, dict) or "t" not in value:
            return
        kind, c = value["t"], value.get("c")
        if kind in {
            "Decimal",
            "Period",
            "OneParen",
            "TwoParens",
            "AlignDefault",
            "AlignLeft",
            "AlignRight",
            "AlignCenter",
            "ColWidthDefault",
            "ColWidth",
        }:
            return  # Pandoc 的列表/列宽枚举不是正文节点。
        if kind == "Span" and doc.markdown_mode and c[0] == ["", [], []]:
            walk(c[1], in_env, list_depth, in_figure)
            return
        if kind not in allowed:
            needle = c[1] if kind in {"RawInline", "RawBlock"} else plain(value)
            s.error("UNSUPPORTED_SYNTAX", f"不支持的文档结构：{kind}", needle, block=kind)
        if kind == "Header":
            if c[1][1] or c[1][2]:
                s.error("UNSUPPORTED_SYNTAX", "标题不接受自定义样式属性。", plain(c[2]))
            if not in_env:
                if c[0] > 3 or c[0] > previous_heading + 1:
                    s.error("INPUT_METADATA", "标题层级过深或跳级。", plain(c[2]), block="heading")
                previous_heading = c[0]
                label(c[1][0], "sec")
        elif kind == "Div":
            ident, classes, attrs = c[0]
            if id(value) in doc.callout_ids:
                if any(x["t"] not in {"Para", "Plain"} for x in c[1]):
                    s.error("UNSUPPORTED_SYNTAX", "提示框暂仅支持段落与公式。", plain(c[1]))
            elif classes == ["proof"] and not ident and not attrs:
                if any(x["t"] not in {"Para", "Plain"} for x in c[1]):
                    s.error("UNSUPPORTED_SYNTAX", "证明内仅支持段落与公式。", plain(c[1]))
            elif ident.split("-", 1)[0] in ENV and not classes and not attrs:
                label(ident, ident.split("-", 1)[0])
                content = c[1]
                if not content or content[0]["t"] != "Header" or not plain(content[0]["c"][2]):
                    s.error("STRUCTURE_INVALID", "数学环境必须以非空 ## 标题开始。", ident)
                if content[0]["c"][0] != 2:
                    s.error("STRUCTURE_INVALID", "数学环境题头必须使用 ##。", ident)
                if any(x["t"] not in {"Para", "Plain"} for x in content[1:]):
                    s.error("UNSUPPORTED_SYNTAX", "数学环境内仅支持段落与公式。", ident)
                in_env = True
            else:
                s.error("UNSUPPORTED_SYNTAX", "不支持的 div 或属性。", ident or "::: {")
        elif kind in {"BulletList", "OrderedList"}:
            list_depth += 1
            limit = 4 if doc.markdown_mode else 2
            if list_depth > limit:
                s.error("UNSUPPORTED_SYNTAX", f"列表最多{limit}层。", plain(value))
            items = c if kind == "BulletList" else c[1]
            if kind == "OrderedList":
                styles = {"Period", "OneParen", "TwoParens"} if doc.markdown_mode else {"Period"}
                if c[0][1]["t"] != "Decimal" or c[0][2]["t"] not in styles:
                    s.error("UNSUPPORTED_SYNTAX", "不支持此有序列表编号形式。", plain(value))
            for item in items:
                if doc.markdown_mode:
                    if not item or item[0]["t"] not in {"Plain", "Para"} or any(
                        x["t"] not in {"Plain", "Para", "BulletList", "OrderedList"} for x in item
                    ):
                        s.error(
                            "UNSUPPORTED_SYNTAX",
                            "列表内仅支持段落、公式与最多四层列表。",
                            plain(value),
                        )
                    continue
                if (
                    not item
                    or item[0]["t"] not in {"Plain", "Para"}
                    or len(item) > 2
                    or (len(item) == 2 and item[1]["t"] not in {"BulletList", "OrderedList"})
                ):
                    s.error("UNSUPPORTED_SYNTAX", "不支持多段复杂列表。", plain(value))
        elif kind == "Note":
            if len(c) != 1 or c[0]["t"] not in {"Para", "Plain"}:
                s.error("UNSUPPORTED_SYNTAX", "首版仅支持单段脚注。", "[^")
        elif kind == "BlockQuote":
            if any(x["t"] not in {"Para", "Plain"} for x in c):
                s.error("UNSUPPORTED_SYNTAX", "首版仅支持普通单层引用段。", ">")
        elif kind == "CodeBlock":
            ident, classes, attrs = c[0]
            if ident or attrs or classes not in ([], ["python"], ["text"]):
                s.error("UNSUPPORTED_SYNTAX", "不支持的代码块属性。", c[1], block="code")
            doc.code.append(c[1])
            return
        elif kind == "Code":
            return
        elif kind == "Math":
            validate_math(doc, value)
            return
        elif kind == "Figure":
            if c[0][1] or c[0][2]:
                s.error("UNSUPPORTED_SYNTAX", "图不接受自定义样式属性。", c[0][0])
            label(c[0][0], "fig")
            in_figure = True
        elif kind == "Image":
            if not in_figure:
                s.error("UNSUPPORTED_SYNTAX", "图片必须独占段落并带图题及标签。", c[2][0])
            if not plain(c[1]).strip():
                s.error("STRUCTURE_INVALID", "图题不能为空。", c[2][0])
            if c[0][1] or c[0][2]:
                s.error("UNSUPPORTED_SYNTAX", "输入图片不接受自定义样式属性。", c[2][0])
            validate_resource(doc, value)
        elif kind == "Table":
            ident = c[0][0]
            if c[0][1] or c[0][2]:
                s.error("UNSUPPORTED_SYNTAX", "表格不接受自定义样式属性。", ident)
            if not ident:
                # 兼容旧 Pandoc 将标签保留在表题文本的 AST。
                hit = re.search(r"\{#(tbl-[a-z0-9-]+)\}", plain(c[1][1]))
                ident = hit[1] if hit else ""
            if ident or doc.profile == "strict":
                label(ident, "tbl")
            if c[5][1] or len(c[4]) != 1 or c[4][0][2]:
                s.error("UNSUPPORTED_SYNTAX", "仅支持单表头基础表格。", ident)
            for row in [*c[3][1], *c[4][0][3]]:
                for cell in row[1]:
                    if (
                        cell[2:4] != [1, 1]
                        or len(cell[4]) != 1
                        or cell[4][0]["t"] not in {"Plain", "Para"}
                        or (
                            doc.profile == "strict"
                            and any(x["t"] == "Code" for x in nodes(cell[4]))
                        )
                    ):
                        s.error("UNSUPPORTED_SYNTAX", "不支持合并或多块单元格。", ident)
        elif kind == "Link":
            parsed = urlsplit(c[2][0])
            if doc.markdown_mode and c[2][0].startswith("#"):
                if c[2][0][1:] not in doc.generated_labels and not re.search(
                    r"\{#" + re.escape(c[2][0][1:]) + r"\}", doc.visible
                ):
                    s.error("REF_UNDEFINED", "页内链接目标不存在。", c[2][0])
            elif parsed.scheme not in {"http", "https"} or not parsed.netloc:
                s.error("UNSUPPORTED_SYNTAX", "普通链接仅接受 http/https 外链。", c[2][0])
        elif kind == "Cite":
            if len(c[0]) != 1 or c[0][0]["citationPrefix"] or c[0][0]["citationSuffix"]:
                s.error("UNSUPPORTED_SYNTAX", "首版仅支持单目标 @标签 引用。", plain(c[1]))
            ident = c[0][0]["citationId"]
            if doc.markdown_mode and ident.startswith("sec-"):
                s.error(
                    "UNSUPPORTED_SYNTAX",
                    "Markdown 模式不生成章节号，请用 [说明](#锚点) 跳转。",
                    "@" + ident,
                    block="reference",
                )
            doc.references.append(ident)
            return
        elif kind == "Str":
            hit = re.fullmatch(r"\{#(eq-[a-z0-9-]+)\}", c)
            if hit:
                label(hit[1], "eq")
            elif re.fullmatch(r"\{#[^}]+\}", c):
                # 表题标签可能由旧 Pandoc 保留为文本，在 Table 分支已记录。
                if c[2:-1] not in doc.labels:
                    s.error("LABEL_INVALID", "标签类型或位置不符。", c)
        walk(c, in_env, list_depth, in_figure)

    # 遍历 AST 的结构数组，非 AST 字典（如引用元数据）不会误作正文。
    def walk_container(value, in_env=False, list_depth=0, in_figure=False):
        if isinstance(value, list):
            for item in value:
                if isinstance(item, list):
                    walk_container(item, in_env, list_depth, in_figure)
                else:
                    walk(item, in_env, list_depth, in_figure)

    # walk 的数组分支已经能深入结构数组；保留同一遍历入口。
    walk_container(doc.ast["blocks"])
    for ident in doc.references:
        if ident not in doc.labels:
            s.error("REF_UNDEFINED", f"引用目标不存在：{ident}", "@" + ident, block="reference")
    # 对源中的显式声明再检查一次，避免 Pandoc 对重复标题 ID 的自动消歧掩盖错误。
    seen = {}
    protected_labels = set(doc.labels)
    for match in re.finditer(r"\{#([a-zA-Z0-9-]+)\}", doc.visible):
        ident = match[1]
        if ident in seen:
            s.error(
                "LABEL_DUPLICATE",
                f"重复标签：{ident}",
                offset=match.start(),
                related=[{"line": s.position(seen[ident])[0]}],
            )
        seen[ident] = match.start()
        if ident not in protected_labels:
            s.error("LABEL_INVALID", f"标签不在支持的结构上：{ident}", offset=match.start())
    validate_proofs(doc, doc.ast["blocks"])


def validate_proofs(doc, blocks):
    previous = None
    for block in blocks:
        if block["t"] == "Div":
            attr, content = block["c"]
            if "proof" in attr[1] and previous not in {"thm", "lem"}:
                doc.source.error(
                    "STRUCTURE_INVALID",
                    "证明必须紧跟一个定理或引理。",
                    plain(content),
                    block="proof",
                )
            previous = attr[0].split("-", 1)[0]
        else:
            previous = None


def validate_resource(doc, node):
    target = node["c"][2][0]
    path = unquote(target)
    s = doc.source
    if (
        "\\" in path
        or re.match(r"^[A-Za-z]:", path)
        or urlsplit(path).scheme
        or path.startswith("/")
        or ".." in Path(path).parts
        or "?" in path
        or "#" in path
    ):
        s.error("RESOURCE_PATH", f"图片路径必须位于输入目录内：{path}", path, block="image")
    root = doc.path.parent.resolve()
    resolved = (root / path).resolve()
    if not resolved.is_relative_to(root):
        s.error("RESOURCE_PATH", f"图片真实路径越过输入目录：{path}", path, block="image")
    if not resolved.is_file():
        s.error("RESOURCE_MISSING", f"找不到图片：{path}", path, block="image")
    if resolved.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
        s.error("RESOURCE_INVALID", f"仅支持 PNG/JPEG：{path}", path, block="image")
    try:
        with Image.open(resolved) as image:
            fmt, size = image.format, image.size
            image.verify()
        with Image.open(resolved) as image:
            image.load()
        expected = "PNG" if resolved.suffix.lower() == ".png" else "JPEG"
        if fmt != expected:
            raise ValueError("真实格式与扩展名不符")
        data = resolved.read_bytes()
    except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
        s.error(
            "RESOURCE_INVALID",
            f"图片无法解码或格式不符：{path}（{type(exc).__name__}）",
            path,
            block="image",
        )
    sha = digest(data)
    destination = f"assets/{sha}.{'png' if fmt == 'PNG' else 'jpg'}"
    doc.resources.append(
        {"original": path, "packed": destination, "sha256": sha, "size": list(size), "format": fmt}
    )
