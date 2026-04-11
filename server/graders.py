from __future__ import annotations

from copy import deepcopy
from typing import Any

from real_estate_pipeline.env import RealEstatePipelineEnv
from real_estate_pipeline.graders import grade_task
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
        return grade_task(self._task, deepcopy(state))


class EasyGrader(_TaskGrader):
    def __init__(self):
        super().__init__(_TASK_BY_DIFFICULTY["easy"])


class MediumGrader(_TaskGrader):
    def __init__(self):
        super().__init__(_TASK_BY_DIFFICULTY["medium"])


class HardGrader(_TaskGrader):
    def __init__(self):
        super().__init__(_TASK_BY_DIFFICULTY["hard"])


def list_graders() -> dict[str, type[_TaskGrader]]:
    return {
        "easy": EasyGrader,
        "medium": MediumGrader,
        "hard": HardGrader,
    }


def available_task_ids() -> list[str]:
    return list_task_ids()
