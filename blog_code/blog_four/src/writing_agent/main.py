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

# for path completion (tab etc)
from prompt_toolkit.completion import PathCompleter

# our classes
from writing_agent.context import ContextStore
from writing_agent.usage import UsageTracker

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
)

context_store = ContextStore()
usage_tracker = UsageTracker()

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

@bindings.add('enter')
def submit(event):
    """Enter submits the input."""
    event.current_buffer.validate_and_handle()

@bindings.add('escape', 'enter')  # Option+Enter on Mac
def newline(event):
    """Option+Enter inserts a newline."""
    event.current_buffer.insert_text('\n')

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

    # create a session for async prompting
    # this is how we support multiline inputs
    session = PromptSession(key_bindings=bindings)

    # Outer loop: each iteration creates a fresh client/session
    while True:
        async with ClaudeSDKClient(options=options) as client:
            # Inject enabled context at the start of each new session
            context_block = context_store.get_enabled_content()
            if context_block:
                enabled_count = sum(1 for item in context_store.items if item.enabled)
                print(f"{META}Injecting {enabled_count} context item(s)...{RESET}")
                await client.query(f"[CONTEXT]\n{context_block}\n[/CONTEXT]\nAcknowledge briefly.")
                # Consume the response and track usage
                async for msg in client.receive_response():
                    if isinstance(msg, ResultMessage):
                        turn = usage_tracker.record_turn(msg.usage, msg.total_cost_usd)
                        print(f"{META}(context injection)\n{turn.format_verbose(usage_tracker.system_prompt_tokens)}{RESET}")
                        break

            # Inner loop: conversation turns within this session
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
                    return  # Exit completely

                if not user_input:
                    continue

                if user_input.lower() in ("quit", "exit"):
                    print("Goodbye!")
                    return  # Exit completely

                if user_input.lower() in ("clear", "new", "/clear", "/new"):
                    print(f"{META}(Starting fresh session...){RESET}")
                    usage_tracker.reset()
                    break  # Break inner loop → new client

                if user_input == "/usage":
                    print(f"{META}{usage_tracker.format_summary()}{RESET}")
                    continue

                if user_input == "/context-status":
                    print(context_store.list())
                    continue
                elif user_input == "/add-context":
                    path = await session.prompt_async("Path: ", completer=PathCompleter())
                    item = context_store.add(path)
                    # Inject into current conversation and capture actual token count
                    await client.query(f"[CONTEXT]\n[FILE:{item.path}]\n{item.content}\n[/CONTEXT]\nAcknowledge briefly.")
                    async for msg in client.receive_response():
                        if isinstance(msg, ResultMessage):
                            turn = usage_tracker.record_turn(msg.usage, msg.total_cost_usd)
                            item.tokens = turn.new_tokens  # actual count from SDK
                            print(f"added {item.path} ({item.tokens} tokens)")
                            print(f"{META}{turn.format_verbose(usage_tracker.system_prompt_tokens)}{RESET}")
                            break
                    continue
                elif user_input == "/toggle-context":
                    print(context_store.list())
                    index = await session.prompt_async("Which index to toggle?: ")
                    try:
                        context_store.toggle(int(index))
                    except (ValueError, IndexError) as e:
                        print(f"Error: {e}")
                    continue
                elif user_input == "/remove-context":
                    print(context_store.list())
                    index = await session.prompt_async("Which index to remove?: ")
                    try:
                        context_store.remove(int(index))
                        print(context_store.list())
                    except (ValueError, IndexError) as e:
                        print(f"Error: {e}")
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
                        # Record and display usage
                        turn = usage_tracker.record_turn(msg.usage, msg.total_cost_usd)
                        print(f"\n{META}{turn.format_verbose(usage_tracker.system_prompt_tokens)}{RESET}")


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
