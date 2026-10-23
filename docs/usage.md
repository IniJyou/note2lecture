# N1 本地使用与检查

本版从项目目录运行，提供 `doctor`、`check`、`export` 三个命令；不要求安装项目为 Python 包。基础导出不加载模型，也不运行笔记代码。输入范围见 [N0.1 规范](input-spec.md)。

## 1. 环境

项目使用自身 `.venv`，不借用 MiniGPT-CN 或 CS336 环境。下载、安装和 Git 写操作仍由用户执行，除非另行明确授权。

本轮实际组合：Python 3.12.4、Quarto 1.10.19（内置 Pandoc 3.10）、XeTeX 0.999996 / TeX Live 2024。注意：转换使用 Quarto 内置 Pandoc，不是 PATH 中独立的 Pandoc 3.12.1。Python 依赖实测版本保存在 [requirements-dev.txt](../requirements-dev.txt)。新环境准备方式为：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

字体固定为 TeX Live 已有的 Fandol 宋/黑/仿宋与 Latin Modern。本轮没有安装思源字体；这是 N0 允许的首轮已备字体方案，不能当成思源字体样张。字体文件不随源包分发，实际字体摘要保存在每份 `manifest.json`。

首套“清简讲义 v0.1”已确认：正文约 11 pt、行距参数 1.4，数学环境为粗体题头、正体正文、无框无线。Times New Roman 仅做过独立对照，用户最终选择保留 Latin Modern，不需要为本模板准备 Times 字体。定稿样张与源包在本机 `output/n1-approved/`；新文档仍按下面的状态规则逐篇检查。

## 2. Quarto 路径

程序优先使用命令的 `--quarto` 参数，其次为环境变量 `NOTE2LECTURE_QUARTO`、PATH；都没有时检查项目 `.cache/quarto/bin/quarto.exe`。

本机最初安装在 `D:\工具\Quarto`，实测 Quarto 1.10.19 从该路径渲染时出现 Lua 模块路径乱码。交付检查时工具已位于 `D:\Tools\Quarto`，项目 `.cache/quarto` 英文目录联接已更新到这个实际位置；旧联接保留为 `.cache/quarto-original-path`。联接被 Git 忽略，不是仓库依赖，助手没有移动或复制安装。新环境建议使用纯英文的 Quarto 安装路径。

如果需要重建本机入口，由用户执行（仅在目标不存在时）：

```powershell
New-Item -ItemType Directory -Path .cache -Force
New-Item -ItemType Junction -Path .cache\quarto -Target 'D:\Tools\Quarto'
```

不要把 `.cache` 中的联接目录递归复制或清理到安装目录。程序不会自动创建联接、修改 PATH 或安装软件。

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

在源包目录运行两次：

```powershell
xelatex -no-shell-escape -halt-on-error -interaction=nonstopmode main.tex
xelatex -no-shell-escape -halt-on-error -interaction=nonstopmode main.tex
```

CLI 输出 JSON；检查或编译成功退出 0，有错误退出 2。`export` 即使编译成功，也保留 `partial` 和未完成的内容/页面检查状态，不自动宣称完整验收；存在编译、资源、缺字、未定义引用或溢出错误时为 `failed`。固定样例的实际工程验收另见 [N1 验收记录](n1-validation.md)，不把它泛化为任意输入都已检查。

重复标签报告原文两处位置；有歧义的文本定位与 TeX 映射标为 `approximate`。定位精度不够时，应同时查看 `source-map.json`、原文与构建日志。输出冲突不改旧目录，仅在终端报告 `OUTPUT_EXISTS`。

Quarto 仅生成 LaTeX，再由程序直接运行 XeLaTeX 至少两轮、最多三轮。配置关闭 Quarto 自动安装、代码执行；XeLaTeX 使用 `-no-shell-escape`。失败日志保留，不静默换后端、字体或输入语义。

## 5. 开发验证

```powershell
.\.venv\Scripts\python.exe -m pytest -q --basetemp=tmp/pytest-new-run
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe scripts/verify_n1.py output/n1-new-check
```

测试的 `--basetemp` 和端到端验收目录应使用新的名称，保留已有诊断产物。端到端脚本使用 `pdfinfo`、`pdftotext` 核对页数与正文；它们属于开发验收工具，不是导出运行依赖。PDF 仍需用 Poppler 渲染并逐页查看，文本提取不能证明版面正确。

在 Codex Windows 沙箱内，Quarto 缓存数据库会触发权限限制，因此本轮实际渲染在沙箱外运行；这不等于用户普通终端也需要管理员权限。自动审批如拒绝操作应明确报告，不通过修改系统或其他项目环境绕过。

当前边界仍是单篇明确语法的 Markdown。常见 Obsidian 扩展留 N2，模型建议留 N3，电子书 PDF 反向提取按规划第 7.1 节另行安排。首套模板的字体、正文密度和数学环境风格已由用户确认，定稿样张见 `output/n1-approved/`；新文档仍需逐篇检查。
