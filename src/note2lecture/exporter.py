"""Quarto 生成 LaTeX，XeLaTeX 离线编译；每次创建独立输出，绝不覆盖。"""

import copy
import json
import re
import shutil
import sys
from collections import Counter
from pathlib import Path

import PIL
import yaml

from . import __version__
from .diagnostics import Diagnostic, NoteError
from .document import digest, nodes, plain, read_document
from .tools import ROOT, find_quarto, pandoc, run, tool_versions

FONT_FILES = [
    "FandolSong-Regular.otf",
    "FandolSong-Bold.otf",
    "FandolHei-Regular.otf",
    "FandolFang-Regular.otf",
    "lmroman10-regular.otf",
    "lmmono10-regular.otf",
    "latinmodern-math.otf",
]
PACKAGES = [
    "ctexart.cls",
    "amsthm.sty",
    "fvextra.sty",
    "fancyhdr.sty",
    "needspace.sty",
    "unicode-math.sty",
    "longtable.sty",
    "booktabs.sty",
    "caption.sty",
]


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def dependencies(quarto):
    versions = tool_versions(quarto)
    fonts = []
    for filename in PACKAGES + FONT_FILES:
        result = run(["kpsewhich", filename])
        located = Path(result.stdout.strip())
        if result.returncode or not located.is_file():
            raise NoteError(
                Diagnostic(
                    "DEPENDENCY_MISSING",
                    f"缺少 TeX 依赖：{filename}",
                    "<dependencies>",
                    hint="请由用户准备依赖后重试。",
                )
            )
        if filename in FONT_FILES:
            fonts.append({"file": filename, "sha256": digest(located.read_bytes())})
    versions.update(python=sys.version.split()[0], PyYAML=yaml.__version__, Pillow=PIL.__version__)
    return versions, fonts


def ref_tex(identifier):
    kind = identifier.split("-", 1)[0]
    ref = r"\ref*{" + identifier + "}"
    visible = {
        "sec": "第~" + ref + "~节",
        "eq": "式~(" + ref + ")",
        "fig": "图~" + ref,
        "tbl": "表~" + ref,
        "def": "定义~" + ref,
        "thm": "定理~" + ref,
        "lem": "引理~" + ref,
        "exm": "例~" + ref,
    }[kind]
    return r"\hyperref[" + identifier + "]{" + visible + "}"


def bookmark_text(text):
    """书签使用公式源码的普通文本表示，TeX 特殊字符只作字面显示。"""
    escapes = {
        "\\": r"\textbackslash{}", "{": r"\{", "}": r"\}", "$": r"\$",
        "&": r"\&", "#": r"\#", "%": r"\%", "_": r"\_",
        "^": r"\textasciicircum{}", "~": r"\textasciitilde{}",
    }
    return "".join(escapes.get(char, char) for char in " ".join(text.split()))


TEXT_SYMBOLS = {"①", "②", "∎"}


def heading_bookmark(heading):
    return any(
        x["t"] == "Math" or (x["t"] == "Str" and TEXT_SYMBOLS.intersection(x["c"]))
        for x in nodes(heading)
    )


