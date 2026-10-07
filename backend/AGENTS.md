# Backend agent notes

Python source files start with a module docstring:

```python
"""Purpose: What this file is responsible for.

Public API:
- exported_name
"""
```

Every function and method has a one-line docstring. Prefer small modules with typed inputs and outputs. The model may call MCP read tools and `propose_action` only. Xero writes go through the invoice service, called by the confirm route or by a person saving in the invoice UI.

Each subfolder has its own `AGENTS.md` for what belongs there. New Python modules still use the header above.
