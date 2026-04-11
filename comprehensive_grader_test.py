#!/usr/bin/env python3
"""Comprehensive grader diagnostic with state inspection."""

from server.graders import EasyGrader, MediumGrader, HardGrader
import json

for name, G in [('Easy', EasyGrader), ('Medium', MediumGrader), ('Hard', HardGrader)]:
    try:
        grader = G()
        print(f"\n{name} Grader:")
        print(f"  Task ID: {grader.task_id}")
        
        # Get state
        grader._env.reset(grader.task_id)
        state = grader._env.state()
        
        print(f"  State keys: {list(state.keys())}")
        if "active_opportunity" in state:
            print(f"  Active opportunity ID: {state['active_opportunity'].get('opportunity_id')}")
        
        # Grade
        score = grader.grade(None)
        print(f"  Score: {score}")
        
        # Check validity
        if score <= 0.0 or score >= 1.0:
            print(f"  ❌ INVALID: Score {score} is not strictly between 0 and 1")
        elif 0 < score < 1:
            print(f"  ✓ VALID: Score {score} is strictly between 0 and 1")
        else:
            print(f"  ? UNKNOWN: Score {score}")
            
    except Exception as e:
        import traceback
        print(f"\n{name} Grader ERROR:")
        print(f"  Exception: {e}")
        traceback.print_exc()
