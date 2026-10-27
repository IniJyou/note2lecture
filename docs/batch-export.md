# N4 第一项：选定文件批量导出

批处理将明确指定的每篇 Markdown 分别转换为 PDF 和可编辑 LaTeX 源包，复用现有单篇导出。按命令中的顺序逐篇执行；使用一个共同的输入模式与 Quarto 配置。原稿只读，笔记代码不执行，模型关闭。

## 1. 使用

已经准备好独立环境和现有工具后，可直接选择三篇公开样例：

```powershell
.\.venv\Scripts\python.exe note2lecture.py batch examples/01-mean.md examples/02-projection.md examples/03-online-mean.md -o output/sample-batch-01
```

普通 Markdown 使用 `--profile markdown`；样例覆盖的 Obsidian 扩展使用 `--profile obsidian`。与单篇命令一致，默认是 `strict`。一批内需要不同模式时，分批运行。

普通模式需要逐项保留源题号时，可加共同的 `--list-numbering preserve`，逐篇传给单篇转换器；默认自动编号遇到跳号等先诊断，不静默重排。各文件需要不同策略时分批运行，规则见 [兼容说明](common-compat.md)。

文件较多时可以在 PowerShell 中明确列出路径，替换成你实际选定的文件：

```powershell
$notes = @(
    '.\private\第一篇.md'
    '.\private\专题 乙\第二篇.md'
    '.\private\专题 丙\第一篇.md'
)
.\.venv\Scripts\python.exe note2lecture.py batch @notes --profile markdown -o output/my-batch-01
```

`-o` 必须指向尚不存在的目录。可以使用 `--quarto` 指定已经安装的 Quarto；不自动下载、安装或执行 Git 操作。输入必须是明确的 `.md` 文件，不接受目录作为扫描指令，也不展开程序收到的通配符。

不同目录里的同名笔记可以分别导出。同一路径重复指定，或不同路径解析为同一文件时，重复项报告 `INPUT_DUPLICATE`，保留它在清单中的位置；其他项继续处理。

## 2. 产物

```text
output/my-batch-01/
  batch-summary.json       输入清单、逐篇结果、相对产物路径和批次统计
  001/                     命令中的第 1 篇
    lecture.pdf
    lecture-source.zip
    lecture-source/
    diagnostics.json
    _build/
  002/                     命令中的第 2 篇
    diagnostics.json       本项失败时仍保存原因；可能保留部分构建材料
  003/                     命令中的第 3 篇
    ...
```

编号目录避免文件同名、Windows 保留文件名和标题过长造成冲突。笔记原名与完整输入路径记录在本机 `batch-summary.json` 中，`items[].output` 和 `items[].artifacts` 使用相对于批次根目录的路径。这些本机记录可能包含私人路径，不应直接上传。

每篇的 PDF、源包结构与单篇 `export` 相同，仍可编辑 `lecture-source/main.tex` 并独立重编译；说明见 [usage.md](usage.md)。批处理不合并章节或跨笔记编号，直接引用的资源仍由该篇已有规则处理。

## 3. 状态和错误

批次汇总在开始及每篇结束后保存。终端进度写到 stderr，最终 JSON 写到 stdout；可按需将 stdout 保存到另一个新文件。

| 字段 | 含义 |
| --- | --- |
| `summary.total` | 明确指定的输入项数量，包含错误和重复项 |
| `summary.converted` | 未被单篇检查判为失败的已转换数量，仍须内容与页面验收 |
| `summary.failed` | 输入、资源、依赖、编译或版面诊断失败数量 |
| `summary.pending` | 尚未完成的输入项数量；正常结束为 0 |
| `summary.review_pending` | 已转换但内容、页面或风格检查仍未全部完成的数量 |
| `items` | 已处理项的输入、输出、状态、各项检查及完整诊断 |

- 全部转换完成且没有失败项：批次 `status=partial`，退出码 **0**；新生成的单篇仍保留待验收状态。
- 任意一篇失败：继续处理其余项，最终批次 `status=failed`，退出码 **2**；成功转换的产物保留，汇总给出各自状态。
- Ctrl+C 中断：尽可能保存 `status=interrupted`，退出码 **130**；尚未完成的项留在 `pending`，不作为完成项计数。当前项可能留有部分构建材料，没有自动续跑功能。
- 已有批次根目录：直接报告 `OUTPUT_EXISTS`，退出码 **2**，不修改旧汇总或产物。

某篇即使留下 PDF，只要有失败诊断，就仍计入 `failed`。输出文件存在不能替代内容与版面验收；编号目录里也可能包含失败时保留的中间材料。程序意外终止时，最后一次保存的汇总可能仍为 `running`，不能视为整批完成。

单篇诊断通常位于对应编号目录的 `diagnostics.json`；若目标冲突或无法另存单篇报告，应查看批次汇总中的完整诊断。批次根目录自身不可读写时，命令报告 `BATCH_IO_FAILED`，应先检查路径和权限。

## 4. 验收范围

公开回归测试覆盖失败后继续、同名与中文空格路径、重复输入、输入边界、已有输出保护、单篇意外异常、版面失败计数、中断状态和 CLI 退出码。端到端检查入口：

```powershell
.\.venv\Scripts\python.exe scripts/verify_batch.py output/batch-review-new
```

该脚本仅复制本项目原创样例及其明确资源到新的验收目录，构造“三项中间一项出错”的批次，检查真正的 PDF / 源包、原稿与图片摘要、单篇源包迁移重编译及旧输出保护，并渲染全部页面。它不自动宣称页面检查通过，仍须实际查看渲染图片。

本次只交付批量 PDF / LaTeX 导出。HTML、Word、EPUB、本地界面和电子书 PDF 反向提取分别安排；新批次不继承某份固定样例已通过的人工验收结论。
