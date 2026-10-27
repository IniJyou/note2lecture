# Windows 第一次导出讲义

这份指南从准备工具开始，完成一次原创样例转换，再说明怎样处理自己的笔记。基础转换在本地运行，不需要 GPU 或模型。当前提供 PDF 与可编辑 LaTeX 源包、单篇与指定文件批处理。

已有基础转换环境时，可按 [桌面界面指南](desktop-gui.md)安装可选界面依赖，通过窗口完成同样的检查和导出。

## 1. 取得项目与准备工具

从 [GitHub 仓库](https://github.com/IniJyou/note2lecture) 下载源码 ZIP 并解压，或使用 Git 获取源码。在含有 `note2lecture.py` 的项目目录打开 PowerShell。后续命令都在这里运行；不需要把项目安装成 Python 包。

需要先由使用者准备以下工具：

| 工具 | 用途 | 已实测组合 |
| --- | --- | --- |
| [Python for Windows](https://www.python.org/downloads/windows/) | 运行转换程序 | Python 3.12.4 |
| [Quarto](https://quarto.org/docs/get-started/) | 使用随附 Pandoc 解析并转换文档 | Quarto 1.10.19 / Pandoc 3.10 |
| [TeX Live for Windows](https://tug.org/texlive/windows.html) | XeLaTeX 编译、中文与数学字体 | TeX Live 2024 |

上表记录已经验证的组合，不宣称其他版本均通过。Python 项目要求 3.12 或以上；首次复现可优先使用 3.12。已有这些工具时可以复用它们，新建本项目自己的 Python 环境即可。

TeX 环境需要能够运行 `xelatex` 和 `kpsewhich`，并提供 Fandol、Latin Modern 及模板所需宏包。下文的 `doctor` 会检查实际依赖，缺项时给出名称。TeX Live 的安装目录按其 [Windows 官方说明](https://tug.org/texlive/windows.html#nonascii) 使用 ASCII 字符路径。无需单独安装其他 Pandoc，也无需安装 Times New Roman、Jupyter 或 R。

Quarto 建议使用英文安装路径；已验证版本在中文安装目录下出现过模块加载错误。安装路径和是否加入 PATH 按官方安装流程选择，不需要创建本项目开发者使用过的目录联接。

普通 Markdown / Obsidian 模板还使用 TeX Live 的 FreeSerif 四种字形；含 💡 时需要 Windows 的 Segoe UI Symbol。额外字体由实际导出检查，缺项时给出文件名，不自动安装或随源包分发。特殊字符采用黑白显示，支持范围见 [字形说明](text-glyphs.md)。

## 2. 建立独立 Python 环境

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

如果使用的是已经确认版本的 Python 解释器，也可以用它执行 `-m venv .venv`。输出环境必须是本项目的新目录；不要覆盖其他项目的环境。

运行依赖只有 PyYAML 和 Pillow，版本写在 `requirements.txt`。开发测试才需要 `requirements-dev.txt`。使用完整的 Python 路径可直接运行，下面不要求激活环境或修改 PowerShell 执行策略。已有本项目 `.venv` 时，先检查其版本及依赖，不必重建。

## 3. 让程序找到现有工具

如果 Quarto 已加入 PATH，直接进入下一步。否则，在当前 PowerShell 窗口设置其实际可执行文件位置，例如：

```powershell
$env:NOTE2LECTURE_QUARTO = 'C:\Tools\Quarto\bin\quarto.exe'
```

把示例路径改成自己的安装位置，目标应是文件 `quarto.exe`。该设置只影响当前窗口；也可以在每次命令末尾添加 `--quarto '实际路径\quarto.exe'`。

确认 TeX 的命令可以找到：

```powershell
Get-Command xelatex, kpsewhich
.\.venv\Scripts\python.exe note2lecture.py doctor
```

`status: checked` 表示工具、宏包和字体检查通过。程序不会自动下载或安装缺失项。退出码可用 `$LASTEXITCODE` 查看，0 表示命令没有报告错误。

## 4. 导出第一篇公开样例

```powershell
.\.venv\Scripts\python.exe note2lecture.py check examples/01-mean.md
if ($LASTEXITCODE -eq 0) {
    .\.venv\Scripts\python.exe note2lecture.py export examples/01-mean.md -o output/my-first-lecture
}
```

成功编译后，打开 `output/my-first-lecture/lecture.pdf`。这篇使用默认 `strict` 模式，展示图片、公式、代码与引用；[公开效果对照](demo.md) 可以先看成品。

新导出返回 `status: partial` 是正常约定：结构与编译已经通过，程序仍保留内容、页面和阅读体验的人工检查项。检查 PDF 的正文、公式、图片与分页后，才能对这份固定产物做验收。`failed` 表示存在错误，查看 JSON 中的 `diagnostics`。

输出目录必须不存在；第二次尝试时换成 `output/my-first-lecture-02`。不要先删除失败目录，日志有助于定位原因。

## 5. 转换自己的笔记

普通 Markdown 显式选择 `markdown`；把下方示例路径改成实际笔记路径：

```powershell
$notePath = 'C:\Notes\我的笔记.md'
.\.venv\Scripts\python.exe note2lecture.py check $notePath --profile markdown
if ($LASTEXITCODE -eq 0) {
    .\.venv\Scripts\python.exe note2lecture.py export $notePath --profile markdown -o output/my-note-01
}
```

包含受支持双链、图片嵌入和提示框的 Obsidian 笔记使用 `--profile obsidian`。先体验仓库内原创样例：

```powershell
.\.venv\Scripts\python.exe note2lecture.py export examples/04-obsidian.md --profile obsidian -o output/my-obsidian-01
```

原笔记及图片只读。图片路径应相对于笔记文件正确；程序不自动在库中搜图或修正失效路径。跨笔记链接不等于自动合并笔记，支持边界见 [普通 Markdown](markdown-profile.md) 和 [Obsidian 扩展](obsidian-fixture.md)。

## 6. 一次选择几篇笔记

前三篇原创样例使用同一个模式，可以一起转换：

```powershell
.\.venv\Scripts\python.exe note2lecture.py batch examples/01-mean.md examples/02-projection.md examples/03-online-mean.md -o output/my-batch-01
```

按照输入顺序查看 `001/lecture.pdf`、`002/lecture.pdf`、`003/lecture.pdf`，以及根目录的 `batch-summary.json`。一篇失败后会继续其他篇；任意失败使最终退出码为 2，全部转换完成且无错误时为 0。每篇仍需人工检查。更多路径写法和字段说明见 [批处理说明](batch-export.md)。

## 7. 产物怎样使用

| 产物 | 什么时候使用 |
| --- | --- |
| `lecture.pdf` | 阅读、打印和分享讲义 |
| `lecture-source.zip` | 保存或发送可编辑、可重编译的完整源包 |
| `lecture-source/main.tex` | 调整讲义文字、公式和排版的入口 |
| `lecture-source/assets/`、`code/`、`template/` | 图片、代码正文与样式配套文件，和主文件一起保留 |
| `diagnostics.json` | 查看错误、警告及检查状态 |
| `_build/` | 排查编译问题时使用的中间文件与日志 |

只阅读时打开 PDF 即可。需要编辑 LaTeX 时，先解压整个源包，再修改 `main.tex`；代码块正文存放在 `code/`。在源包目录用 XeLaTeX 编译，详细步骤见 [输出与重编译](usage.md#4-输出与状态)。复制单独一个 `.tex` 无法替代完整源包。

## 8. 常见问题

| 现象 | 处理 |
| --- | --- |
| 找不到 Python、Quarto 或 XeLaTeX | 检查实际安装位置，重新打开终端；Quarto 可显式指定，TeX 命令须能从 PATH 找到 |
| `DEPENDENCY_MISSING` | 按诊断准备所列工具、宏包或字体，然后重新运行 `doctor` |
| `RESOURCE_MISSING` | 按原笔记引用位置检查必要图片；本地文档引用的 warning 与缺图错误含义不同 |
| `OUTPUT_EXISTS` | 换新的输出目录，已有产物不覆盖 |
| `STRUCTURE_INVALID` / `UNSUPPORTED_SYNTAX` | 根据文件、行列与说明核对输入；确认选对 profile，并查支持规则 |
| `COMPILE_FAILED` / `LAYOUT_OVERFLOW` | 按提示查看源位置与 `_build/` 日志；保留失败产物，修正后换新目录 |
| 转换完成却是 `partial` | 人工检查项尚未自动批准；查看 PDF，不要将其当作编译失败 |

本轮复现条件和结果见 [N5 复现记录](n5-validation.md)。开发者测试及页面检查工具另见 [开发验证](development.md)。
