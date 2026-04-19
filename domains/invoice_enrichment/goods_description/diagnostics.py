from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

DiagnosticSeverity = Literal["info", "warning", "error", "critical"]


@dataclass(frozen=True, slots=True)
class Diagnostic:
    stage: str
    message: str
    severity: DiagnosticSeverity = "warning"
    line_no: int | None = None
    field: str | None = None

    def to_dict(self) -> dict[str, object]:
        data: dict[str, object] = {
            "stage": self.stage,
            "severity": self.severity,
            "message": self.message,
        }
        if self.line_no is not None:
            data["line_no"] = self.line_no
        if self.field:
            data["field"] = self.field
        return data

    def to_warning_message(self) -> str:
        prefix = f"line {self.line_no}: " if self.line_no is not None else ""
        field = f"{self.field}: " if self.field else ""
        return f"{prefix}{field}{self.message}"


@dataclass(slots=True)
class Diagnostics:
    items: list[Diagnostic] = field(default_factory=list)

    def add(
        self,
        *,
        stage: str,
        message: str,
        severity: DiagnosticSeverity = "warning",
        line_no: int | None = None,
        field: str | None = None,
    ) -> None:
        self.items.append(
            Diagnostic(
                stage=stage,
                severity=severity,
                line_no=line_no,
                field=field,
                message=message,
            )
        )

    def extend(self, diagnostics: list[Diagnostic]) -> None:
        self.items.extend(diagnostics)

    def to_dicts(self) -> list[dict[str, object]]:
        return [item.to_dict() for item in self.items]

    def warning_messages(self) -> list[str]:
        return [item.to_warning_message() for item in self.items]
