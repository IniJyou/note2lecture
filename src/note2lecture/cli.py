"""命令入口只导出指定文件，不运行笔记代码，不自动提交或安装。"""

import argparse
import json
import sys
from pathlib import Path

from .batch import export_batch
from .diagnostics import Diagnostic, NoteError
from .document import read_document
from .exporter import dependencies, export_document
from .tools import find_quarto


def main(argv=None):
    parser = argparse.ArgumentParser(description="Note2Lecture 中文讲义基础导出")
    sub = parser.add_subparsers(dest="command", required=True)
    doctor = sub.add_parser("doctor", help="只读检查已有工具、宏包与字体")
    doctor.add_argument("--quarto", help="Quarto 可执行文件路径")
    for command in ("check", "export", "batch"):
        help_text = {"check": "检查输入", "export": "导出讲义", "batch": "批量导出明确选定的笔记"}
        part = sub.add_parser(command, help=help_text[command])
        part.add_argument("input", type=Path, **({"nargs": "+"} if command == "batch" else {}))
        part.add_argument("--quarto", help="Quarto 可执行文件路径")
        part.add_argument(
            "--profile",
            choices=("strict", "markdown", "obsidian"),
            default="strict",
            help="strict：N0.1；markdown：普通 Markdown；obsidian：样例覆盖的 Obsidian 扩展",
        )
        part.add_argument(
            "--list-numbering", choices=("auto", "preserve"), default="auto",
            help="auto：连续自动编号，跳号报错；preserve：显式保留每项源题号（普通模式）",
        )
        if command in {"export", "batch"}:
            part.add_argument("--output", "-o", required=True, type=Path, help="全新的独立输出目录")
    args = parser.parse_args(argv)
    list_options = {"list_numbering": args.list_numbering} if (
        getattr(args, "list_numbering", "auto") != "auto"
    ) else {}
    try:
        if args.command == "doctor":
            versions, fonts = dependencies(find_quarto(args.quarto))
            result = {
                "status": "checked",
                "tools": versions,
                "fonts": fonts,
                "model_enabled": False,
                "code_execution": False,
            }
        elif args.command == "check":
            doc = read_document(
                args.input, find_quarto(args.quarto), args.profile,
                list_numbering=args.list_numbering,
            )
            result = {
                "status": "checked",
                "file": doc.path.name,
                "labels": doc.labels,
                "references": doc.references,
                "resources": doc.resources,
                "code_blocks": len(doc.code),
                "math_blocks": len(doc.math),
                "profile": doc.profile,
                "adaptations": doc.adaptations,
                "obsidian": doc.obsidian,
                "diagnostics": [x.to_dict() for x in doc.warnings],
            }
        elif args.command == "batch":
            result = export_batch(
                args.input, args.output, args.quarto, args.profile,
                progress=lambda index, total, name: print(
                    f"[{index}/{total}] 正在处理 {name}", file=sys.stderr, flush=True
                ),
                **list_options,
            )
        else:
            result = export_document(
                args.input, args.output, args.quarto, args.profile,
                **list_options,
            )
    except NoteError as exc:
        result = {"status": "failed", "diagnostics": [exc.diagnostic.to_dict()]}
    except OSError:
        result = {
            "status": "failed",
            "diagnostics": [
                Diagnostic(
                    "BATCH_IO_FAILED" if args.command == "batch" else "RESOURCE_MISSING",
                    "无法读写批次输出，请检查路径和权限。" if args.command == "batch"
                    else "无法读取指定输入文件。",
                    "<batch>" if args.command == "batch"
                    else Path(getattr(args, "input", "<input>")).name,
                ).to_dict()
            ],
        }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["status"] == "interrupted":
        return 130
    return 2 if result["status"] == "failed" else 0
