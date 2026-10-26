"""只处理明确选定的 Markdown；逐篇隔离失败，原稿和已有输出不覆盖。"""

import json
from pathlib import Path

from .diagnostics import Diagnostic, NoteError
from .exporter import export_document, write_json


def failed_report(diagnostic):
    return {
        "status": "failed",
        "checks": {
            "structure": False,
            "compile": False,
            "content_review": False,
            "page_review": False,
            "style_approved": False,
        },
        "diagnostics": [diagnostic.to_dict()],
    }


def export_batch(input_paths, output, quarto=None, profile="strict", *, progress=None):
    inputs = [Path(path).absolute() for path in input_paths]
    if not inputs:
        raise NoteError(Diagnostic("BATCH_INPUT_EMPTY", "请明确指定至少一篇 Markdown。", "<batch>"))
    output = Path(output).absolute()
    try:
        # 原子创建根目录，连空目录和失效链接也不复用。
        output.mkdir(parents=True)
    except FileExistsError as exc:
        raise NoteError(Diagnostic(
            "OUTPUT_EXISTS", "批次输出已存在，拒绝覆盖；请换新目录。", "<batch>"
        )) from exc

    report = {
        "schema": "N4-batch.1",
        "status": "running",
        "profile": profile,
        "output": str(output),
        "inputs": [str(path) for path in inputs],
        "model_enabled": False,
        "code_execution": False,
        "summary": {
            "total": len(inputs), "converted": 0, "failed": 0,
            "pending": len(inputs), "review_pending": 0,
        },
        "items": [],
        "diagnostics": [],
    }
    summary_path = output / "batch-summary.json"
    write_json(summary_path, report)
    seen = {}
    for index, path in enumerate(inputs, 1):
        folder = f"{index:03d}"
        target = output / folder
        try:
            if progress:
                progress(index, len(inputs), path.name)
            if path.suffix.lower() != ".md" or path.is_dir():
                raise NoteError(Diagnostic(
                    "INPUT_INVALID", "批处理只接受明确指定的 .md 文件，不扫描目录。", path.name
                ))
            if not path.is_file():
                raise NoteError(Diagnostic("RESOURCE_MISSING", "指定的输入文件不存在。", path.name))
            identity = path.resolve()
            if identity in seen:
                raise NoteError(Diagnostic(
                    "INPUT_DUPLICATE", "同一输入被重复指定，未再次导出。", path.name,
                    hint=f"与本批第 {seen[identity]} 项相同；不同目录的同名文件可以分别导出。",
                ))
            seen[identity] = index
            result = export_document(path, target, quarto, profile)
        except KeyboardInterrupt:
            # 未完成项仍计入 pending，不能把中断当作整批完成。
            report["status"] = "interrupted"
            report["diagnostics"].append(Diagnostic(
                "BATCH_INTERRUPTED", "批处理已中断，未完成项仍标为待处理。", path.name
            ).to_dict())
            write_json(summary_path, report)
            return report
        except NoteError as exc:
            result = failed_report(exc.diagnostic)
        except Exception as exc:
            # 批次边界隔离单篇意外异常；只报告类型，避免终端泄露私人正文。
            result = failed_report(Diagnostic(
                "BATCH_ITEM_FAILED", f"单篇处理异常：{type(exc).__name__}。", path.name,
                hint="其他项继续处理；可用单篇 export 命令和新的输出目录复现此项。",
            ))

        conflict = any(x["code"] == "OUTPUT_EXISTS" for x in result["diagnostics"])
        if result["status"] == "failed" and not conflict:
            try:
                if target.is_symlink() or not target.resolve().is_relative_to(output.resolve()):
                    raise OSError("诊断目录意外指向批次之外")
                target.mkdir(exist_ok=True)
                diagnostic_path = target / "diagnostics.json"
                if not diagnostic_path.exists():
                    # 独占创建，不覆盖转换器已经写出的报告。
                    with diagnostic_path.open("x", encoding="utf-8") as stream:
                        stream.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
            except OSError:
                result["diagnostics"].append(Diagnostic(
                    "BATCH_DIAGNOSTIC_IO", "无法另存单篇诊断，请查看本批 batch-summary.json。",
                    path.name, severity="warning",
                ).to_dict())
        item = {
            "index": index, "input": str(path), "output": folder, **result,
            "artifacts": {
                key: f"{folder}/{relative}"
                for key, relative in (
                    ("pdf", "lecture.pdf"), ("source_zip", "lecture-source.zip"),
                    ("source_tex", "lecture-source/main.tex"), ("diagnostics", "diagnostics.json"),
                )
                if not conflict and (target / relative).is_file()
            },
        }
        report["items"].append(item)
        summary = report["summary"]
        failed = result["status"] == "failed"
        summary["failed" if failed else "converted"] += 1
        if not failed and not all(
            result["checks"][key] for key in ("content_review", "page_review", "style_approved")
        ):
            summary["review_pending"] += 1
        summary["pending"] -= 1
        # 每篇结束即落盘；崩溃时仍可查已完成项，不覆盖单篇的诊断状态。
        if summary["pending"] == 0:
            report["status"] = "failed" if summary["failed"] else "partial"
        write_json(summary_path, report)
    return report
