"""
solver.py
---------

Constraint-programming solver for the SchedulingProblem, using Google
OR-Tools' CP-SAT solver -- a real, industrial-strength constraint solver
(the same class of tool -- constraint/integer programming -- that real
rostering products like the posting's "ShiftPlan" are built on), not a
hand-rolled heuristic.

Decision variables: shift[(staff_id, day, shift_type)] -- a boolean,
1 if that staff member works that shift on that day.

Hard constraints (must hold in any returned solution):
  1. Minimum staffing per shift per day.
  2. At most one shift per staff member per day.
  3. Night-shift qualification: unqualified staff never assigned NIGHT.
  4. Minimum rest: no staff member works a LATE or NIGHT shift
     immediately followed by an EARLY shift the next day (a simplified
     stand-in for the real Ruhezeiten/rest-period requirement named in
     the posting).
  5. Max consecutive working days (a rolling window constraint).
  6. Weekly max shifts, based on contract type (full-time vs part-time).

Soft constraint (minimized, not enforced): requested days off. Modeled
as a penalty in the objective rather than a hard constraint, so the
solver always returns a feasible schedule -- if honoring every request
were impossible given minimum staffing, a hard constraint would make the
whole problem infeasible, which is the wrong behavior for a real
scheduling tool (a hospital always needs *a* schedule, even an imperfect
one).
"""

from __future__ import annotations

from dataclasses import dataclass

from ortools.sat.python import cp_model

from src.model import SchedulingProblem, ShiftType


@dataclass
class ScheduleResult:
    status: str  # "OPTIMAL", "FEASIBLE", or "INFEASIBLE"
    assignments: dict  # {(staff_id, day, shift_type): bool}
    violated_off_requests: list  # [(staff_id, day)] -- requests the solver couldn't honor
    solve_time_seconds: float


def solve_schedule(problem: SchedulingProblem, time_limit_seconds: float = 10.0) -> ScheduleResult:
    model = cp_model.CpModel()
    shift_types = problem.shift_types()
    days = range(problem.num_days)

    # Decision variables.
    shift = {}
    for s in problem.staff:
        for d in days:
            for st in shift_types:
                shift[(s.staff_id, d, st)] = model.NewBoolVar(f"shift_{s.staff_id}_{d}_{st.value}")

    # 1. Minimum staffing per shift per day.
    for d in days:
        for st in shift_types:
            model.Add(
                sum(shift[(s.staff_id, d, st)] for s in problem.staff) >= problem.min_staff_per_shift[st]
            )

    # 2. At most one shift per staff member per day.
    for s in problem.staff:
        for d in days:
            model.Add(sum(shift[(s.staff_id, d, st)] for st in shift_types) <= 1)

    # 3. Night-shift qualification.
    for s in problem.staff:
        if not s.qualified_for_night:
            for d in days:
                model.Add(shift[(s.staff_id, d, ShiftType.NIGHT)] == 0)

    # 4. Minimum rest: no LATE or NIGHT on day d immediately followed by
    #    EARLY on day d+1.
    for s in problem.staff:
        for d in range(problem.num_days - 1):
            late_or_night_today = shift[(s.staff_id, d, ShiftType.LATE)] + shift[(s.staff_id, d, ShiftType.NIGHT)]
            early_tomorrow = shift[(s.staff_id, d + 1, ShiftType.EARLY)]
            # If late_or_night_today == 1, early_tomorrow must be 0.
            model.Add(late_or_night_today + early_tomorrow <= 1)

    # 5. Max consecutive working days (rolling window).
    works_day = {}
    for s in problem.staff:
        for d in days:
            works = model.NewBoolVar(f"works_{s.staff_id}_{d}")
            model.Add(sum(shift[(s.staff_id, d, st)] for st in shift_types) == works)
            works_day[(s.staff_id, d)] = works

    for s in problem.staff:
        window = problem.max_consecutive_days + 1
        for start in range(problem.num_days - window + 1):
            model.Add(
                sum(works_day[(s.staff_id, d)] for d in range(start, start + window)) <= problem.max_consecutive_days
            )

    # 6. Weekly max shifts by contract type, over each non-overlapping 7-day block.
    for s in problem.staff:
        max_per_week = problem.max_shifts_per_week(s)
        for week_start in range(0, problem.num_days, 7):
            week_days = range(week_start, min(week_start + 7, problem.num_days))
            model.Add(sum(works_day[(s.staff_id, d)] for d in week_days) <= max_per_week)

    # Soft constraint: minimize violated day-off requests.
    violation_vars = []
    violation_keys = []
    for s in problem.staff:
        for d in s.requested_days_off:
            if d >= problem.num_days:
                continue
            v = model.NewBoolVar(f"violation_{s.staff_id}_{d}")
            model.Add(v == works_day[(s.staff_id, d)])
            violation_vars.append(v)
            violation_keys.append((s.staff_id, d))

    if violation_vars:
        model.Minimize(sum(violation_vars))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_seconds
    solver.parameters.num_search_workers = 4
    status = solver.Solve(model)

    status_name = solver.StatusName(status)
    assignments = {}
    violated = []

    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        for key, var in shift.items():
            assignments[key] = bool(solver.Value(var))
        for (staff_id, d), v in zip(violation_keys, violation_vars):
            if solver.Value(v):
                violated.append((staff_id, d))

    return ScheduleResult(
        status=status_name,
        assignments=assignments,
        violated_off_requests=violated,
        solve_time_seconds=solver.WallTime(),
    )
