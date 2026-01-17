#!/usr/bin/env python3
"""Writing Agent - A Claude-powered writing assistant.

A CLI tool for working with blog/writing projects.
"""

import asyncio
import sys
import yaml
import os
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass

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
      HookMatcher,
      ResultMessage,
      TextBlock,
      ToolUseBlock,
      UserMessage,
      query,
  )

from claude_agent_sdk.types import HookInput, HookContext, HookJSONOutput

context_store = ContextStore()
usage_tracker = UsageTracker()

# Default system prompt - customize this for your writing style
SYSTEM_PROMPT = """You are a writing assistant helping with writing (usually blog) content.

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


# Load the blog config details
def load_config() -> dict:
    """Load blog configuration from the config file"""
    config_path = Path(__file__).parent.parent.parent / "config.yaml"
    if config_path.exists():
        with open(config_path) as f:
            return yaml.safe_load(f)
    return {}

# we need this to store metadata about checkpoints
@dataclass
class Checkpoint:
    uuid: str
    turn: int
    timestamp: datetime
    summary: str = ""  # Brief description from Haiku


config = load_config()

big_model = "opus"
medium_model = "sonnet"
small_model = "haiku"

async def bash_permission_hook(
        input_data: HookInput,
        tool_use_id: str | None,
        context: HookContext
    ) -> HookJSONOutput:
    """Prompt user for every Bash comand"""
    if input_data.get("hook_event_name") != "PreToolUse":
        return {"continue_": True}
    if input_data.get("tool_name") != "Bash":
        return {"continue_": True}

    command = input_data.get("tool_input", {}).get("command", "")
    print(f"\n{META}Bash permission requested:{RESET}")
    print(f"{CODE}  {command}{RESET}")
    response = input(f"{USER}Allow? [y/n]: {RESET}")

    if response.lower() == 'y':
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "allow",
            }
        }
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": "User denied this command"
        }
    }


async def summarize_turn(user_prompt: str, tool_calls: list[str]) -> str:
    """Use Haiku to generate a brief summary of what happened this turn."""
    summary_prompt = f"""Summarize this interaction in 10 words or less.
