import pytest

from note2lecture.diagnostics import NoteError, Source


def test_ambiguous_token_location_is_explicitly_approximate():
    source = Source("note.md", "相同词\n相同词\n")
    with pytest.raises(NoteError) as error:
        source.error("UNSUPPORTED_SYNTAX", "无法唯一定位", "相同词")
    assert error.value.diagnostic.approximate


def test_known_offset_is_exact_even_if_text_repeats():
    source = Source("note.md", "相同词\n相同词\n")
    with pytest.raises(NoteError) as error:
        source.error("LABEL_DUPLICATE", "第二处", offset=4)
    diagnostic = error.value.diagnostic
    assert (diagnostic.line, diagnostic.column, diagnostic.approximate) == (2, 1, False)
