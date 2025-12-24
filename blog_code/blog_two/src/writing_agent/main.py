#!/usr/bin/env python3
"""Writing Agent - A Claude-powered writing assistant.

A CLI tool for working with your blog/writing projects.
"""

import asyncio
import sys
from pathlib import Path

# for multi line support
from prompt_toolkit import PromptSession
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.formatted_text import ANSI

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

# ─── Colors ───────────────────────────────────────────────
ESC = "\033["
RESET = f"{ESC}0m"

BANNER = f"{ESC}38;2;156;147;138m"    # warm taupe gray
USER = f"{ESC}38;2;86;148;148m"       # muted teal
ASSISTANT = f"{ESC}38;2;217;119;87m"  # coral/terracotta
META = f"{ESC}38;2;180;156;120m"      # muted amber
ERROR = f"{ESC}38;2;204;82;82m"       # warm red
CODE = f"{ESC}38;2;140;160;160m"      # blue-gray for tool calls
PATH = f"{ESC}38;2;120;140;180m"      # soft blue
# ──────────────────────────────────────────────────────────

bindings = KeyBindings()
@bindings.add('escape', 'enter') # this is Option+Enter on the Mac
def submit(event):
    event.current_buffer.validate_and_handle()

async def run_agent(blog_path: Path | None = None):
    """Run the interactive writing agent."""

    # Determine working directory
    cwd = blog_path or Path.cwd()
    # Startup banner
    print(f"{BANNER}Writing Agent starting...{RESET}")
    print(f"{BANNER}Working directory: {PATH}{cwd}{RESET}")
    print(f"{BANNER}Type 'quit' or 'exit' to stop, 'clear' to reset conversation{RESET}\n")

    options = ClaudeAgentOptions(
        system_prompt=SYSTEM_PROMPT,
        allowed_tools=["Read", "Write", "Edit", "Bash", "Glob", "Grep"],
        cwd=str(cwd),
    )

    # create a session form async prompting
    # this is how we support multiline inputs
    session = PromptSession(key_bindings=bindings)

    async with ClaudeSDKClient(options=options) as client:
        while True:
            # Get user input
            try:
                user_input = (await session.prompt_async(
                    ANSI(f"\n{USER}You:{RESET} "),
                    multiline=True,
                    prompt_continuation="",
                )).strip()

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
            print(f"\n{ASSISTANT}Assistant:{RESET} ", end="", flush=True)

            async for msg in client.receive_response():
                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, TextBlock):
                            print(block.text, end="", flush=True)
                        elif isinstance(block, ToolUseBlock):
                            print(f"\n{CODE}[{block.name}: {block.input}]{RESET}", end="", flush=True)

                elif isinstance(msg, ResultMessage):
                    if msg.total_cost_usd and msg.total_cost_usd > 0:
                        print(f"\n{META}(Cost: ${msg.total_cost_usd:.4f}){RESET}")
                    else:
                        print()  # Newline after response


def main():
    """Entry point."""
    # Simple arg parsing - just an optional path
    blog_path = None
    if len(sys.argv) > 1:
        blog_path = Path(sys.argv[1]).resolve()
        if not blog_path.exists():
            print(f"{ERROR}Error: Path does not exist: {blog_path}{RESET}")
            sys.exit(1)

    try:
        asyncio.run(run_agent(blog_path))
    except KeyboardInterrupt:
        print("\nInterrupted")


if __name__ == "__main__":
    main()
