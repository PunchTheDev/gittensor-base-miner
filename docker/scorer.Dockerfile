FROM python:3.12-slim

# Pre-install tree-sitter so the network-isolated Phase 2 scorer can use it.
# Versions pinned to match gittensor's pyproject.toml exactly.
RUN pip install --no-cache-dir \
    tree-sitter==0.24.0 \
    "tree-sitter-language-pack==0.7.2"
