# 本地使用与检查

本版从项目目录运行，提供 `doctor`、`check`、`export`、`batch` 四个命令；不要求安装项目为 Python 包。基础导出不加载模型，也不运行笔记代码。首次配置从 [Windows 指南](quickstart-windows.md) 开始；输入规则按所选 profile 查看。

## 1. 环境

项目使用自身 `.venv`，不借用 MiniGPT-CN 或 CS336 环境。下载、安装和 Git 写操作仍由用户执行，除非另行明确授权。

已验证组合：Python 3.12.4、Quarto 1.10.19（内置 Pandoc 3.10）、XeTeX 0.999996 / TeX Live 2024。转换使用所选 Quarto 随附的 Pandoc，不需要另外安装 Pandoc。导出运行依赖实测版本保存在 [requirements.txt](../requirements.txt)，开发工具另见 [开发验证](development.md)。新环境准备方式为：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

字体使用 TeX Live 提供的 Fandol 宋/黑/仿宋与 Latin Modern。字体文件不随源包分发，实际字体摘要保存在每份 `manifest.json`。

普通模式的正文希腊字母及 ✓、⚠、❌ 使用 FreeSerif；💡 使用 Windows 已有的 Segoe UI Symbol，统一按黑白显示。额外字体在导出时检查，原稿、数学和代码不改写；具体范围与缺字定位见 [特殊字符说明](text-glyphs.md)。

首套“清简讲义 v0.1”已确认：正文约 11 pt、行距参数 1.4，数学环境为粗体题头、正体正文、无框无线。当前公开样张与源包见 [效果对照](demo.md)；新文档仍按下面的状态规则逐篇检查。

超宽普通公式在竖版内先尝试外层关系符及明确的二元加减号分行，再考虑有限缩放，保留原公式与运算次序；列表内按实际剩余行宽排版。仍无法安全排下则报告位置和尺寸。正文符号、手写或显式标签公式的边界见 [兼容规则](common-compat.md)。

## 2. Quarto 路径

程序优先使用命令的 `--quarto` 参数，其次为环境变量 `NOTE2LECTURE_QUARTO`、PATH；都没有时检查项目 `.cache/quarto/bin/quarto.exe`。

Quarto 应安装在英文路径，并使用自己的实际安装位置；不依赖开发者的目录联接或特定盘符。例如在当前 PowerShell 窗口设置：

```powershell
$env:NOTE2LECTURE_QUARTO = 'C:\Tools\Quarto\bin\quarto.exe'
```

把示例值改为自己的可执行文件。转换使用 Quarto 随附的 Pandoc；本项目不会创建联接、改写 PATH、下载安装工具或自动准备字体。

## 3. 命令

在项目目录运行，或使用入口脚本及输入文件的绝对路径。以下输出目录必须尚不存在；重新导出请换新目录。

```powershell
.\.venv\Scripts\python.exe note2lecture.py doctor
.\.venv\Scripts\python.exe note2lecture.py check examples/01-mean.md
.\.venv\Scripts\python.exe note2lecture.py export examples/01-mean.md -o output/my-first-lecture
```

非 PATH 的英文 Quarto 路径可显式指定，例如：

```powershell
.\.venv\Scripts\python.exe note2lecture.py export examples/02-projection.md -o output/projection-new --quarto 'D:\Quarto\bin\quarto.exe'
```

`doctor` 只检查已有工具版本、所需宏包和字体文件，不证明某篇文档能编译。`check` 检查输入与资源，不生成 PDF。`export` 创建独立目录，写入 PDF、完整源包目录、源包 ZIP、诊断与构建日志。

默认 `strict` 继续使用 N0.1。普通 Markdown 可显式选择适配模式，规则见 [markdown-profile.md](markdown-profile.md)：

```powershell
.\.venv\Scripts\python.exe note2lecture.py check '.\private\note.md' --profile markdown
.\.venv\Scripts\python.exe note2lecture.py export '.\private\note.md' --profile markdown -o output/real-note-new
```

该模式支持从首行 H1 提取书名、提升正文标题层级、生成缺少的标题和图片标签、转换空 HTML 锚点及同篇链接、保留无表题表格。正文接受六级标题，四至六级独立成行并保留书签，目录默认到二级。列表最多四层，支持数字、字母和罗马编号，条目可含多段正文及已有支持的其他块。常见积分（含 `\oint`）等命令见 [数学命令清单](math-commands.md)。没有作者不补写，手写章节号保留且不叠加自动编号。本地文档引用只作为文字与路径保留，发出 warning，不会打开或合并被引用文档；PNG/JPEG 仍按资源规则检查并打包。

H1 书名中的行内数学现在经过受控渲染，封面/页眉显示数学，元数据用源码纯文本表示；闭合 `$$` 内部空行保留原文，只在排版副本中作为空白处理。带说明的矩阵变换可在外层箭头或已知带注关系符处分行，支持标准证明结束符 `\blacksquare`。边界与验收见 [矩阵兼容说明](matrix-compat.md)。

默认有序列表按起始编号连续递增，或将统一重复标记（例如全部 `1.`）作为自动编号。跳号、重复混用和前导零返回 `LIST_NUMBERING`。确认要逐项保留原题号时，在检查与导出命令上都加 `--list-numbering preserve`；例如：

