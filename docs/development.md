# 开发与工程检查

普通用户从 [Windows 首次使用指南](quickstart-windows.md) 开始。这里的 pytest、Ruff、Poppler 与验收脚本供开发检查使用，不是基础导出的全部运行依赖。

## 独立环境与依赖

在项目目录、已有本项目独立环境的条件下，由使用者执行：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q --basetemp=tmp/pytest-new-run
.\.venv\Scripts\python.exe -m ruff check .
```

`requirements-dev.txt` 包含 `requirements.txt` 的两个运行依赖，以及已记录版本的测试工具。临时目录必须使用新名称，保留旧诊断。项目从源码目录运行，`pyproject.toml` 记录依赖范围与测试配置，当前不把 `pip install .` 作为已验收的安装方式。

## 真实转换与源包检查

已有 Quarto、XeLaTeX、字体与宏包后，可以在全新目录运行：

```powershell
.\.venv\Scripts\python.exe scripts/verify_n1.py output/n1-new-check
.\.venv\Scripts\python.exe scripts/verify_batch.py output/batch-review-new
```

检查已经存在的单篇产物：

```powershell
.\.venv\Scripts\python.exe scripts/verify_markdown.py examples/04-obsidian.md output/obsidian-new output/obsidian-review-new --profile obsidian
```

该脚本只读取指定原稿及必要图片，核对原稿、数学、代码、PDF 正文、标签、源包 ZIP，并复制到新目录重编译。不会重新导出、打开本地文档链接或自动将页面检查设为通过。

脚本使用现有 `pdfinfo`、`pdftotext` 和 `pdftoppm` 做工程核对与页面渲染。它们可以由开发者另行准备，普通导出不依赖 Poppler。自动检查后仍须实际查看页面，检查缺字、溢出、裁切、分页、页眉页码与图表。

## 状态与实测边界

CLI 的运行结果与人工验收记录分别保存。固定产物通过后，不应直接修改原始 `partial` / `failed` 报告来冒充程序自动验收；用户阅读反馈需指向当时的产物摘要。

新环境验证应说明目录、Python 环境和系统工具的隔离范围。同一台电脑上的全新 Python 环境仍共享系统 Quarto 与 TeX，不能据此宣称另一台机器或其他操作系统已通过。

在 Codex Windows 沙箱中，Quarto 缓存数据库曾触发权限限制，实际渲染由已授权的沙箱外进程执行。这不要求普通用户以管理员运行终端，不应通过改动其他项目环境解决。

原稿、私人 PDF、日志、缓存与权重留在 Git 忽略目录。公开演示只使用本项目原创样例；发布材料须从已检查固定产物复制并核对摘要，生成过程不执行笔记代码。
