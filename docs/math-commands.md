# 数学命令支持范围

更新：2026-10-26。适用于显式选择 `--profile markdown` / `obsidian`；默认 strict 继续使用 [N0.1](input-spec.md) 的基础白名单。公式的分隔符、环境与宽度规则见 [Markdown 适配](markdown-profile.md)。

数学命令采用明确白名单；保留原始命令和参数，不猜测自定义宏的含义，也不自动下载宏包。检查遇到未知命令时，一次汇总已解析数学节点里的全部未知命令并去重，JSON 的 `related` 列出每种命令的源位置；位置有歧义时标记 `approximate`。代码示例不参加数学命令扫描。

以下是首批补齐的 **101 个命令**，随后增加 37 个，再补齐 2 个，共 140 个（不含更早已有集合）。均用带实际参数的原创公式在现有 XeLaTeX、unicode-math 与 Latin Modern Math 下编译检查，并验证 Markdown / Obsidian 到最终 TeX 的原文往返。

| 类别 | 本轮新增命令 |
| --- | --- |
| 关系符与上方说明 | `\not`、`\stackrel`、`\nleq`、`\ngeq`、`\nless`、`\ngtr`、`\asymp`、`\cong`、`\prec`、`\preceq`、`\succ`、`\succeq`、`\parallel`、`\nparallel`、`\nmid`、`\models`、`\vdash`、`\dashv`、`\bowtie`、`\subsetneq`、`\supsetneq` |
| 常用算子 | `\sinh`、`\cosh`、`\tanh`、`\coth`、`\sec`、`\csc`、`\Pr`、`\gcd`、`\deg`、`\hom`、`\ker`、`\lg`、`\limsup`、`\liminf` |
| 集合与大型运算符 | `\bigcap`、`\bigvee`、`\bigwedge`、`\bigoplus`、`\bigotimes`、`\biguplus`、`\coprod`、`\sqcup`、`\sqcap`、`\uplus`、`\complement` |
| 箭头 | `\longleftarrow`、`\longleftrightarrow`、`\Longleftarrow`、`\hookrightarrow`、`\hookleftarrow`、`\leftrightarrow`、`\nearrow`、`\searrow`、`\nwarrow`、`\swarrow`、`\updownarrow`、`\Uparrow`、`\Downarrow`、`\Updownarrow`、`\rightleftharpoons` |
| 字体与符号类别 | `\mathscr`、`\mathfrak`、`\mathnormal`、`\mathop`、`\mathrel`、`\mathbin`、`\mathord`、`\mathopen`、`\mathclose`、`\mathpunct`、`\mathinner`、`\textnormal`、`\textbf`、`\textit`、`\textsf`、`\texttt` |
| 重音与向量 | `\acute`、`\grave`、`\breve`、`\check`、`\mathring`、`\overrightarrow`、`\overleftarrow`、`\overleftrightarrow`、`\underleftarrow`、`\underrightarrow` |
| 组合数 | `\tbinom` |
| 括号与取整 | `\lfloor`、`\rfloor`、`\lceil`、`\rceil`、`\biggl`、`\biggr`、`\Biggl`、`\Biggr` |
| 间距 | `\thinspace`、`\medspace`、`\thickspace`、`\negthinspace`、`\enspace` |

本轮进一步补齐的 37 个命令：

| 类别 | 命令 |
| --- | --- |
| 积分 | `\oint`、`\iiiint`、`\idotsint`、`\oiiint` |
| 关系符 | `\leqslant`、`\geqslant`、`\lesssim`、`\gtrsim`、`\lessapprox`、`\gtrapprox`、`\doteq`、`\doteqdot`、`\triangleq`、`\eqsim`、`\approxeq`、`\lessgtr`、`\gtrless`、`\nsubseteq`、`\nsupseteq`、`\Doteq`、`\sqsubset`、`\sqsupset`、`\sqsubseteq`、`\sqsupseteq` |
| 常用符号 | `\hbar`、`\hslash`、`\imath`、`\jmath`、`\wp`、`\aleph`、`\beth`、`\gimel`、`\daleth`、`\eth`、`\varkappa` |
| 高阶重音 | `\dddot`、`\ddddot` |
| 2026-10-27 补充 | `\blacksquare`、`\xleftarrow` |

`\doteqdot` 在模板中作为同符号 `\Doteq` 的标准别名提供；`\square` / `\blacksquare` 分别由同符号 `\mdlgwhtsquare` / `\mdlgblksquare` 提供。原命令不替换。未将默认数学字体缺字的符号冒充可用支持。

此前支持的 `\frac`、`\mathbb`、`\begin{pmatrix}` 等基础命令，以及普通 Markdown 已有的反三角函数、`\boxed`、`\tag`、`\lt` / `\gt` 等继续保留。新增命令集中维护在 `src/note2lecture/math_commands.py`；完整基础集合在 `document.py` 的 `MATH_COMMANDS`。

例如，以下两种写法保留原命令交给原生 TeX 排版：

```latex
\not=
x \stackrel{\mathrm{def}}= y
```

自动分行不会把 `\not` 与紧随的关系符拆开，也不会拆分 `\stackrel` 的两个参数；字体、重音和取整括号的范围一并保护。新增关系符可正常显示，但不表示每种关系符都成为自动断点。普通超宽公式优先尝试外层关系符及明确的二元加减号，再考虑有限缩放；作用范围有歧义时不猜测，详见 [兼容说明](common-compat.md)。数学命令检查通过也不等于参数写法、整篇结构或页面排版已通过。

未知命令、自定义宏定义、文件读取及执行命令仍明确报错；不自动加载 `\usepackage`、`\require` 或运行笔记代码。数学环境和基础 `array` 列格式的限制保持，strict 不扩大支持范围。

首批命令修复及四项兼容改进分别完成 291 / 332 项历史检查，原样张均保持固定结果。2026-10-27 的数学书名、矩阵变换与空行修复完成最新 **360 项 pytest 与 Ruff**；原创两页的内容、源包和页面核对通过，三篇指定笔记共 2,132 处数学盒子预检通过。该预检没有生成私人 PDF，不代替整篇分页/页面验收。此前另一篇的引用块内列表限制仍保留。原稿只读，私人内容不进入公开样例与测试；新规则见 [矩阵兼容说明](matrix-compat.md)。
