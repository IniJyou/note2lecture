"""本地桌面入口：使用本项目 Python 环境，不执行笔记代码。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from note2lecture.desktop import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
