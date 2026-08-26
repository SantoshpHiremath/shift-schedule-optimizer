"""
validate.py
-----------

Independent validator for a solved schedule. This does NOT trust the
solver's claimed feasibility -- it walks the returned assignment dict
and re-checks every hard constraint from scratch using plain Python,
completely independent of the CP-SAT model. This is the same
"independently re-verify, don't just trust the tool" discipline used
throughout this project portfolio (e.g. re-verifying test results rather
than trusting a first green run).

Returns a list of human-readable violation strings; an empty list means
the schedule is genuinely valid.
"""

from __future__ import annotations

from src.model import SchedulingProblem, ShiftType


def validate_schedule(problem: SchedulingProblem, assignments: dict) -> list:
    violations = []
    shift_types = problem.shift_types()
    days = range(problem.num_days)

    def works(staff_id, d, st):
        return assignments.get((staff_id, d, st), False)

    def works_any(staff_id, d):
        return any(works(staff_id, d, st) for st in shift_types)

    # 1. Minimum staffing per shift per day.
    for d in days:
        for st in shift_types:
            count = sum(1 for s in problem.staff if works(s.staff_id, d, st))
            if count < problem.min_staff_per_shift[st]:
                violations.append(
                    f"day {d} shift {st.value}: staffed {count}, needs >= {problem.min_staff_per_shift[st]}"
                )

    # 2. At most one shift per staff member per day.
    for s in problem.staff:
        for d in days:
            count = sum(1 for st in shift_types if works(s.staff_id, d, st))
            if count > 1:
                violations.append(f"staff {s.staff_id} day {d}: assigned {count} shifts (max 1)")

    # 3. Night-shift qualification.
    for s in problem.staff:
        if not s.qualified_for_night:
            for d in days:
                if works(s.staff_id, d, ShiftType.NIGHT):
                    violations.append(f"staff {s.staff_id} day {d}: assigned NIGHT but not qualified")

    # 4. Minimum rest: no LATE/NIGHT immediately followed by EARLY next day.
    for s in problem.staff:
        for d in range(problem.num_days - 1):
            if (works(s.staff_id, d, ShiftType.LATE) or works(s.staff_id, d, ShiftType.NIGHT)) \
                    and works(s.staff_id, d + 1, ShiftType.EARLY):
                violations.append(f"staff {s.staff_id}: LATE/NIGHT on day {d} followed by EARLY on day {d + 1} (rest violation)")

    # 5. Max consecutive working days.
    for s in problem.staff:
        run = 0
        for d in days:
            if works_any(s.staff_id, d):
                run += 1
                if run > problem.max_consecutive_days:
                    violations.append(
                        f"staff {s.staff_id}: {run} consecutive working days ending day {d} (max {problem.max_consecutive_days})"
                    )
            else:
                run = 0

    # 6. Weekly max shifts by contract type.
    for s in problem.staff:
        max_per_week = problem.max_shifts_per_week(s)
        for week_start in range(0, problem.num_days, 7):
            week_days = range(week_start, min(week_start + 7, problem.num_days))
            count = sum(1 for d in week_days if works_any(s.staff_id, d))
            if count > max_per_week:
                violations.append(
                    f"staff {s.staff_id} week starting day {week_start}: {count} shifts (max {max_per_week} for {s.contract.value})"
                )

    return violations
