"""Local-PC-driven autonomous production pipeline (Phase 1 skeleton).

This package is additive: it does not modify the existing GitHub-Actions
oriented pipeline in stock_factory/pipeline.py, and nothing here is wired
into CI. It is meant to be invoked on the operator's own always-on
machine (see providers/*.py docstrings for why browser-automation
generation cannot run from a cloud CI/agent session).
"""
