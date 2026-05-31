"""
src/context/ — LLM context assembly for PPT.

WHY a dedicated context module?
  An LLM is only as smart as the context it receives.
  This module assembles a snapshot of "who Rana is right now" from all
  PPT data sources and formats it for injection into an Ollama prompt.

  Without this: LLM answers generic questions generically.
  With this: LLM knows your sleep, your habits, your goals, your patterns —
             and gives advice that's actually relevant to your life.

  The context block is also the foundation for the training data exporter:
  training examples are built by varying the context and generating Q&A pairs.
"""
from src.context.builder import build_context, build_system_prompt

__all__ = ["build_context", "build_system_prompt"]
