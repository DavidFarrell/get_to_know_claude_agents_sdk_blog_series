#!/usr/bin/env python3
"""Writing Agent - A Claude-powered writing assistant.

A CLI tool for working with your blog/writing projects.
"""

import asyncio
import sys
from pathlib import Path

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
)


# Default system prompt - customize this for your writing style
SYSTEM_PROMPT = """You are a writing assistant helping with blog content.

You have access to the user's blog folder and can:
- Read existing posts to understand their style and topics
- Help draft, edit, and improve content
- Run shell commands when needed (e.g., for git operations)

Be concise but helpful. When reading files, summarize what you find rather than
dumping entire contents unless asked.
"""


async def run_agent(blog_path: Path | None = None):
    """Run the interactive writing agent."""

    # Determine working directory
    cwd = blog_path or Path.cwd()
    print(f"Writing Agent starting...")
    print(f"Working directory: {cwd}")
    print(f"Type 'quit' or 'exit' to stop, 'clear' to reset conversation\n")

    options = ClaudeAgentOptions(
        system_prompt=SYSTEM_PROMPT,
        allowed_tools=["Read", "Write", "Edit", "Bash", "Glob", "Grep"],
        cwd=str(cwd),
    )

    async with ClaudeSDKClient(options=options) as client:
        while True:
            # Get user input
            try:
                user_input = input("\nYou: ").strip()
            except (KeyboardInterrupt, EOFError):
                print("\nGoodbye!")
                break

            if not user_input:
                continue

            if user_input.lower() in ("quit", "exit"):
                print("Goodbye!")
                break

            if user_input.lower() == "clear":
                # Reconnect to start fresh
                print("(Conversation cleared)")
                continue

            # Send to Claude
            await client.query(user_input)

            # Stream the response
            print("\nAssistant: ", end="", flush=True)

            async for msg in client.receive_response():
                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, TextBlock):
                            print(block.text, end="", flush=True)
                        elif isinstance(block, ToolUseBlock):
                            print(f"\n[Using {block.name}...{block.s}]", end="", flush=True)

                elif isinstance(msg, ResultMessage):
                    if msg.total_cost_usd and msg.total_cost_usd > 0:
                        print(f"\n(Cost: ${msg.total_cost_usd:.4f})")
                    else:
                        print()  # Newline after response


def main():
    """Entry point."""
    # Simple arg parsing - just an optional path
    blog_path = None
    if len(sys.argv) > 1:
        blog_path = Path(sys.argv[1]).resolve()
        if not blog_path.exists():
            print(f"Error: Path does not exist: {blog_path}")
            sys.exit(1)

    try:
        asyncio.run(run_agent(blog_path))
    except KeyboardInterrupt:
        print("\nInterrupted")


if __name__ == "__main__":
    main()
