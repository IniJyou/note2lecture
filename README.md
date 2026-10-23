# Note2Lecture

将单篇 UTF-8 Markdown 及其直接引用的本地资源，转换为中文讲义 PDF 和可编辑、可重编译的 LaTeX 源包。

当前交付：**N0 样例与输入规范**。转换器、命令入口和讲义模板尚未实现，没有已通过验收的 PDF。产品规划版本仍为 v0.2；下文的输入协议 N0.1 是本轮约定的版本，二者含义不同。

- 当前任务与下一验收点：[docs/current-work.md](docs/current-work.md)
- 产品范围与阶段：[PROJECT_PLAN.md](PROJECT_PLAN.md)
- 协作规则：[AGENTS.md](AGENTS.md)
- 三篇原创样例：[examples/README.md](examples/README.md)
- 输入语法、资源与诊断：[docs/input-spec.md](docs/input-spec.md)
- 期望输出与逐篇核对表：[docs/expected-output.md](docs/expected-output.md)
- 首套中文模板方向：[docs/template-direction.md](docs/template-direction.md)

基础转换关闭模型辅助，不依赖 MiniGPT-CN、Qwen 或 LoRA。M5 工程已收尾，模型质量未达接纳门槛；模型建议留待 N3 单独验收。

N1 再验证 Python + Quarto/Pandoc + XeLaTeX 路线，建立本项目独立环境和运行说明。目前没有可执行的转换命令，不需要为阅读 N0 样例安装任何依赖。下载、安装和 Git 写操作由用户执行。

原笔记只读。公开演示使用本项目新写的样例，不读取私人笔记库。电子书 PDF 反向提取按规划第 7.1 节保留为后续独立功能，不属于基础导出或 N0—N2 的前置条件。
