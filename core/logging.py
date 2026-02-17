import logging
from typing import List, Tuple


class ExportLogger:
    """Collects log messages during export for UI display."""

    def __init__(self, max_messages: int = 500):
        self.max_messages = max_messages
        self._messages: List[Tuple[str, str]] = []  # (level, message)
        self._logger = logging.getLogger("io_export_urho3d")

    def info(self, msg: str) -> None:
        self._log("INFO", msg)

    def warning(self, msg: str) -> None:
        self._log("WARNING", msg)

    def error(self, msg: str) -> None:
        self._log("ERROR", msg)

    def critical(self, msg: str) -> None:
        self._log("CRITICAL", msg)

    def _log(self, level: str, msg: str) -> None:
        if len(self._messages) < self.max_messages:
            self._messages.append((level, msg))
        self._logger.log(getattr(logging, level), msg)

    @property
    def messages(self) -> List[Tuple[str, str]]:
        return self._messages

    @property
    def has_errors(self) -> bool:
        return any(lvl in ("ERROR", "CRITICAL") for lvl, _ in self._messages)

    @property
    def error_count(self) -> int:
        return sum(1 for lvl, _ in self._messages if lvl in ("ERROR", "CRITICAL"))

    @property
    def warning_count(self) -> int:
        return sum(1 for lvl, _ in self._messages if lvl == "WARNING")

    def clear(self) -> None:
        self._messages.clear()
