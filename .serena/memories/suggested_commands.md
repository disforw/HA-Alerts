# Suggested Commands

- No build step required (uncompiled JS, Python)
- Lint Python: `cd custom_components/ha_alerts && python3 -m py_compile *.py`
- Check syntax: `python3 -c "import ast; ast.parse(open('file.py').read())"`
- Git: standard git commands, push to origin main directly (no PRs)
- No test suite currently
