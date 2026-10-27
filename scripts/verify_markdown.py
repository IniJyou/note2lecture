"""用户指定单篇 Markdown 的导出验收；私人内容与检查记录只写独立目录。"""

import argparse
import json
import re
import sys
import unicodedata
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from verify_n1 import checked, labels_in_aux, prose_tokens, recompile  # noqa: E402

from note2lecture.document import digest, nodes, read_document  # noqa: E402
from note2lecture.exporter import write_json  # noqa: E402
from note2lecture.math_input import parse_ast  # noqa: E402
from note2lecture.text_glyphs import monochrome_text  # noqa: E402
from note2lecture.tools import find_quarto  # noqa: E402


def compact(text):
    # PDF 的布局空白、英文断词与兼容字形不算正文改写；公式另以原文字节核对。
    # TeX 字体会把直撇号及 `` / '' 排成弯引号，仅统一这些标点字形。
    text = unicodedata.normalize("NFKC", text).replace("``", "“").replace("''", "”")
    text = text.translate(str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"'}))
    return re.sub(r"[\s\u00ad\u200b-]+", "", monochrome_text(text))


def verify(input_path, output, review, profile="markdown", list_numbering="auto"):
    if review.exists():
        raise RuntimeError("检查目录已存在，请换新目录。")
    review.mkdir(parents=True)
    quarto = find_quarto()
    doc = read_document(input_path, quarto, profile, list_numbering=list_numbering)
    package = output / "lecture-source"
    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    tex = (package / "main.tex").read_text(encoding="utf-8")
    assert manifest["input"]["sha256"] == digest(input_path.read_bytes()) == doc.sha256
    assert manifest["protected_content"]["math"] == doc.math
    assert all(x["text"] in tex for x in doc.math)
    assert manifest["model_enabled"] is False and manifest["code_execution"] is False
    assert manifest.get("obsidian", {}) == doc.obsidian
    for resource in doc.resources:
        assert digest((package / resource["packed"]).read_bytes()) == resource["sha256"]
        assert digest((input_path.parent / resource["original"]).read_bytes()) == resource["sha256"]
    for code in doc.code:
        assert (package / "code" / (digest(code.encode()) + ".txt")).read_bytes() == code.encode()
    # 从原稿重解析，复用数学语法解码但不使用结构适配后的正文。
    # 仅去掉完整行的空 HTML 锚点，保留字符数，数学位置仍指向原稿。
    original = re.sub(
        r'(?m)^<a\s+id="[A-Za-z][A-Za-z0-9_-]*"\s*></a>[^\S\n]*$',
        lambda match: " " * len(match[0]),
        doc.source.text,
    )
    original_ast = parse_ast(doc, original, quarto)
    original_ast["blocks"] = [
        block
        for block in original_ast["blocks"]
        if not (
            block["t"] == "Para"
            and len(block["c"]) == 1
            and block["c"][0]["t"] == "Str"
            and block["c"][0]["c"].lower() == "[toc]"
        )
    ]
    original_math = [x["c"][1] for x in nodes(original_ast["blocks"]) if x["t"] == "Math"]
    assert original_math == [x["text"] for x in doc.math]
    if profile == "obsidian":
        # 仅剥离源语法标记，原题头、正文和公式仍参与独立原稿核对。
        for quote in nodes(original_ast["blocks"]):
            if quote["t"] == "BlockQuote" and quote["c"] and quote["c"][0]["t"] == "Para":
                first = quote["c"][0]["c"]
                if (
                    first
                    and first[0]["t"] == "Str"
                    and re.fullmatch(r"\[!(?:note|tip|warning)\]", first[0]["c"], re.I)
                ):
                    first[0]["c"] = ""
            elif quote["t"] == "Figure":
                image = next((x for x in nodes(quote["c"][2]) if x["t"] == "Image"), None)
                if image and "wikilink" in image["c"][0][1]:
                    filename = Path(image["c"][2][0]).name
                    image["c"][1] = [{"t": "Str", "c": filename}]
                    quote["c"][1] = [None, [{"t": "Plain", "c": image["c"][1]}]]
    text = checked(["pdftotext", "-layout", output / "lecture.pdf", "-"])
    # layout 模式会按行穿插相邻表格列，raw 模式用于连续核对单元格正文。
    raw_text = checked(["pdftotext", "-raw", output / "lecture.pdf", "-"])
    normalized = compact(text) + "\n" + compact(raw_text)
    tokens = list(prose_tokens(original_ast["blocks"]))
    missing = [x for x in tokens if compact(x) not in normalized]
    assert not missing, f"PDF 缺少原稿正文词段：{missing[:8]}"
    # 行内代码也需要出现在实际 PDF，不能只核对外置代码文件。
    inline_code = [x["c"][1] for x in nodes(original_ast["blocks"]) if x["t"] == "Code"]
    assert all(compact(x) in normalized for x in inline_code)
    assert not re.search(r"N2L_SOURCE|\?\?|\{#(?:sec|fig|tbl)-", text)
    labels = labels_in_aux(output / "_build/main.aux")
    assert all(x in labels for x in doc.labels)
    assert all(x["to"] in labels for x in doc.internal_links)
    figures = [labels[x] for x in doc.labels if x.startswith("fig-")]
    assert figures == [str(x) for x in range(1, len(figures) + 1)]
    with zipfile.ZipFile(output / "lecture-source.zip") as archive:
        packed = {x for x in archive.namelist() if not x.endswith("/")}
        expected = {x.relative_to(package).as_posix() for x in package.rglob("*") if x.is_file()}
        assert packed == expected
        assert all(archive.read(x) == (package / x).read_bytes() for x in packed)
    relocated = review / "relocated-source"
    assert recompile(package, relocated) == labels
    recorder = (relocated / "main.fls").read_text(encoding="utf-8", errors="replace")
    assert (
        str(input_path.parent).replace("\\", "/").lower() not in recorder.replace("\\", "/").lower()
    )
    assert not re.search(r"(?<![A-Za-z0-9])[A-Za-z]:[/\\]", tex)
    pages = int(re.search(r"Pages:\s+(\d+)", checked(["pdfinfo", output / "lecture.pdf"]))[1])
    result = {
        "pages": pages,
        "math_exact": len(doc.math),
        "code_exact": len(doc.code),
        "inline_code": len(inline_code),
        "prose_tokens": len(tokens),
        "tables": sum(x["t"] == "Table" for x in nodes(original_ast["blocks"])),
        "resources": len(doc.resources),
        "internal_links": len(doc.internal_links),
        "profile": profile,
        "obsidian": doc.obsidian,
        "input_unchanged": True,
        "source_zip_exact": True,
        "relocated_compile": True,
        "content_review": True,
        "page_review": False,
        "local_reference_warnings": len(doc.warnings),
        "pdf_sha256": digest((output / "lecture.pdf").read_bytes()),
        "source_zip_sha256": digest((output / "lecture-source.zip").read_bytes()),
    }
    write_json(review / "validation.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="检查已导出的单篇 Markdown；不扫描笔记库")
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("review", type=Path, help="全新的独立检查目录")
    parser.add_argument("--profile", choices=("markdown", "obsidian"), default="markdown")
    parser.add_argument("--list-numbering", choices=("auto", "preserve"), default="auto")
    args = parser.parse_args()
    verify(args.input.absolute(), args.output.absolute(), args.review.absolute(), args.profile,
           args.list_numbering)
