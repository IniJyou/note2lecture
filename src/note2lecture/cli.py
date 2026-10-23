"""命令入口只导出指定文件，不运行笔记代码，不自动提交或安装。"""

import argparse
import json
from pathlib import Path

from .diagnostics import Diagnostic, NoteError
from .document import read_document
from .exporter import dependencies, export_document
from .tools import find_quarto


def main(argv=None):
    parser = argparse.ArgumentParser(description="Note2Lecture 中文讲义基础导出")
    sub = parser.add_subparsers(dest="command", required=True)
    doctor = sub.add_parser("doctor", help="只读检查已有工具、宏包与字体")
    doctor.add_argument("--quarto", help="Quarto 可执行文件路径")
    for command in ("check", "export"):
        part = sub.add_parser(command, help="检查输入" if command == "check" else "导出讲义")
        part.add_argument("input", type=Path)
        part.add_argument("--quarto", help="Quarto 可执行文件路径")
        if command == "export":
            part.add_argument("--output", "-o", required=True, type=Path, help="全新的独立输出目录")
    args = parser.parse_args(argv)
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
            doc = read_document(args.input, find_quarto(args.quarto))
            result = {
                "status": "checked",
                "file": doc.path.name,
                "labels": doc.labels,
                "references": doc.references,
                "resources": doc.resources,
                "code_blocks": len(doc.code),
                "math_blocks": len(doc.math),
            }
        else:
            result = export_document(args.input, args.output, args.quarto)
    except NoteError as exc:
        result = {"status": "failed", "diagnostics": [exc.diagnostic.to_dict()]}
    except OSError:
        result = {
            "status": "failed",
            "diagnostics": [
                Diagnostic(
                    "RESOURCE_MISSING",
                    "无法读取指定输入文件。",
                    Path(getattr(args, "input", "<input>")).name,
                ).to_dict()
            ],
        }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 2 if result["status"] == "failed" else 0
