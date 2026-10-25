"""工具边界与长 UTF-8 输出回归，不读取私人笔记。"""

import json
import os

from note2lecture.document import nodes, plain
from note2lecture.tools import pandoc, pandoc_command


def test_pandoc_uses_quarto_bundled_binary_when_present(tmp_path):
    quarto = tmp_path / "quarto.exe"
    tools = tmp_path / "tools"
    tools.mkdir()
    bundled = tools / ("pandoc.exe" if os.name == "nt" else "pandoc")
    bundled.touch()
    assert pandoc_command(quarto) == [bundled]


def test_pandoc_without_bundled_layout_keeps_explicit_quarto(tmp_path):
    quarto = tmp_path / "quarto.exe"
    assert pandoc_command(quarto) == [quarto, "pandoc"]


def test_large_utf8_document_retains_every_block_and_formula(quarto):
    paragraphs = [f"原创第{i}段" + "核对字符" * 24 for i in range(750)]
    text = "\n\n".join(f"{p} $v_{{{i}}}$。" for i, p in enumerate(paragraphs))
    # 大于包装命令的一次输出缓冲，读入与写出两条路径均核对实际内容。
    assert len(text.encode()) > 200_000
    ast = json.loads(pandoc(quarto, text, "markdown-smart-latex_macros", "json"))
    assert len(ast["blocks"]) == len(paragraphs)
    assert all(plain(block).startswith(p) for block, p in zip(ast["blocks"], paragraphs))
    assert [n["c"][1] for n in nodes(ast["blocks"]) if n["t"] == "Math"] == [
        f"v_{{{i}}}" for i in range(len(paragraphs))
    ]
    output = pandoc(quarto, json.dumps(ast, ensure_ascii=False), "json", "markdown-smart-raw_tex")
    assert all(p in output for p in paragraphs)
    assert all(f"$v_{{{i}}}$" in output for i in range(len(paragraphs)))
