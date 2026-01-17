# usage.py
"""Usage tracking for the writing agent.

Tracks token consumption and costs across conversation turns.
"""

from dataclasses import dataclass, field


@dataclass
class TurnUsage:
    """Usage data for a single turn."""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0
    cost_usd: float = 0.0

    @property
    def total_input(self) -> int:
        """Total input tokens (cached + uncached)."""
        return self.input_tokens + self.cache_creation_tokens + self.cache_read_tokens

    @property
    def new_tokens(self) -> int:
        """Tokens newly added this turn (not from cache)."""
        return self.input_tokens + self.cache_creation_tokens

    def format_brief(self, baseline_cache: int = 0) -> str:
        """One-line summary for display after each turn.

        Args:
            baseline_cache: System prompt tokens to subtract from cache_read
                           to show only user-relevant cached content.
        """
        # What this turn added (new content, not from cache)
        added = self.new_tokens

        # What was reused from cache (excluding system prompt baseline)
        reused = max(0, self.cache_read_tokens - baseline_cache)

        parts = [f"+{added}"]
        if reused > 0:
            parts.append(f"reused:{reused}")
        parts.append(f"out:{self.output_tokens}")
        parts.append(f"${self.cost_usd:.4f}")

        return " ".join(parts)

    def format_verbose(self, baseline_cache: int = 0) -> str:
        """Multi-line detailed breakdown for display after each turn.

        Args:
            baseline_cache: System prompt tokens to subtract from cache_read
                           to show only user-relevant cached content.
        """
        user_cache_read = max(0, self.cache_read_tokens - baseline_cache)

        lines = [
            f"  input: {self.input_tokens} (uncached) + {self.cache_creation_tokens} (newly cached) = {self.new_tokens} new tokens",
            f"  cache: {user_cache_read} tokens reused from previous turns" + (f" (+{baseline_cache} system prompt)" if baseline_cache > 0 else ""),
            f"  output: {self.output_tokens} tokens",
            f"  cost: ${self.cost_usd:.4f}",
        ]
        return "\n".join(lines)


@dataclass
class UsageTracker:
    """Accumulates usage across conversation turns."""
    turns: list[TurnUsage] = field(default_factory=list)

    # Track the baseline (Claude Code system prompt) separately
    system_prompt_tokens: int = 0
    system_prompt_detected: bool = False

    def record_turn(self, usage_dict: dict | None, cost_usd: float | None) -> TurnUsage:
        """Record usage from a ResultMessage and return the TurnUsage."""
        turn = TurnUsage()

        if usage_dict:
            turn.input_tokens = usage_dict.get('input_tokens', 0)
            turn.output_tokens = usage_dict.get('output_tokens', 0)
            turn.cache_creation_tokens = usage_dict.get('cache_creation_input_tokens', 0)
            turn.cache_read_tokens = usage_dict.get('cache_read_input_tokens', 0)

        if cost_usd:
            turn.cost_usd = cost_usd

        # Detect system prompt on first turn (it's the cache_read on turn 1)
        if not self.system_prompt_detected and len(self.turns) == 0:
            # First turn's cache_read is mostly the Claude Code system prompt
            self.system_prompt_tokens = turn.cache_read_tokens
            self.system_prompt_detected = True

        self.turns.append(turn)
        return turn

    @property
    def total_input_tokens(self) -> int:
        """Sum of all input tokens across turns."""
        return sum(t.total_input for t in self.turns)

    @property
    def total_output_tokens(self) -> int:
        """Sum of all output tokens across turns."""
        return sum(t.output_tokens for t in self.turns)

    @property
    def total_cost_usd(self) -> float:
        """Sum of all costs across turns."""
        return sum(t.cost_usd for t in self.turns)

    @property
    def total_cache_read(self) -> int:
        """Sum of cache read tokens across turns."""
        return sum(t.cache_read_tokens for t in self.turns)

    @property
    def total_cache_creation(self) -> int:
        """Sum of cache creation tokens across turns."""
        return sum(t.cache_creation_tokens for t in self.turns)

    @property
    def user_content_tokens(self) -> int:
        """Estimate of user-added content (excluding system prompt)."""
        # This is approximate - subtract system prompt from total cache
        if self.system_prompt_tokens > 0:
            return self.total_cache_creation + max(0, self.total_cache_read - self.system_prompt_tokens * len(self.turns))
        return self.total_cache_creation

    def format_summary(self) -> str:
        """Format a full usage summary."""
        lines = [
            "Session Usage Summary",
            "─" * 40,
            f"  Turns: {len(self.turns)}",
            f"  Total input tokens: {self.total_input_tokens:,}",
            f"  Total output tokens: {self.total_output_tokens:,}",
            f"  Cache efficiency:",
            f"    - Created: {self.total_cache_creation:,} tokens",
            f"    - Read: {self.total_cache_read:,} tokens",
        ]

        if self.system_prompt_tokens > 0:
            lines.append(f"    - System prompt: ~{self.system_prompt_tokens:,} tokens (baseline)")

        lines.extend([
            f"  Total cost: ${self.total_cost_usd:.4f}",
            "─" * 40,
        ])

        return "\n".join(lines)

    def reset(self) -> None:
        """Reset for a new session."""
        self.turns = []
        self.system_prompt_tokens = 0
        self.system_prompt_detected = False
