# context.py
"""Context management for the writing agent.

Maintains a "context profile" - a curated set of files that persists
across conversations and gets injected fresh on /new or /clear.
"""

from dataclasses import dataclass
from pathlib import Path


@dataclass
class ContextItem:
    """A single item in the context profile."""
    path: str
    content: str
    tokens: int = 0  # actual count captured after injection
    enabled: bool = True


class ContextStore:
    """Manages the context profile."""

    def __init__(self):
        self.items: list[ContextItem] = []

    def add(self, path: str) -> ContextItem:
        """Add a file to the context profile.

        Token count starts at 0, updated with actual count after injection.
        """
        file_path = Path(path).expanduser().resolve()
        file_content = file_path.read_text()

        item = ContextItem(
            path=path,
            content=file_content,
        )
        self.items.append(item)
        return item

    def remove(self, index: int) -> None:
        """Remove an item by index."""
        if 0 <= index < len(self.items):
            self.items.pop(index)
        else:
            raise IndexError(f"Index {index} out of range")

    def toggle(self, index: int) -> None:
        """Toggle an item's enabled state."""
        if 0 <= index < len(self.items):
            self.items[index].enabled = not self.items[index].enabled
        else:
            raise IndexError(f"Index {index} out of range")

    def list(self) -> str:
        """Format context items for display."""
        if not self.items:
            return "No context items"

        lines = []
        for i, item in enumerate(self.items):
            status = "✓" if item.enabled else "✗"
            lines.append(f"  {i}: [{status}] {item.path} ({item.tokens} tokens)")

        lines.append(f"\n  Total enabled: {self.total_tokens()} tokens")
        return "\n".join(lines)

    def total_tokens(self) -> int:
        """Sum of enabled context items."""
        return sum(item.tokens for item in self.items if item.enabled)

    def get_enabled_content(self) -> str:
        """Build context block from enabled items only.

        Used when starting a new conversation - injects all enabled
        context items as a single block.
        """
        enabled_items = [item for item in self.items if item.enabled]
        if not enabled_items:
            return ""

        blocks = [f"[FILE:{item.path}]\n{item.content}\n" for item in enabled_items]
        return "".join(blocks)
