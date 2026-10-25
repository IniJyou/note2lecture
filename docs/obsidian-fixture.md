# N2 Obsidian 样例、支持规则与验收

更新：2026-10-25。状态：**样例覆盖的基础扩展已通过工程检查，用户对提示框样张给出正面反馈，当前样式先沿用**。协议标记为 `N2-obsidian.1`。工程实测日期为 2026-10-24，本次仅登记反馈。

用户当前没有使用这些扩展的真实笔记，因此明确选择 [04-obsidian.md](../examples/04-obsidian.md) 进行适配与验收。它是专门编写的功能样例，不作为真实用户使用习惯的证据，也不要求用户为测试改变记笔记方式。

样例及文字为本项目原创，图片复用已有原创 `assets/mean-flow.png`，双链指向已有公开样例 `01-mean.md`。不读取私人笔记，不增加下载或依赖；前三篇 N0 / N1 样例保持原样。

| 覆盖项 | 样例写法 | 本轮支持规则 |
| --- | --- | --- |
| 跨笔记双链 | `[[01-mean]]` | 只检查输入目录内明确相对路径是否为现存 Markdown 文件；不读正文、不扫描或递归合并；输出名称与路径，并发出 `WIKI_NOTE_NOT_PACKAGED` 警告 |
| 带别名双链 | `[[01-mean\|算术平均的基础笔记]]` | 保留显示别名和目标记录；PDF 中不得产生虚假的可点击目标 |
| 同篇标题双链 | `[[#复核结果\|复核结果]]`、`[[#计算顺序\|计算顺序]]` | 向前、向后跳转均定位同篇正确标题，保留显示文字 |
| 本地图片嵌入 | `![[assets/mean-flow.png]]` | 只接受独占段落的 PNG/JPEG，原图字节不变；没有图题时明确使用文件名，不猜测图片含义；后续图示说明原样保留 |
| 三种普通提示框 | note、tip、warning，均有自定义题头 | 保留类别、原题头、段落和公式；排为“笔记 / 提示 / 注意”粗体题头、正体正文、轻微缩进、无框；不当成数学环境 |
| 提示框内的双链 | tip 正文中的同篇跳转 | 不能因处于引用块内而漏掉链接或正文 |
| 字面代码块 | text 围栏中的同类记号 | 逐字保留，不解析为资源或链接，不执行 |

数学与图片要继续通过源包保真检查；PDF 与可编辑 LaTeX 源包都要可独立交付。仅写出样例不等于转换成功，更不等于页面通过验收。

默认 strict、markdown 模式不自动启用这些扩展。显式运行：

```powershell
.\.venv\Scripts\python.exe note2lecture.py check examples/04-obsidian.md --profile obsidian
.\.venv\Scripts\python.exe note2lecture.py export examples/04-obsidian.md --profile obsidian -o output/obsidian-new
.\.venv\Scripts\python.exe scripts/verify_markdown.py examples/04-obsidian.md output/obsidian-new output/obsidian-review-new --profile obsidian
```

本轮实测 94 项 pytest 通过、Ruff 与 Git 空白检查通过。原创样例导出为 2 页，12 处数学正文、1 个代码块、1 幅原图、2 次同篇跳转、3 种提示框及 36 个原稿正文词段核对通过；源包 ZIP 字节一致，复制到新目录直接重编译通过。两页已实际渲染检查，未发现缺字、溢出、裁切或孤立题头。产物与检查记录在本机 Git 忽略的 `output/n2-obsidian/`，不作为真实 Obsidian 笔记体验的证明。

故障测试在临时目录构造缺失目标、丢失图片、越界路径、重复标题、未闭合双链、折叠和嵌套等输入，要求明确诊断并定位原文；损坏输入不发布 PDF 或源包。另检查关联笔记正文从未打开、代码中的记号不解析，以及同一原图同时以普通图片和嵌入引用时不覆盖用户图题。

边界：不支持跨笔记标题或块引用、整篇笔记或 PDF 嵌入、图片尺寸/别名参数、折叠/嵌套提示框、提示框内列表或其他复杂块。缺失目标为 `REF_UNDEFINED`，不唯一标题为 `REF_AMBIGUOUS`，越界路径为 `RESOURCE_PATH`，不支持的写法为 `UNSUPPORTED_SYNTAX`；不猜目标、不静默忽略。

省略 `.md` 的普通笔记名会补扩展名；含点的文件名应显式写 `.md`。带子目录的目标也必须显式给出相对路径，真实路径不得越过输入目录；不使用 Obsidian 整库搜索或“最接近”的名称匹配。同篇双链按标题原文字面匹配，标题不唯一时拒绝猜测。

转换、图片、双链和提示框的记录写入 `manifest.json` 的 `obsidian` 字段。CLI 新导出仍为 `partial`，需要逐篇检查内容和页面；本篇固定产物在工程检查与用户反馈完成后单独补记为 complete，保留两条预期的关联笔记 warning。基础规则继承 [markdown-profile.md](markdown-profile.md)，模型、代码执行及自动安装继续关闭。
