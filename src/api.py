"""
api.py
------

FastAPI backend exposing the scheduling solver as an HTTP service --
directly addressing the posting's "Backend-APIs in Python fuer unser
Produkt ShiftPlan mitentwickeln und implementieren" responsibility.

Endpoints:

  GET  /health                 -> liveness check
  POST /schedule/default       -> solves the built-in default problem,
                                   returns the schedule + validation result
  POST /schedule                -> solves a caller-supplied problem
                                    (staff list, constraints) and returns
                                    the schedule + validation result

Every response includes the independent-validator's result (see
validate.py) alongside the solver's own status, not just the solver's
self-reported feasibility -- so a client of this API sees the same
"don't just trust the solver" verification this project applies
internally.
"""

from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel, Field

from src.model import ContractType, ShiftType, Staff, SchedulingProblem, build_default_problem
from src.solver import solve_schedule
from src.validate import validate_schedule


class StaffIn(BaseModel):
    staff_id: str
    name: str
    contract: ContractType
    qualified_for_night: bool = True
    requested_days_off: list[int] = Field(default_factory=list)


class ScheduleRequestIn(BaseModel):
    staff: list[StaffIn]
    num_days: int = Field(gt=0, le=28)
    min_staff_early: int = Field(gt=0)
    min_staff_late: int = Field(gt=0)
    min_staff_night: int = Field(gt=0)
    max_consecutive_days: int = Field(default=5, gt=0)


def _problem_from_request(req: ScheduleRequestIn) -> SchedulingProblem:
    staff = tuple(
        Staff(
            staff_id=s.staff_id,
            name=s.name,
            contract=s.contract,
            qualified_for_night=s.qualified_for_night,
            requested_days_off=tuple(s.requested_days_off),
        )
        for s in req.staff
    )
    return SchedulingProblem(
        staff=staff,
        num_days=req.num_days,
        min_staff_per_shift={
            ShiftType.EARLY: req.min_staff_early,
            ShiftType.LATE: req.min_staff_late,
            ShiftType.NIGHT: req.min_staff_night,
        },
        max_consecutive_days=req.max_consecutive_days,
    )


def _serialize_result(problem: SchedulingProblem, result) -> dict:
    schedule = []
    for s in problem.staff:
        for d in range(problem.num_days):
            for st in problem.shift_types():
                if result.assignments.get((s.staff_id, d, st)):
                    schedule.append({"staff_id": s.staff_id, "day": d, "shift": st.value})

    violations = validate_schedule(problem, result.assignments)

    return {
        "solver_status": result.status,
        "solve_time_seconds": result.solve_time_seconds,
        "schedule": schedule,
        "violated_off_requests": [{"staff_id": sid, "day": d} for sid, d in result.violated_off_requests],
        "independent_validation": {
            "valid": len(violations) == 0,
            "violations": violations,
        },
    }


def create_app() -> FastAPI:
    app = FastAPI(title="ShiftPlan-style Rostering Optimizer")

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.post("/schedule/default")
    def schedule_default(num_staff: int = 10, num_days: int = 14):
        problem = build_default_problem(num_staff=num_staff, num_days=num_days)
        result = solve_schedule(problem)
        return _serialize_result(problem, result)

    @app.post("/schedule")
    def schedule(req: ScheduleRequestIn):
        problem = _problem_from_request(req)
        result = solve_schedule(problem)
        return _serialize_result(problem, result)

    return app


app = create_app()