def prepare_ast(doc, package):
    ast = copy.deepcopy(doc.ast)
    resources = {x["original"]: x for x in doc.resources}
    heading_nodes = {
        id(child)
        for heading in nodes(ast["blocks"])
        if heading["t"] == "Header"
        for child in nodes(heading)
    }
    numbered_displays = {
        id(child)
        for block in nodes(ast["blocks"])
        if block["t"] in {"Para", "Plain"}
        and any(
            x["t"] == "Str" and re.fullmatch(r"\{#eq-[a-z0-9-]+\}", x["c"])
            for x in block["c"]
        )
        for child in nodes(block)
        if child["t"] == "Math" and child["c"][0]["t"] == "DisplayMath"
    }
    for item in nodes(ast["blocks"]):
        kind, c = item["t"], item.get("c")
        if doc.markdown_mode and kind == "Header" and heading_bookmark(item):
            c[2].append(
                {"t": "RawInline", "c": ["latex", r"\NtwoLHeadingBookmark{" + c[1][0] + "}"]}
            )
        elif kind == "Cite":
            item.update(t="RawInline", c=["latex", ref_tex(c[0][0]["citationId"])])
        elif kind == "Image":
            from urllib.parse import unquote

            resource = resources[unquote(c[2][0])]
            c[2][0] = resource["packed"]
            width, height = resource["size"]
            scale = min(25.4 / 96, 160 / width, 135 / height)
            c[0][2].append(["width", f"{width * scale:.3f}mm"])
        elif kind == "CodeBlock":
            data = c[1].encode("utf-8")
            target = "code/" + digest(data) + ".txt"
            (package / "code").mkdir(exist_ok=True)
            (package / target).write_bytes(data)
            c[0][2].append(["n2l-code", target])
        elif doc.markdown_mode and kind == "Math":
            if id(item) in heading_nodes:
                # 原生书签写出器会把后端占位符当成题头，故题头数学显式提供纯文本书签。
                item.update(
                    t="RawInline",
                    c=["latex", r"\texorpdfstring{\(" + c[1] + r"\)}{" + bookmark_text(c[1]) + "}"],
                )
                continue
            # 保护行内空格/软换行及独立公式缩进；后端完成后统一恢复原文。
            token = r"\NtwoLMathToken{" + digest(c[1].encode()) + "}"
            if (
                c[0]["t"] == "DisplayMath"
                and id(item) not in numbered_displays
                and not re.search(r"\\tag\b", c[1])
            ):
                # 宏从正文环境测宽并按需分行，不能套在已有的 \[...\] 中。
                item.update(
                    t="RawInline",
                    c=["latex", r"\NtwoLMathDisplay{" + digest(c[1].encode()) + "}{" + token + "}"],
                )
                continue
            if c[0]["t"] == "DisplayMath" and not re.search(r"\\tag\b", c[1]):
                token = r"\NtwoLDisplay{" + token + "}"
            c[1] = token
        elif doc.markdown_mode and kind == "Str" and TEXT_SYMBOLS.intersection(c):
            # 只切换已知缺字的字体，保留原 Unicode 字符；代码和数学不走此路径。
            pieces = re.split("([①②∎])", c)
            item.update(t="Span", c=[["", [], []], [
                {"t": "RawInline", "c": ["latex", r"\NtwoLTextSymbol{" + p + "}"]}
                if p in TEXT_SYMBOLS else {"t": "Str", "c": p}
                for p in pieces if p
            ]])
            if id(item) in heading_nodes:
                heading_nodes.update(id(x) for x in nodes(item))
        elif doc.markdown_mode and kind in {"Code", "Str"} and id(item) not in heading_nodes:
            text = c[1] if kind == "Code" else c
            if (
                re.fullmatch(r"[A-Za-z0-9_./-]+", text)
                and re.search(r"[A-Za-z]", text)
                and any(x in text for x in "_./")
            ):
                parts = re.split(r"([_./])", text)
                escaped = "".join(
                    (r"\_" if x == "_" else x) + (r"\allowbreak{}" if x in "_./" and x else "")
                    for x in parts
                )
                if kind == "Code":
                    escaped = r"\texttt{" + escaped + "}"
                item.update(t="RawInline", c=["latex", escaped])
    # 源标记仅用于定位，不改变文档可见内容。
    marked = []
    cursor = len(doc.source.text) - len(doc.body)
    for index, block in enumerate(ast["blocks"]):
        identifiers = [x["c"][1][0] for x in nodes(block) if x["t"] == "Header"]
        line = next((doc.labels[x]["line"] for x in identifiers if x in doc.labels), None)
        if line is None:
            # 使用保留的词或公式/代码正文定位，不能用导出后的重排文本假装精确匹配。
            candidates = []
            for item in nodes(doc.ast["blocks"][index]):
                if item["t"] in {"Math", "CodeBlock"}:
                    candidates.append(item["c"][1])
                elif item["t"] == "Str" and len(item["c"]) >= 3:
                    candidates.append(item["c"])
            offsets = [doc.source.text.find(x, cursor) for x in candidates]
            offset = next((x for x in offsets if x >= 0), cursor)
            line = doc.source.position(offset)[0]
        # 位置仍标为近似；顺序推进，避免重复词把后文错误映回早先章节。
        line_start = sum(len(x) for x in doc.source.text.splitlines(keepends=True)[: line - 1])
        end = doc.source.text.find("\n\n", line_start)
        cursor = max(cursor, end + 2 if end >= 0 else line_start)
        marked.extend([{"t": "RawBlock", "c": ["latex", f"% N2L_SOURCE {line} {index}"]}, block])
    ast["blocks"] = marked
    return ast


