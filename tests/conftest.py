import pytest

from note2lecture.diagnostics import NoteError
from note2lecture.tools import find_quarto


@pytest.fixture(scope="session")
def quarto():
    try:
        return find_quarto()
    except NoteError:
        pytest.skip("需要现有 Quarto；测试不自动安装。")
