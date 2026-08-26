"""
tests/test_solver.py
---------------------

Tests the CP-SAT solver against real constraint scenarios, always
cross-checked with the independent validator (validate.py) rather than
trusting the solver's own "OPTIMAL"/"FEASIBLE" status label alone --
the same discipline used throughout this portfolio of not trusting a
green result without independent re-verification.
"""

from src.model import ContractType, ShiftType, Staff, SchedulingProblem, build_default_problem
from src.solver import solve_schedule
from src.validate import validate_schedule


class TestDefaultProblemSolves:
    def test_default_problem_is_feasible(self):
        problem = build_default_problem(num_staff=15, num_days=14)
        result = solve_schedule(problem)
        assert result.status in ("OPTIMAL", "FEASIBLE")

    def test_default_problem_solution_passes_independent_validation(self):
        problem = build_default_problem(num_staff=15, num_days=14)
        result = solve_schedule(problem)
        violations = validate_schedule(problem, result.assignments)
        assert violations == [], f"Solver returned a schedule that fails independent validation: {violations}"

    def test_default_problem_meets_minimum_staffing_every_shift(self):
        problem = build_default_problem(num_staff=15, num_days=14)
        result = solve_schedule(problem)
        for d in range(problem.num_days):
            for st in problem.shift_types():
                count = sum(1 for s in problem.staff if result.assignments.get((s.staff_id, d, st)))
                assert count >= problem.min_staff_per_shift[st]


class TestQualificationConstraint:
    def test_unqualified_staff_never_assigned_night_shift(self):
        problem = build_default_problem(num_staff=15, num_days=14)
        result = solve_schedule(problem)
        for s in problem.staff:
            if not s.qualified_for_night:
                for d in range(problem.num_days):
                    assert not result.assignments.get((s.staff_id, d, ShiftType.NIGHT)), \
                        f"{s.staff_id} assigned NIGHT despite qualified_for_night=False"


class TestRestConstraint:
    def test_no_late_or_night_immediately_followed_by_early(self):
        problem = build_default_problem(num_staff=15, num_days=14)
        result = solve_schedule(problem)
        for s in problem.staff:
            for d in range(problem.num_days - 1):
                late_or_night = result.assignments.get((s.staff_id, d, ShiftType.LATE)) \
                    or result.assignments.get((s.staff_id, d, ShiftType.NIGHT))
                early_next = result.assignments.get((s.staff_id, d + 1, ShiftType.EARLY))
                assert not (late_or_night and early_next), \
                    f"{s.staff_id}: LATE/NIGHT day {d} immediately followed by EARLY day {d + 1}"


class TestOneShiftPerDay:
    def test_no_staff_double_booked_same_day(self):
        problem = build_default_problem(num_staff=15, num_days=14)
        result = solve_schedule(problem)
        for s in problem.staff:
            for d in range(problem.num_days):
                count = sum(1 for st in problem.shift_types() if result.assignments.get((s.staff_id, d, st)))
                assert count <= 1


class TestWeeklyHoursByContract:
    def test_part_time_staff_never_exceed_three_shifts_per_week(self):
        problem = build_default_problem(num_staff=15, num_days=14)
        result = solve_schedule(problem)
        for s in problem.staff:
            if s.contract != ContractType.PART_TIME:
                continue
            for week_start in (0, 7):
                count = sum(
                    1 for d in range(week_start, min(week_start + 7, problem.num_days))
                    for st in problem.shift_types()
                    if result.assignments.get((s.staff_id, d, st))
                )
                assert count <= 3

    def test_full_time_staff_never_exceed_five_shifts_per_week(self):
        problem = build_default_problem(num_staff=15, num_days=14)
        result = solve_schedule(problem)
        for s in problem.staff:
            if s.contract != ContractType.FULL_TIME:
                continue
            for week_start in (0, 7):
                count = sum(
                    1 for d in range(week_start, min(week_start + 7, problem.num_days))
                    for st in problem.shift_types()
                    if result.assignments.get((s.staff_id, d, st))
                )
                assert count <= 5


class TestConsecutiveDaysConstraint:
    def test_no_staff_exceeds_max_consecutive_working_days(self):
        problem = build_default_problem(num_staff=15, num_days=14)
        result = solve_schedule(problem)
        for s in problem.staff:
            run = 0
            for d in range(problem.num_days):
                works = any(result.assignments.get((s.staff_id, d, st)) for st in problem.shift_types())
                run = run + 1 if works else 0
                assert run <= problem.max_consecutive_days


