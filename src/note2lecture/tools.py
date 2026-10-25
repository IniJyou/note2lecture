"""只调用已有工具；不下载、安装或修改系统环境。"""

import os
import shutil
import subprocess
from pathlib import Path

from .diagnostics import Diagnostic, NoteError

ROOT = Path(__file__).resolve().parents[2]


def run(args, *, cwd=None, text=None, timeout=180):
    env = os.environ.copy()
    env.update(NO_COLOR="1", PYTHONIOENCODING="utf-8")
    try:
        return subprocess.run(
            [str(x) for x in args],
            cwd=cwd,
            input=text,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=env,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        # 不输出命令中的私人绝对路径。
        raise NoteError(
            Diagnostic(
                "DEPENDENCY_MISSING", f"无法运行工具：{type(exc).__name__}", "<dependencies>"
            )
        ) from exc


def find_quarto(explicit=None):
    candidate = explicit or os.environ.get("NOTE2LECTURE_QUARTO") or shutil.which("quarto")
    if not candidate:
        # 本地兼容入口由开发时创建，忽略于 Git；不作为发布环境的硬编码路径。
        alias = ROOT / ".cache/quarto/bin/quarto.exe"
        if alias.is_file():
            candidate = alias
    if not candidate or not Path(candidate).is_file():
        raise NoteError(
            Diagnostic(
                "DEPENDENCY_MISSING",
                "未找到 Quarto；请使用 --quarto 指定已有可执行文件。",
                "<dependencies>",
                hint="本程序不会自动安装 Quarto。",
            )
        )
    # 不 resolve：保留英文联接路径，避免 Quarto 的中文安装路径加载问题。
    return Path(os.path.abspath(candidate))


def pandoc_command(quarto):
    # 本机 Quarto 包装命令在大 stdout 中转时会随机漏片段；直接运行它随附的同版 Pandoc。
    # 保留英文联接路径，不改用 PATH 中另装的 Pandoc。
    binary = "pandoc.exe" if os.name == "nt" else "pandoc"
    bundled = Path(quarto).parent / "tools" / binary
    return [bundled] if bundled.is_file() else [quarto, "pandoc"]


def pandoc(quarto, text, input_format, output_format):
    result = run(
        [
            *pandoc_command(quarto),
            "--from",
            input_format,
            "--to",
            output_format,
            "--wrap=none",
            "--preserve-tabs",
        ],
        text=text,
    )
    if result.returncode:
        raise NoteError(
            Diagnostic(
                "STRUCTURE_INVALID", "Pandoc 无法解析文档。", "<input>", hint=result.stderr[-2000:]
            )
        )
    return result.stdout


def tool_versions(quarto):
    commands = {
        "quarto": [quarto, "--version"],
        "pandoc": [*pandoc_command(quarto), "--version"],
        "xelatex": ["xelatex", "--version"],
    }
    versions = {}
    for name, command in commands.items():
        result = run(command)
        if result.returncode:
            raise NoteError(
                Diagnostic("DEPENDENCY_MISSING", f"{name} 版本检查失败。", "<dependencies>")
            )
        versions[name] = result.stdout.splitlines()[0]
    return versions