def render_config(meta):
    titles = {"thm": "定理", "lem": "引理", "def": "定义", "exm": "例"}
    return {
        **meta,
        "format": {
            "latex": {
                "documentclass": "ctexart",
                "classoption": ["fontset=fandol"],
                "fontsize": "11pt",
                "pdf-engine": "xelatex",
                "latex-auto-install": False,
                "keep-tex": True,
                "toc": True,
                "toc-depth": 2,
                "number-sections": True,
                "mainfont": "Latin Modern Roman",
                "mathfont": "Latin Modern Math",
                "monofont": "Latin Modern Mono",
                "colorlinks": True,
                "linkcolor": "black",
                "urlcolor": "black",
                "citecolor": "black",
                "fig-pos": "H",
                "include-in-header": ["template/header.tex"],
            }
        },
        "filters": ["template/code.lua"],
        "execute": {"enabled": False},
        "crossref": {"chapters": False, **{x + "-title": y for x, y in titles.items()}},
    }


def adapt_preamble(tex):
    """只适配实测存在的 Quarto 定理定义；不触碰正文、公式或代码。"""
    preamble, separator, body = tex.partition(r"\begin{document}")
    if not separator:
        raise NoteError(
            Diagnostic("COMPILE_FAILED", "生成的 LaTeX 缺少 document 入口。", "main.tex")
        )
    preamble = preamble.replace(r"\theoremstyle{plain}", r"\theoremstyle{definition}")
    preamble = re.sub(
        r"(\\newtheorem\{(?:theorem|lemma|definition|example)\}\{[^}]+\})\[section\]",
        r"\1",
        preamble,
    )
    return preamble + separator + body


def restore_display_math(tex, doc):
    """仅展开程序生成的行内/独立数学占位符，保持空格和换行。"""
    if not doc.markdown_mode:
        return tex
    expected = {}
    heading_math = Counter(
        digest(node["c"][1].encode())
        for heading in nodes(doc.ast["blocks"]) if heading["t"] == "Header"
        for node in nodes(heading) if node["t"] == "Math"
    )
    for math in doc.math:
        if heading_math[math["sha256"]]:
            heading_math[math["sha256"]] -= 1
            continue
        expected.setdefault(math["sha256"], []).append(math["text"])

    def restore(match):
        entries = expected.get(match[1], [])
        if not entries:
            doc.source.error("COMPILE_FAILED", "后端产生了非预期的公式占位符。", block="math")
        return entries.pop()

    tex = re.sub(r"\\NtwoLMathToken\{([0-9a-f]{64})\}", restore, tex)
    if any(expected.values()):
        missing = [text for entries in expected.values() for text in entries]
        doc.source.error(
            "COMPILE_FAILED",
            f"排版后端缺少 {len(missing)} 处公式保护标记，导出已停止。",
            missing[0],
            block="math",
            hint="这是后端输出完整性问题；保留本次中间文件供排查，不要删除保护检查。",
        )
    for heading in nodes(doc.ast["blocks"]):
        if heading["t"] != "Header" or not heading_bookmark(heading):
            continue
        ident = heading["c"][1][0]
        marker = r"\NtwoLHeadingBookmark{" + ident + "}"
        start = tex.find(marker)
        boundary = start + len(marker)
        while boundary < len(tex) and tex[boundary].isspace():
            boundary += 1
        label = tex.find(r"\label{" + ident + "}", boundary)
        if start < 0 or tex[boundary : boundary + 2] != "}{" or tex[label - 2 : label] != "}}":
            doc.source.error("COMPILE_FAILED", "后端标题书签结构无法安全恢复。", ident)
        fallback = bookmark_text(plain(heading["c"][2]))
        tex = tex[:start] + "}{" + fallback + "}}" + tex[label:]
    return tex


