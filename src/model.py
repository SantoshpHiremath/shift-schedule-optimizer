"""
model.py
--------

Data model for a small, real nurse/staff rostering problem -- the
scheduling domain this project targets (built to close a mathematical-
optimization gap identified against Daphos's "ShiftPlan" posting, whose
core ask is exactly this: the Nurse Rostering Problem, described in the
posting itself as NP-hard).

Kept intentionally small and honest: 3 shift types per day, a two-week
horizon, and a handful of real, named constraints (minimum staffing,
qualification requirements, one-shift-per-day, minimum rest between a
closing and an opening shift, a maximum-consecutive-working-days cap,
and a weekly max-hours cap derived from contract type) -- not a claim of
covering the full German Arbeitszeitgesetz or a real hospital's actual
staffing rules, which is a much larger and more legally complex problem
than a single project could honestly claim to solve.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ShiftType(str, Enum):
    EARLY = "EARLY"   # 06:00-14:00
    LATE = "LATE"      # 14:00-22:00
    NIGHT = "NIGHT"    # 22:00-06:00


class ContractType(str, Enum):
    FULL_TIME = "FULL_TIME"   # max 5 shifts/week
    PART_TIME = "PART_TIME"   # max 3 shifts/week


@dataclass(frozen=True)
class Staff:
    staff_id: str
    name: str
    contract: ContractType
    qualified_for_night: bool = True
    # Days (0-indexed into the horizon) this staff member has requested
    # off. A *soft* preference -- the solver will try to honor it, but
    # will violate it rather than produce an infeasible schedule if
    # honoring every request is impossible given minimum staffing.
    requested_days_off: tuple[int, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class SchedulingProblem:
    staff: tuple[Staff, ...]
    num_days: int
    min_staff_per_shift: dict  # {ShiftType: int} -- same minimum every day, kept simple
    max_consecutive_days: int = 5
    min_rest_shifts: int = 1  # shifts of rest required between LATE/NIGHT and next day's EARLY

    def shift_types(self) -> tuple[ShiftType, ...]:
        return (ShiftType.EARLY, ShiftType.LATE, ShiftType.NIGHT)

    def max_shifts_per_week(self, staff_member: Staff) -> int:
        return 5 if staff_member.contract == ContractType.FULL_TIME else 3


def build_default_problem(num_staff: int = 15, num_days: int = 14, seed_off_requests: bool = True) -> SchedulingProblem:
    """
    Builds a small, realistic synthetic staffing problem: enough staff to
    make the minimum-staffing constraints genuinely binding (not trivially
    satisfiable), a mix of full-time/part-time contracts, a few staff not
    qualified for night shifts (a real constraint many hospitals have for
    newer or part-time staff), and a handful of requested days off so the
    soft-preference / hard-constraint tradeoff has something real to
    resolve.
    """
    staff = []
    for i in range(num_staff):
        contract = ContractType.FULL_TIME if i % 3 != 0 else ContractType.PART_TIME
        qualified_for_night = not (i % 5 == 0)  # every 5th staff member can't do nights
        requested_days_off = ()
        if seed_off_requests and i % 4 == 0:
            requested_days_off = (i % num_days,)
        staff.append(Staff(
            staff_id=f"S{i:02d}",
            name=f"Staff {i:02d}",
            contract=contract,
            qualified_for_night=qualified_for_night,
            requested_days_off=requested_days_off,
        ))

    return SchedulingProblem(
        staff=tuple(staff),
        num_days=num_days,
        min_staff_per_shift={ShiftType.EARLY: 3, ShiftType.LATE: 3, ShiftType.NIGHT: 2},
    )
