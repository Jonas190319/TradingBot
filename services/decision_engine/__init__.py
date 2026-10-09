"""Importable package for the existing decision-engine source directory."""
from pathlib import Path

__path__ = [str(Path(__file__).resolve().parent.parent / "decision-engine")]
