import logging
from datetime import datetime, timezone
from pathlib import Path

from src.backend.logging_handlers import DateStampedFileHandler


def test_date_stamped_file_handler_creates_expected_path(tmp_path) -> None:
    current = datetime(2024, 5, 26, 12, 34, 56, tzinfo=timezone.utc)
    handler = DateStampedFileHandler(
        directory=tmp_path / "app",
        prefix="app",
        current_time=current,
        encoding="utf-8",
    )
    try:
        expected_dir = (tmp_path / "app" / "2024-05-26").resolve()
        expected_file = expected_dir / "app_2024-05-26_08-34-56_EDT.log"
        file_path = Path(handler.baseFilename)
        assert file_path == expected_file
        assert file_path.exists()

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname=__file__,
            lineno=0,
            msg="hello world",
            args=(),
            exc_info=None,
        )
        handler.emit(record)

        contents = file_path.read_text(encoding="utf-8")
        assert "hello world" in contents
    finally:
        handler.close()


def test_handler_derives_prefix_from_filename(tmp_path) -> None:
    current = datetime(2023, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    handler = DateStampedFileHandler(
        filename=tmp_path / "custom.log",
        prefix=None,
        current_time=current,
    )
    try:
        expected_dir = (tmp_path / "2023-01-01").resolve()
        expected_file = expected_dir / "custom_2023-01-01_22-04-05_EST.log"
        file_path = Path(handler.baseFilename)
        assert file_path == expected_file
        assert file_path.exists()
    finally:
        handler.close()
