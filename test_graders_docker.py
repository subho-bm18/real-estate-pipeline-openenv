#!/usr/bin/env python3
"""Test graders in Docker to diagnose scoring issues."""

from server.graders import EasyGrader, MediumGrader, HardGrader

for name, g in [('Easy', EasyGrader()), ('Medium', MediumGrader()), ('Hard', HardGrader())]:
    try:
        score = g.grade(None)
        status = 'OK' if 0 < score < 1 else f'FAIL — value is {score}'
        print(f'{name}: {status}')
    except Exception as e:
        import traceback
        print(f'{name}: IMPORT/CALL ERROR — {e}')
        traceback.print_exc()
