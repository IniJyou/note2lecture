# Note2Lecture

将单篇 UTF-8 Markdown 及其直接引用的本地资源，转换为中文讲义 PDF 和可编辑、可重编译的 LaTeX 源包。

当前交付：**N1 已完成，N2 已交付基础适配及首轮验收样例，正在推进后续长文回归**。提供普通 Markdown 与基础 Obsidian 语法适配、单篇命令入口、输入与资源诊断、PDF 及可独立重编译的 LaTeX 源包。首套采用 Fandol＋Latin Modern、11 pt、1.4 行距和教材式无框数学环境，提示框样式先沿用。产品规划仍为 v0.2；默认 strict 使用 N0.1，markdown 与 obsidian 模式须显式选择，不承诺任意 Obsidian 语法。

2026-10-25 后续真实笔记回归补充了缩进公式、多段列表、反斜线数学分隔符和目录占位符适配，并修复列表题头分页；新样本 18 页的内容与页面工程检查完成，阅读反馈待确认。支持边界与实测记录见下方文档。

同日长文回归补充了行内公式首尾空格与段内软换行、常见数学命令、手写编号、括号列表和数学书签，并修复本机工具命令的长输出截断。根据最新阅读反馈，超宽普通公式改为在竖版内按外层关系符分行，公式原文不变；不能安全分行或仍超宽则明确报错。150 项测试通过，原创样张的 2 页、内容和独立源包已验证；用户已导出私人长文新版并认可阅读效果，整篇内容与助手逐页检查仍待完成。

- 当前任务与下一验收点：[docs/current-work.md](docs/current-work.md)
- 产品范围与阶段：[PROJECT_PLAN.md](PROJECT_PLAN.md)
- 协作规则：[AGENTS.md](AGENTS.md)
- 三篇原创样例：[examples/README.md](examples/README.md)
- 输入语法、资源与诊断：[docs/input-spec.md](docs/input-spec.md)
- 期望输出与逐篇核对表：[docs/expected-output.md](docs/expected-output.md)
- 首套中文模板方向：[docs/template-direction.md](docs/template-direction.md)
- 使用与环境说明：[docs/usage.md](docs/usage.md)
- N1 实测与限制：[docs/n1-validation.md](docs/n1-validation.md)
- 普通 Markdown 适配：[docs/markdown-profile.md](docs/markdown-profile.md)
- N2 首轮实测与限制：[docs/n2-validation.md](docs/n2-validation.md)
- Obsidian 基础扩展与样例检查：[docs/obsidian-fixture.md](docs/obsidian-fixture.md)

基础转换关闭模型辅助，不依赖 MiniGPT-CN、Qwen 或 LoRA。用户于 2026-10-25 决定先跳过 N3，下一阶段转向 N4 使用与格式扩展，首项实现尚未启动。M5 模型质量未达接纳门槛，模型能力保留为后续可选任务，届时单独验收。

已准备独立 `.venv`、Quarto 和 XeLaTeX 的本地环境可运行：

```powershell
.\.venv\Scripts\python.exe note2lecture.py doctor
.\.venv\Scripts\python.exe note2lecture.py check examples/01-mean.md
.\.venv\Scripts\python.exe note2lecture.py export examples/01-mean.md -o output/my-lecture
```

输出目录必须尚不存在；依赖准备、Quarto 路径和源包重编译见使用说明。导出不自动下载或安装。程序新导出的结果保持 `partial`，等待内容与页面检查；固定样例已完成的检查单独记录，不能泛化到任意笔记。下载、安装和 Git 写操作仍由用户执行。

原笔记只读。公开演示使用本项目新写的样例；私人笔记仅按用户指定读取，私人原稿与产物不加入公开仓库。电子书 PDF 反向提取按规划第 7.1 节保留为后续独立功能，不属于基础导出或 N0—N2 的前置条件。
