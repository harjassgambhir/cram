"""
profiles/registry.py — Specialty profiles removed.

The system is fully dynamic: all research guidance is generated from the input
scenario by pipeline/question_analyzer.py. No predefined clinical field types.

Previously contained 8 specialty profiles (surgery, oncology, cardiology, etc.)
with keyword lists and priority source routing. These have been removed because:
  - The LLM understands the scenario without explicit field labels
  - Profile keyword matching caused mis-classification and false-positive routing
  - question_analyzer.py already generates better, scenario-specific guidance
"""