def tex_source_map(tex, doc):
    markers = []
    for number, line in enumerate(tex.splitlines(), 1):
        hit = re.match(r"% N2L_SOURCE (\d+) (\d+)", line)
        if hit:
            markers.append(
                {
                    "tex_line": number,
                    "source_line": int(hit[1]),
                    "block_index": int(hit[2]),
                    "approximate": True,
                }
            )
    return {"file": doc.path.name, "markers": markers}


def log_diagnostics(log, doc, mapping):
    diagnostics = []
    patterns = [
        ("GLYPH_MISSING", r"Missing character:[^\n]*"),
        ("LAYOUT_OVERFLOW", r"Overfull \\[hv]box[^\n]*"),
        ("REF_UNDEFINED", r"LaTeX Warning: (?:Reference|There were undefined)[^\n]*"),
    ]
    for code, pattern in patterns:
        for hit in re.finditer(pattern, log):
            numbers = re.search(r"at lines? (\d+)", log[hit.start() : hit.end() + 200])
            tex_line = int(numbers[1]) if numbers else 0
            candidates = [x for x in mapping["markers"] if x["tex_line"] <= tex_line]
            source_line = candidates[-1]["source_line"] if candidates else 1
            diagnostics.append(
                Diagnostic(
                    code,
                    hit[0],
                    doc.path.name,
                    source_line,
                    block="layout",
                    approximate=True,
                    hint="查看 _build/main.log 与 source-map.json。",
                )
            )
    return diagnostics


def math_width_diagnostic(log, doc):
    """测宽标记携带原公式摘要，避免把整个大段落起点冒充出错公式位置。"""
    hit = re.search(r"N2LWIDE:([0-9a-f]{64})", log)
    if not hit:
        return None
    formula = next((m for m in doc.math if m["sha256"] == hit[1]), None)
    if formula is None:
        return None
    needle = formula["text"].strip()
    offset = doc.source.text.find(needle)
    approximate = offset < 0 or doc.source.text.count(needle) != 1
    if offset < 0:
        first = next((line.strip() for line in needle.splitlines() if line.strip()), "")
        offset = doc.source.text.find(first)
    line, column = doc.source.position(offset)
    dimensions = re.search(r"N2LDIMS:([\d.]+)pt:([\d.]+)pt", log)
    detail = ""
    if dimensions:
        width, available = (float(x) * 25.4 / 72.27 for x in dimensions.groups())
        detail = f"（公式约 {width:.1f} mm，可用 {available:.1f} mm）"
    return Diagnostic(
        "LAYOUT_OVERFLOW",
        "公式仍超过当前页面的可读宽度" + detail + "。",
        doc.path.name,
        line,
        column,
        block="math",
        hint="保留原稿；需要为此公式单独选择排版方式，查看 _build/xelatex-1.log。",
        approximate=approximate,
    )


SOURCE_README = """# 可编辑 LaTeX 源包

入口是 main.tex。图片位于 assets/，代码原文位于 code/（若有），样式位于 template/。
在全新目录首次编译，或修改正文导致目录、分页变化时，建议运行三轮 XeLaTeX：

```powershell
xelatex -no-shell-escape -halt-on-error -interaction=nonstopmode main.tex
xelatex -no-shell-escape -halt-on-error -interaction=nonstopmode main.tex
xelatex -no-shell-escape -halt-on-error -interaction=nonstopmode main.tex
```

检查 main.log；若仍提示 Rerun，应继续编译至目录页码和引用收敛。
这里不调用 Quarto、Python、模型或原笔记目录，也不需要下载。
请保留所有资源和样式。字体采用 TeX Live 中的 Fandol 宋/黑/仿宋与 Latin Modern；
所需宏包包括 ctex、unicode-math、amsmath、amsthm、graphicx、geometry、longtable、
booktabs、caption、fvextra、fancyhdr、needspace、setspace、hyperref 等。
依赖的实际工具版本及字体摘要见 manifest.json。字体文件未随包分发。

normalized.md 是生成过程的工作副本，不是原稿；引用已转换为受控 LaTeX，
资源路径和代码块属性已经重写。render-config.yml 记录受控渲染设置。
仅重新编译 main.tex 不依赖这些 Markdown 渲染工具。
输出 PDF 不表示已通过内容、页面或风格检查，检查状态见上级 diagnostics.json。
"""


