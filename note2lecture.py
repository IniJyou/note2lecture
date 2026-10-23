r"""免安装的项目入口：.venv\Scripts\python.exe note2lecture.py --help。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from note2lecture.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