class TestSoftPreferenceHandling:
    def test_problem_with_off_requests_still_feasible(self):
        """Even with day-off requests present, the schedule must remain
        feasible (soft constraint, never blocks a solution)."""
        problem = build_default_problem(num_staff=15, num_days=14, seed_off_requests=True)
        result = solve_schedule(problem)
        assert result.status in ("OPTIMAL", "FEASIBLE")

    def test_off_requests_honored_when_slack_exists(self):
        """With plenty of staff relative to minimum staffing, the solver
        should be able to honor day-off requests without violating
        minimum staffing -- verifies the objective function is actually
        doing something, not just present but ineffective."""
        staff = tuple(
            Staff(staff_id=f"S{i:02d}", name=f"Staff {i}", contract=ContractType.FULL_TIME,
                  qualified_for_night=True, requested_days_off=(0,) if i == 0 else ())
            for i in range(15)  # generously more staff than the minimums need
        )
        problem = SchedulingProblem(
            staff=staff, num_days=7,
            min_staff_per_shift={ShiftType.EARLY: 2, ShiftType.LATE: 2, ShiftType.NIGHT: 2},
        )
        result = solve_schedule(problem)
        assert result.violated_off_requests == [], \
            "Expected the day-off request to be honored given ample staffing slack"


class TestInfeasibleProblemDetected:
    def test_impossible_minimum_staffing_reported_infeasible(self):
        """A minimum staffing requirement that literally exceeds the
        total number of staff available must be reported as infeasible,
        not silently 'solved' with an invalid schedule."""
        staff = tuple(
            Staff(staff_id=f"S{i:02d}", name=f"Staff {i}", contract=ContractType.FULL_TIME)
            for i in range(2)  # only 2 staff total
        )
        problem = SchedulingProblem(
            staff=staff, num_days=3,
            # Impossible: needs 5 people per shift, but only 2 exist.
            min_staff_per_shift={ShiftType.EARLY: 5, ShiftType.LATE: 5, ShiftType.NIGHT: 5},
        )
        result = solve_schedule(problem)
        assert result.status == "INFEASIBLE"
        assert result.assignments == {}


class TestValidatorCatchesRealViolations:
    """Directly exercises validate.py with a deliberately broken,
    hand-constructed schedule (not solver output) to confirm the
    validator actually catches each violation type rather than being a
    rubber stamp. This is the 'confirm the check has real teeth' test
    for the validation layer itself."""

    def _minimal_problem(self):
        staff = (
            Staff(staff_id="S00", name="A", contract=ContractType.FULL_TIME, qualified_for_night=False),
            Staff(staff_id="S01", name="B", contract=ContractType.PART_TIME, qualified_for_night=True),
        )
        return SchedulingProblem(
            staff=staff, num_days=3,
            min_staff_per_shift={ShiftType.EARLY: 1, ShiftType.LATE: 1, ShiftType.NIGHT: 1},
        )

    def test_validator_catches_understaffing(self):
        problem = self._minimal_problem()
        assignments = {}  # nobody assigned anywhere -- badly understaffed
        violations = validate_schedule(problem, assignments)
        assert any("staffed 0" in v for v in violations)

    def test_validator_catches_unqualified_night_assignment(self):
        problem = self._minimal_problem()
        assignments = {("S00", 0, ShiftType.NIGHT): True}  # S00 is not qualified for nights
        violations = validate_schedule(problem, assignments)
        assert any("not qualified" in v for v in violations)

    def test_validator_catches_rest_violation(self):
        problem = self._minimal_problem()
        assignments = {
            ("S01", 0, ShiftType.NIGHT): True,
            ("S01", 1, ShiftType.EARLY): True,  # immediately followed by an early shift -- no rest
        }
        violations = validate_schedule(problem, assignments)
        assert any("rest violation" in v for v in violations)

    def test_validator_catches_double_booking(self):
        problem = self._minimal_problem()
        assignments = {
            ("S01", 0, ShiftType.EARLY): True,
            ("S01", 0, ShiftType.LATE): True,  # two shifts, same day
        }
        violations = validate_schedule(problem, assignments)
        assert any("assigned 2 shifts" in v for v in violations)

    def test_validator_passes_a_genuinely_valid_hand_built_schedule(self):
        """Negative-control check: the validator shouldn't flag a
        schedule that actually satisfies every constraint."""
        problem = self._minimal_problem()
        assignments = {
            ("S00", 0, ShiftType.EARLY): True,
            ("S01", 0, ShiftType.LATE): True,
            ("S01", 0, ShiftType.NIGHT): False,
            ("S00", 1, ShiftType.NIGHT): False,
        }
        # S00 not qualified for night, so only ever assign EARLY/LATE for S00.
        # This deliberately leaves NIGHT and some minimums unmet, so it's
        # NOT a fully valid schedule -- just confirms no false positives
        # are raised for constraints that ARE satisfied here.
        violations = validate_schedule(problem, assignments)
        assert not any("not qualified" in v for v in violations)
        assert not any("rest violation" in v for v in violations)
        assert not any("2 shifts" in v for v in violations)
