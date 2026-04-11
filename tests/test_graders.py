from pathlib import Path

import yaml

from real_estate_pipeline.env import RealEstatePipelineEnv
from server.graders import EasyGrader, HardGrader, MediumGrader, grade_easy, grade_hard, grade_medium


def test_all_tasks_produce_bounded_grader_scores() -> None:
    env = RealEstatePipelineEnv()
    for task_id in env.available_tasks():
        env.reset(task_id)
        score = env.state()["grader_score"]
        assert 0.0 < score < 1.0


def test_validator_style_graders_import_and_grade_none() -> None:
    for grader_cls in (EasyGrader, MediumGrader, HardGrader):
        score = grader_cls().grade(None)
        assert 0.0 < score < 1.0


def test_manifest_grader_functions_exist_and_score_in_bounds() -> None:
    manifest = yaml.safe_load(Path("openenv.yaml").read_text(encoding="utf-8"))
    expected_functions = {
        "residential_buyer_qualification": grade_easy,
        "residential_missing_info_followup": grade_medium,
        "commercial_lease_strategy": grade_hard,
    }
    for task in manifest["tasks"]:
        assert task["grader"]["module"] == "server.graders"
        function_name = task["grader"]["function"]
        score = expected_functions[task["id"]]()
        assert function_name in {"grade_easy", "grade_medium", "grade_hard"}
        assert 0.0 < score < 1.0
