# Note2Lecture v0.1.0

Windows 本地源码版，首次使用配置好环境后，可双击 `Start Note2Lecture.cmd` 打开桌面窗口。规划文档版本仍为 v0.2，与软件版本 v0.1.0 是两回事。

## 这版提供什么

Note2Lecture 将明确选定的 UTF-8 Markdown 与本地图片转换为中文 PDF 讲义，并提供可编辑、可用 XeLaTeX 重编译的完整源包。面向 Windows 本地使用，包含命令行、批处理和桌面窗口。

- 清简讲义模板：A4、11 pt、1.4 行距，Fandol 中文与 Latin Modern 西文/数学，教材式无框数学环境。
- strict、markdown、obsidian 三种输入模式；常用正文、标题、列表、数学、代码、基础图表与受支持的 Obsidian 扩展。
- 单篇错误定位和批处理失败隔离；检查原稿位置、缺图、数学命令、编译缺字与溢出。
- Windows GUI：原生文件选择、浅深色、检查与导出、当前会话任务记录、停止后续和结果打开。
- 配置一次环境后，可双击根目录 `Start Note2Lecture.cmd` 启动；自动使用项目 `.venv`，失败时中文提示并保留本机日志。
- 原稿与图片只读，代码不执行，基础转换关闭模型；输出新建目录，保留旧结果。

## 开始使用

源码目录中运行，无需先 `pip install .`。准备 Python、Quarto、XeLaTeX、必要宏包和字体；GUI 另需 WebView2 Runtime。安装和首次转换见 [Windows 指南](https://github.com/IniJyou/note2lecture/blob/v0.1.0/docs/quickstart-windows.md)，成品与原稿见 [公开效果对照](https://github.com/IniJyou/note2lecture/blob/v0.1.0/docs/demo.md)。

当前验收组合与复现范围见 [候选验收](https://github.com/IniJyou/note2lecture/blob/v0.1.0/docs/release-candidate.md)。早期 4 篇演示保持原始快照，新版首次体验样例和 GUI 截图单独记录。

## 已知限制

- 已验收 Windows；同机独立环境复现不等同其他电脑、全新系统或其他操作系统通过。
- 原稿必须在支持范围内。数学命令受控，不猜测任意宏；超宽公式无法安全排下时停止并给出诊断。
- 本地文档链接只保留说明与路径，不读取、合并或打包目标；直接引用的受支持图片会打包。
- `partial` 是待人工内容/页面检查，不是自动验收通过。原始 JSON 不因人工确认而改写。
- GUI 的右侧是模板示意；任务历史仅保留当前会话 10 项；停止等待当前文件完成，不中断正在编译的单篇。
- 当前从源码运行，不含独立 EXE、一键安装器、自动更新或自动依赖安装。Quarto、TeX 和字体由使用者准备。
- HTML、Word/EPUB、模型辅助和电子书 PDF 反向提取尚未进入本次交付。

## 许可与第三方资源

本版尚未设置覆盖全项目的代码许可证。样例与图片的展示、复制和修改授权见 [说明](https://github.com/IniJyou/note2lecture/blob/v0.1.0/examples/README.md)；字体、第三方工具和模型不随源码或讲义源包分发。
