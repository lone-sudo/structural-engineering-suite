from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List


class CheckStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_CHECKED = "NOT CHECKED"
    NOT_APPLICABLE = "NOT APPLICABLE"
    WARNING = "WARNING"


@dataclass
class Check:
    name: str
    status: CheckStatus
    demand: float | None = None
    capacity: float | None = None
    unit: str = ""
    message: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.value,
            "demand": self.demand,
            "capacity": self.capacity,
            "unit": self.unit,
            "message": self.message,
        }


@dataclass
class DesignAudit:
    checks: List[Check] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def add(self, name: str, status: CheckStatus, **kwargs: Any) -> None:
        self.checks.append(Check(name=name, status=status, **kwargs))

    @property
    def overall_status(self) -> CheckStatus:
        if any(c.status == CheckStatus.FAIL for c in self.checks):
            return CheckStatus.FAIL
        if any(c.status == CheckStatus.NOT_CHECKED for c in self.checks):
            return CheckStatus.NOT_CHECKED
        if any(c.status == CheckStatus.WARNING for c in self.checks):
            return CheckStatus.WARNING
        return CheckStatus.PASS

    def as_dict(self) -> Dict[str, Any]:
        return {
            "overall_status": self.overall_status.value,
            "checks": [c.as_dict() for c in self.checks],
            "warnings": list(self.warnings),
        }
