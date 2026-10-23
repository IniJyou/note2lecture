"""诊断始终指向原输入，不能把编译行号冒充笔记行号。"""

from dataclasses import asdict, dataclass


@dataclass
class Diagnostic:
    code: str
    message: str
    file: str
    line: int = 1
    column: int = 1
    severity: str = "error"
    block: str = "document"
    hint: str = ""
    approximate: bool = False
    related: list | None = None

    def to_dict(self):
        return asdict(self)


class NoteError(Exception):
    def __init__(self, diagnostic: Diagnostic):
        self.diagnostic = diagnostic
        super().__init__(diagnostic.message)


class Source:
    def __init__(self, filename: str, text: str):
        self.filename = filename
        self.text = text

    def position(self, offset: int):
        offset = max(0, offset)
        return self.text.count("\n", 0, offset) + 1, offset - self.text.rfind("\n", 0, offset)

    def error(
        self, code, message, needle="", *, offset=None, block="document", hint="", related=None
    ):
        ambiguous = offset is None and bool(needle) and self.text.count(needle) > 1
        if offset is None:
            offset = self.text.find(needle) if needle else 0
        approximate = offset < 0 or ambiguous
        line, column = self.position(offset)
        raise NoteError(
            Diagnostic(
                code,
                message,
                self.filename,
                line,
                column,
                block=block,
                hint=hint,
                approximate=approximate,
                related=related,
            )
        )
