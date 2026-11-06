"""Small parsing helpers of the reader, on text as Windows OCR really gives it."""
import pytest

import reader


@pytest.mark.parametrize("text,expected", [
    ("152 (142+10)", (152, 142)),
    ("1 52 (1 42+1 0)", (152, 142)),     # OCR puts a space after every 1
    ("32 (30+2)", (32, 30)),
    ("4", (4, 4)),
    ("", (None, None)),
])
def test_stat_number(text, expected):
    assert reader.stat_number(text) == expected
