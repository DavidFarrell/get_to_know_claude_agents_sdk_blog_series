# Blog Two Notes

Working notes for Claude Agent SDK Part 2 blog post.

---

## Dev Environment Setup

- User opened project in Antigravity Open (Google's VS Code fork)
- IntelliSense wasn't working - no autocomplete/tooltips for SDK types
- **Fix**: `uv pip install -e .` to install package in editable mode from `pyproject.toml`
- Then select the correct Python interpreter in IDE (Command Palette → "Python: Select Interpreter")

---

## The ToolUseBlock Debugging Adventure

### The Problem
User was editing code to show more info when tools are used. IntelliSense suggested `block.signature` and `block.content`. Code crashed at runtime:

```
AttributeError: 'ToolUseBlock' object has no attribute 'signature'
```

### Investigation
Used runtime introspection to discover actual attributes:

```python
from claude_agent_sdk import ToolUseBlock
print(ToolUseBlock.__dataclass_fields__.keys())
# Result: ['id', 'name', 'input']
```

### Root Cause
`signature` belongs to **ThinkingBlock**, `content` belongs to **ToolResultBlock** - neighboring classes in `types.py`:

```python
@dataclass
class ThinkingBlock:
    thinking: str
    signature: str    # <-- IntelliSense grabbed this

@dataclass
class ToolUseBlock:
    id: str
    name: str
    input: dict[str, Any]

@dataclass
class ToolResultBlock:
    tool_use_id: str
    content: str | ...  # <-- And this
```

### Lesson
IntelliSense type narrowing inside `elif isinstance()` branches isn't always reliable. When it suggests unfamiliar attributes, verify with runtime introspection before using.

---

## SDK Type Reference

### Block Types (from `claude_agent_sdk.types`)

| Type | Fields |
|------|--------|
| `TextBlock` | `text: str` |
| `ThinkingBlock` | `thinking: str`, `signature: str` |
| `ToolUseBlock` | `id: str`, `name: str`, `input: dict[str, Any]` |
| `ToolResultBlock` | `tool_use_id: str`, `content: str \| list \| None`, `is_error: bool \| None` |

---

## Raw Notes / Ideas

(Space for capturing things as we go...)