```powershell
.\.venv\Scripts\python.exe note2lecture.py check '.\private\note.md' --profile markdown --list-numbering preserve
.\.venv\Scripts\python.exe note2lecture.py export '.\private\note.md' --profile markdown --list-numbering preserve -o output/source-numbers-new
```

该选项连同嵌套列表逐项保留源标签，并记录预期警告。详细边界见 [兼容规则](common-compat.md)。strict 不接受此选项。

样例覆盖的双链、图片嵌入及 note/tip/warning 提示框需显式选择 obsidian 模式；详细边界见 [obsidian-fixture.md](obsidian-fixture.md)：

```powershell
.\.venv\Scripts\python.exe note2lecture.py check examples/04-obsidian.md --profile obsidian
.\.venv\Scripts\python.exe note2lecture.py export examples/04-obsidian.md --profile obsidian -o output/obsidian-new
```

跨笔记双链仅检查目录内明确目标是否存在，保留名称和路径、发出 warning，不读或合并正文；同篇标题双链转换为 PDF 跳转。无图题的图片嵌入使用文件名作图题。提示框保留原题头、正文和公式，采用无框样式，不转换为数学环境。

### 选定文件批处理

```powershell
.\.venv\Scripts\python.exe note2lecture.py batch examples/01-mean.md examples/02-projection.md examples/03-online-mean.md -o output/sample-batch-01
```

`batch` 复用单篇导出，默认 `strict`，也支持共同的 `--profile markdown` / `obsidian` 与 `--quarto`。只接收明确指定的文件；每篇写入编号目录，支持不同目录的同名文件。一篇失败后继续处理其余项，批次根目录保存 `batch-summary.json`；根目录必须不存在。路径清单、状态和汇总字段见 [batch-export.md](batch-export.md)。

全部转换完成且无失败项时退出 0，状态仍为 `partial`；任意一项失败退出 2，汇总给出各自结果和产物位置。不要仅根据批次退出码判断每篇是否已完成内容与页面验收。

## 4. 输出与状态

```text
output/my-first-lecture/
  lecture.pdf
  lecture-source.zip
  lecture-source/
    main.tex                 编辑正文与排版的入口
    assets/                  摘要命名的原图字节
    code/                    代码原文（若有），编辑这里改变代码内容
    template/                讲义样式与生成时的 Lua 过滤器
    normalized.md            工作副本，非原笔记
    render-config.yml        受控渲染配置
    manifest.json            内容、工具、字体与资源记录
    source-map.json          编译行号到原笔记块的近似映射
    README.md                源包独立重编译说明
  diagnostics.json
  _build/                    构建日志、中间文件及 Quarto 缓存
```

源包还保留生成用的 `main.qmd` 和最小 `_quarto.yml`。重新编译 `main.tex` 不依赖它们、原笔记、原资源目录、Quarto、Python 或模型；只需预先准备的 XeLaTeX、宏包与字体。代码采用 `VerbatimInput` 排版，原始代码单独可编辑，TeX 结束记号也作为字面量显示。

首次在全新目录编译，或正文变化影响目录、分页时，建议在源包目录运行三轮：

```powershell
xelatex -no-shell-escape -halt-on-error -interaction=nonstopmode main.tex
xelatex -no-shell-escape -halt-on-error -interaction=nonstopmode main.tex
xelatex -no-shell-escape -halt-on-error -interaction=nonstopmode main.tex
```

检查 `main.log`，若仍提示 `Rerun` 则继续编译，直到目录和引用收敛。验收脚本会等待 `.aux`、`.toc`、`.out` 稳定且无重编译提示，最多四轮；不能只凭两轮退出码判定目录页码正确。

CLI 输出 JSON；检查或编译成功退出 0，有错误退出 2。`export` 即使编译成功，也保留 `partial` 和未完成的内容/页面检查状态，不自动宣称完整验收；存在编译、资源、缺字、未定义引用或溢出错误时为 `failed`。固定样例的实际工程验收另见 [N1 验收记录](n1-validation.md)，不把它泛化为任意输入都已检查。

“缺少公式保护标记”表示程序检测到中间输出不完整，应排查工具调用和后端；这不等于原笔记存在未闭合公式。保留失败目录供检查，修复后换新输出目录重试，保护检查继续保留。

重复标签报告原文两处位置；有歧义的文本定位与 TeX 映射标为 `approximate`。定位精度不够时，应同时查看 `source-map.json`、原文与构建日志。输出冲突不改旧目录，仅在终端报告 `OUTPUT_EXISTS`。

Quarto 仅生成 LaTeX，再由程序直接运行 XeLaTeX 至少两轮、最多三轮。配置关闭 Quarto 自动安装、代码执行；XeLaTeX 使用 `-no-shell-escape`。失败日志保留，不静默换后端、字体或输入语义。

## 5. 工程检查与支持范围

开发环境准备、测试和内容/页面核对见 [开发验证](development.md)。普通导出只安装两个 Python 运行依赖；Poppler、pytest 与 Ruff 用于开发检查。

当前支持明确语法的单篇 Markdown 和明确文件清单的批量导出，各篇独立生成产物。[N5 复现记录](n5-validation.md) 说明本轮公开演示的验证条件；[Markdown 适配](markdown-profile.md) 与 [Obsidian 扩展](obsidian-fixture.md) 说明语法边界。新文档仍须逐篇检查，固定样例的通过结论不泛化到任意输入。