def export_document(input_path, output, quarto=None, profile="strict"):
    output = Path(output).absolute()
    if output.exists() or output.is_symlink():
        raise NoteError(
            Diagnostic(
                "OUTPUT_EXISTS", "输出目录已存在，拒绝覆盖；请换新目录。", Path(input_path).name
            )
        )
    output.mkdir(parents=True)
    report = {
        "status": "failed",
        "checks": {
            "structure": False,
            "compile": False,
            "content_review": False,
            "page_review": False,
            "style_approved": False,
        },
        "diagnostics": [],
    }
    try:
        quarto = find_quarto(quarto)
        versions, fonts = dependencies(quarto)
        doc = read_document(input_path, quarto, profile)
        report["diagnostics"] = [x.to_dict() for x in doc.warnings]
        report["checks"]["structure"] = True
        package = output / "lecture-source"
        package.mkdir()
        (package / "assets").mkdir()
        template = package / "template"
        template.mkdir()
        template_hashes = {}
        template_files = ["header.tex", "code.lua"]
        if doc.markdown_mode:
            template_files.extend(["markdown.tex", "markdown.lua", "math-wrap.tex"])
        if doc.profile == "obsidian":
            template_files.extend(["obsidian.tex", "obsidian.lua"])
        for filename in template_files:
            data = (ROOT / "templates/lecture" / filename).read_bytes()
            (template / filename).write_bytes(data)
            template_hashes[filename] = digest(data)
        for resource in doc.resources:
            data = (doc.path.parent / resource["original"]).read_bytes()
            if digest(data) != resource["sha256"]:
                doc.source.error(
                    "RESOURCE_INVALID", "检查后图片发生变化，请重试。", resource["original"]
                )
            (package / resource["packed"]).write_bytes(data)
        ast = prepare_ast(doc, package)
        body = pandoc(quarto, json.dumps(ast, ensure_ascii=False), "json", "markdown-smart-raw_tex")
        normalized = "---\n" + yaml.safe_dump(doc.metadata, allow_unicode=True) + "---\n" + body
        (package / "normalized.md").write_text(normalized, encoding="utf-8")
        config = render_config(doc.metadata)
        if doc.markdown_mode:
            config["format"]["latex"]["number-sections"] = False
            config["format"]["latex"]["include-in-header"].append("template/markdown.tex")
            config["format"]["latex"]["include-in-header"].append("template/math-wrap.tex")
            config["filters"].append("template/markdown.lua")
        if doc.profile == "obsidian":
            config["format"]["latex"]["include-in-header"].append("template/obsidian.tex")
            config["filters"].append("template/obsidian.lua")
        (package / "render-config.yml").write_text(
            yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding="utf-8"
        )
        # 独立渲染项目隔离父目录配置；仅渲染明确指定的文件。
        (package / "_quarto.yml").write_text("project:\n  type: default\n", encoding="utf-8")
        (package / "main.qmd").write_text(
            "---\n" + yaml.safe_dump(config, allow_unicode=True, sort_keys=False) + "---\n" + body,
            encoding="utf-8",
        )
        build = output / "_build"
        build.mkdir()
        result = run([quarto, "render", "main.qmd", "--to", "latex", "--no-execute"], cwd=package)
        (build / "quarto.log").write_text(result.stdout + result.stderr, encoding="utf-8")
        if result.returncode or not (package / "main.tex").is_file():
            doc.source.error(
                "COMPILE_FAILED",
                "Quarto 生成 LaTeX 失败。",
                hint="查看 _build/quarto.log；未启用自动安装。",
            )
        tex_path = package / "main.tex"
        tex = restore_display_math(adapt_preamble(tex_path.read_text(encoding="utf-8")), doc)
        for math in doc.math:
            if math["text"] not in tex:
                doc.source.error(
                    "COMPILE_FAILED",
                    "后端未原样保留公式正文，本次导出不能通过。",
                    math["text"],
                    block="math",
                    hint="检查规范化副本与生成的 LaTeX；程序没有自动改写公式。",
                )
        tex_path.write_text(tex, encoding="utf-8")
        mapping = tex_source_map(tex, doc)
        write_json(package / "source-map.json", mapping)
        for index in range(3):
            result = run(
                [
                    "xelatex",
                    "-no-shell-escape",
                    "-halt-on-error",
                    "-interaction=nonstopmode",
                    "-file-line-error",
                    "-recorder",
                    f"-output-directory={build}",
                    "main.tex",
                ],
                cwd=package,
            )
            (build / f"xelatex-{index + 1}.log").write_text(
                result.stdout + result.stderr, encoding="utf-8"
            )
            if result.returncode:
                width_error = math_width_diagnostic(result.stdout, doc)
                if width_error is not None:
                    raise NoteError(width_error)
                hit = re.search(r"main\.tex:(\d+):[^\n]*", result.stdout)
                line = int(hit[1]) if hit else 0
                marks = [x for x in mapping["markers"] if x["tex_line"] <= line]
                doc.source.error(
                    "COMPILE_FAILED",
                    hit[0] if hit else "XeLaTeX 编译失败。",
                    offset=-1,
                    block="compile",
                    hint=f"近似原文行 {marks[-1]['source_line'] if marks else 1}；"
                    f"查看 _build/xelatex-{index + 1}.log。",
                )
            if index >= 1 and "Rerun to get" not in result.stdout:
                break
        log = (build / "main.log").read_text(encoding="utf-8", errors="replace")
        diagnostics = log_diagnostics(log, doc, mapping)
        report["checks"]["compile"] = True
        if diagnostics:
            report["diagnostics"].extend(x.to_dict() for x in diagnostics)
        shutil.copyfile(build / "main.pdf", output / "lecture.pdf")
        manifest = {
            "note2lecture": __version__,
            "input_protocol": {
                "strict": "N0.1",
                "markdown": "N2-markdown.1",
                "obsidian": "N2-obsidian.1",
            }[doc.profile],
            "profile": doc.profile,
            "adaptations": doc.adaptations,
            "internal_links": doc.internal_links,
            "obsidian": doc.obsidian,
            "model_enabled": False,
            "code_execution": False,
            "input": {"file": doc.path.name, "sha256": doc.sha256},
            "resources": doc.resources,
            "labels": doc.labels,
            "references": doc.references,
            "protected_content": {
                "code": [{"text": x, "sha256": digest(x.encode())} for x in doc.code],
                "math": doc.math,
            },
            "template": {"name": "清简讲义", "version": "0.1", "files": template_hashes},
            "fonts": fonts,
            "tools": versions,
            "config": config,
        }
        write_json(package / "manifest.json", manifest)
        (package / "README.md").write_text(SOURCE_README, encoding="utf-8")
        if digest(doc.path.read_bytes()) != doc.sha256:
            doc.source.error("INPUT_ENCODING", "导出期间原输入发生变化，本次结果不能通过。")
        # Quarto 自建缓存移到本次构建日志目录，不打进可编辑源包，也不删除诊断证据。
        cache = package / ".quarto"
        if cache.exists():
            if not cache.resolve().is_relative_to(output.resolve()):
                doc.source.error("RESOURCE_PATH", "生成的缓存目录意外指向输出目录之外。")
            cache.rename(build / "quarto-cache")
        shutil.make_archive(str(output / "lecture-source"), "zip", package)
        report["status"] = "failed" if diagnostics else "partial"
    except NoteError as exc:
        report["status"] = "failed"
        report["diagnostics"].append(exc.diagnostic.to_dict())
    except (OSError, ValueError) as exc:
        report["status"] = "failed"
        report["diagnostics"].append(
            Diagnostic(
                "COMPILE_FAILED",
                f"文件或数据处理失败：{type(exc).__name__}",
                Path(input_path).name,
            ).to_dict()
        )
    write_json(output / "diagnostics.json", report)
    return report
