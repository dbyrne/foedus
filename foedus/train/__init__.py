"""Training-gym utilities: turn arena decision-logs into SFT data (build_sft).

This subpackage is intentionally dependency-light. ``build_sft`` uses only the
standard library so the dataset can be built anywhere (CI, the project's default
venv). The heavy ML stack (torch/peft/bitsandbytes/trl) lives behind the
``[train]`` optional extra and is only needed by ``scripts/foedus_train_qlora.py``.
"""
