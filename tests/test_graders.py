from real_estate_pipeline.env import RealEstatePipelineEnv
from server.graders import EasyGrader, HardGrader, MediumGrader


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
