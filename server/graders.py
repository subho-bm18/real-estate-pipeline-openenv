from __future__ import annotations

from copy import deepcopy
from typing import Any

from real_estate_pipeline.env import RealEstatePipelineEnv
from real_estate_pipeline.graders import grade_task as core_grade_task
from real_estate_pipeline.tasks import list_task_ids, load_task


_TASK_BY_DIFFICULTY = {
    "easy": "residential_buyer_qualification",
    "medium": "residential_missing_info_followup",
    "hard": "commercial_lease_strategy",
}


class _TaskGrader:
    def __init__(self, task_id: str):
        self.task_id = task_id
        self._env = RealEstatePipelineEnv(task_id=task_id)
        self._task = load_task(task_id)

    def grade(self, state: dict[str, Any] | None) -> float:
        if state is None:
            self._env.reset(self.task_id)
            state = self._env.state()
        return core_grade_task(self._task, deepcopy(state))


class EasyGrader(_TaskGrader):
    def __init__(self):
        super().__init__(_TASK_BY_DIFFICULTY["easy"])


class MediumGrader(_TaskGrader):
    def __init__(self):
        super().__init__(_TASK_BY_DIFFICULTY["medium"])


class HardGrader(_TaskGrader):
    def __init__(self):
        super().__init__(_TASK_BY_DIFFICULTY["hard"])


def _extract_state(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        if "active_opportunity" in value:
            return value
        nested_state = value.get("state")
        if isinstance(nested_state, dict) and "active_opportunity" in nested_state:
            return nested_state
    return None


def _resolve_task_id(
    *,
    explicit_task_id: str | None = None,
    explicit_difficulty: str | None = None,
    payload: Any = None,
    fallback_task_id: str,
) -> str:
    if explicit_task_id:
        return explicit_task_id
    if explicit_difficulty in _TASK_BY_DIFFICULTY:
        return _TASK_BY_DIFFICULTY[explicit_difficulty]
    if isinstance(payload, dict):
        payload_task_id = payload.get("task_id")
        if isinstance(payload_task_id, str) and payload_task_id:
            return payload_task_id
        payload_difficulty = payload.get("difficulty")
        if isinstance(payload_difficulty, str) and payload_difficulty in _TASK_BY_DIFFICULTY:
            return _TASK_BY_DIFFICULTY[payload_difficulty]
    return fallback_task_id


def _score_for_task(
    fallback_task_id: str,
    state: dict[str, Any] | None = None,
    *args: Any,
    task_id: str | None = None,
    difficulty: str | None = None,
    **kwargs: Any,
) -> float:
    payload = state if state is not None else (args[0] if args else None)
    resolved_state = _extract_state(state)
    if resolved_state is None:
        resolved_state = _extract_state(payload)
    resolved_task_id = _resolve_task_id(
        explicit_task_id=task_id or kwargs.get("task_id"),
        explicit_difficulty=difficulty or kwargs.get("difficulty"),
        payload=payload,
        fallback_task_id=fallback_task_id,
    )
    return _TaskGrader(resolved_task_id).grade(resolved_state)


def grade_easy(state: dict[str, Any] | None = None, *args: Any, **kwargs: Any) -> float:
    return _score_for_task(_TASK_BY_DIFFICULTY["easy"], state, *args, **kwargs)


def grade_medium(state: dict[str, Any] | None = None, *args: Any, **kwargs: Any) -> float:
    return _score_for_task(_TASK_BY_DIFFICULTY["medium"], state, *args, **kwargs)


def grade_hard(state: dict[str, Any] | None = None, *args: Any, **kwargs: Any) -> float:
    return _score_for_task(_TASK_BY_DIFFICULTY["hard"], state, *args, **kwargs)


def grade_task(state: dict[str, Any] | None = None, *args: Any, **kwargs: Any) -> float:
    fallback_task_id = _TASK_BY_DIFFICULTY.get(kwargs.get("difficulty"), _TASK_BY_DIFFICULTY["easy"])
    return _score_for_task(fallback_task_id, state, *args, **kwargs)


def list_graders() -> dict[str, type[_TaskGrader]]:
    return {
        "easy": EasyGrader,
        "medium": MediumGrader,
        "hard": HardGrader,
    }


def available_task_ids() -> list[str]:
    return list_task_ids()