User asked: {user_prompt[:200]}
Tools used: {', '.join(tool_calls) if tool_calls else 'none'}
Reply with ONLY the summary, no explanation."""

    try:
        summary = ""
        async for msg in query(
            prompt=summary_prompt,
            options=ClaudeAgentOptions(
                model=small_model,
                allowed_tools=[],  # No tools needed for summary
            )
        ):
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        summary += block.text
        return summary.strip()[:50]  # Cap at 50 chars just in case
    except Exception:
        return "(summary unavailable)"


async def run_agent(blog_path: Path | None = None):
    """Run the interactive writing agent."""

    # Agent home = where .claude/commands/ and config.yaml live
    agent_home = Path(__file__).parent.parent.parent

    # Blog directory - CLI arg overrides config
    if blog_path:
        blog_dir = blog_path
    elif config.get("blog", {}).get("path"):
        blog_dir = Path(config["blog"]["path"])
    else:
        blog_dir = None

    # Add blog path to system prompt
    system_prompt = SYSTEM_PROMPT
    if blog_dir:
        system_prompt += f"\n\nThe blog you're helping with is located at: {blog_dir}"


    # Startup banner
    print(f"{BANNER}Writing Agent starting...{RESET}")
    print(f"{BANNER}Agent Home: {PATH}{agent_home}{RESET}")
    print(f"{BANNER}Blog directory: {PATH}{blog_dir}{RESET}")
    print(f"{BANNER}Type 'quit' or 'exit' to stop, 'clear' to reset conversation{RESET}\n")

    options = ClaudeAgentOptions(
        system_prompt=system_prompt,
        model=medium_model, # set to sonnet for time being
        allowed_tools=["Read", "Write", "Edit","Glob", "Grep"], #removed Bash
        hooks = {
            "PreToolUse": [
                HookMatcher(
                    matcher="Bash",
                    hooks=[bash_permission_hook],
                    timeout=120
                )
            ]
        },
        cwd=str(agent_home),
        setting_sources=["project"],
        enable_file_checkpointing=True,
        extra_args={"replay-user-messages": None},  # Required to get checkpoint UUIDs
        env={**os.environ, "CLAUDE_CODE_ENABLE_SDK_FILE_CHECKPOINTING": "1"},  # Required env var
    )

    # Checkpoint tracking for file rewinds
    checkpoints: list[Checkpoint] = []
    session_id: str | None = None
    pending_file_tool: bool = False  # True when we're waiting for tool result after Write/Edit

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
                elif user_input == "/rewind":
                    if not checkpoints:
                        print (f"{META}: No checkpoints available yet.{RESET}")
                        continue
                    print (f"{META}Available Checkpoints: {RESET}")
                    for i, cp in enumerate(checkpoints):
                        summary_display = f" - {cp.summary}" if cp.summary else ""
                        print (f"    {i}: Turn {cp.turn} @ {cp.timestamp.strftime('%H:%M:%S')}{summary_display}")
                    idx = await session.prompt_async("Rewind to checkpoint: ")
                    try:
                        target = checkpoints[int(idx)]
                        # warn user
                        print(f"{ERROR}⚠ WARNING: This is destructive!{RESET}")
                        print(f"{ERROR}  Files will be restored to turn {target.turn}.{RESET}")
                        print(f"{ERROR}  Changes after this point will be PERMANENTLY LOST.{RESET}")
                        confirm = await session.prompt_async("Type 'yes' to confirm: ")
                        if confirm.lower() != "yes":
                            print(f"{META}Rewind cancelled.{RESET}")
                            continue

                        # Call rewind on the SAME client (checkpoints are in CLI memory)
                        try:
                            await client.rewind_files(target.uuid)
                            print(f"{META}✅ Rewound to turn {target.turn}{RESET}")
                            # Clear checkpoints later than rewind point
                            checkpoints[:] = checkpoints[:int(idx)]
                        except Exception as rewind_error:
                            print(f"{ERROR}Rewind failed: {rewind_error}{RESET}")
                            print(f"{META}(Checkpoint may not have a file backup - this is a known SDK limitation){RESET}")
                    except (ValueError, IndexError) as e:
                        print(f"{ERROR}Error: {e}{RESET}")
                        continue


                # Send to Claude
                await client.query(user_input)

                # Stream the response
                print(f"\n{ASSISTANT}Assistant:{RESET} ", end="", flush=True)

                # Track checkpoint - capture FIRST UserMessage (the prompt echo, before edits)
                turn_checkpoint_captured = False
                turn_tool_calls: list[str] = []  # Track tools used this turn

                async for msg in client.receive_response():
                    # Capture first UserMessage as checkpoint (represents state BEFORE edits)
                    if isinstance(msg, UserMessage) and msg.uuid and not turn_checkpoint_captured:
                        checkpoints.append(Checkpoint(
                            uuid=msg.uuid,
                            turn=len(checkpoints) + 1,
                            timestamp=datetime.now()
                        ))
                        turn_checkpoint_captured = True

                    if isinstance(msg, AssistantMessage):
                        for block in msg.content:
                            if isinstance(block, TextBlock):
                                print(block.text, end="", flush=True)
                            elif isinstance(block, ToolUseBlock):
                                print(f"\n{CODE}[{block.name}: {block.input}]{RESET}", end="", flush=True)
                                turn_tool_calls.append(block.name)

                    elif isinstance(msg, ResultMessage):
                        session_id = msg.session_id
                        turn = usage_tracker.record_turn(msg.usage, msg.total_cost_usd)
                        print(f"\n{META}{turn.format_verbose(usage_tracker.system_prompt_tokens)}{RESET}")

                        # Get summary from Haiku for the checkpoint (if we captured one)
                        if turn_checkpoint_captured and checkpoints:
                            print(f"{META}(summarizing...){RESET}", end="", flush=True)
                            summary = await summarize_turn(user_input, turn_tool_calls)
                            checkpoints[-1].summary = summary
                            print(f" {summary}")


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
