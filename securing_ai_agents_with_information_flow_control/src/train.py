"""Agent-loop runner (this paper has no training procedure).

Paper: https://arxiv.org/abs/2505.23643v2
Section references:
  Algorithm 2 — planning loop
  Algorithm 5 — taint-tracking loop with policy abort

The runnable demo lives in src/evaluate.py.
"""

from src.evaluate import main, run_undefended, run_with_policy

__all__ = ["main", "run_undefended", "run_with_policy"]
