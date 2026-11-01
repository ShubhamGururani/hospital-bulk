import pytest

from app.csv_parser import CSVValidationError, parse_csv, validate_csv
from tests.conftest import make_csv


def test_parses_valid_rows() -> None:
    rows = parse_csv(make_csv(3), max_rows=20)

    assert [row.name for row in rows] == ["Hospital 1", "Hospital 2", "Hospital 3"]
    assert rows[0].row == 1
    assert rows[0].phone == "555-0001"


def test_phone_is_optional() -> None:
    rows = parse_csv(b"name,address\nGeneral,1 Main St\nCity,2 Main St,\n", max_rows=20)

    assert all(row.phone is None for row in rows)


def test_handles_bom_whitespace_and_header_case() -> None:
    rows = parse_csv("﻿ Name , ADDRESS ,Phone\n  General  , 1 Main St ,\n".encode(), max_rows=20)

    assert rows[0].name == "General"
    assert rows[0].address == "1 Main St"


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (b"", "CSV is empty"),
        (b"name,phone\nGeneral,555\n", "Missing required column(s): address"),
        (b"name,address,phone\n", "CSV contains no hospital rows"),
        ("name,address\nCaf\xe9,1 St\n".encode("latin-1"), "File must be UTF-8 encoded"),
    ],
)
def test_file_level_errors(content: bytes, message: str) -> None:
    result = validate_csv(content, max_rows=20)

    assert not result.is_valid
    assert result.errors[0].row == 0
    assert result.errors[0].message == message


def test_reports_every_invalid_row() -> None:
    result = validate_csv(b"name,address\n,1 Main St\nGeneral,\nOk,3 St\nA,B,C,D\n", max_rows=20)

    assert [(error.row, error.message) for error in result.errors] == [
        (1, "'name' is required"),
        (2, "'address' is required"),
        (4, "Row has more values than columns"),
    ]
    assert result.total_rows == 4


def test_rejects_more_than_max_rows() -> None:
    with pytest.raises(CSVValidationError) as exc_info:
        parse_csv(make_csv(21), max_rows=20)

    assert exc_info.value.errors[0].message == "CSV has 21 rows; maximum is 20"
