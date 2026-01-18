---
title: "Claude Agent SDK Parte 7: Creación de Herramientas MCP Personalizadas"
date: 2026-02-02T06:30:00Z
slug: /02-02-claude-agent-sdk-part-7/
description: "Exposing Python functions as tools Claude can call directly"
image: images/2026/02-02-claude-agent-sdk-part-7.png
caption: "TBD"
categories:
  - coding
  - artificial-intelligence
  - feature
tags:
  - claude
  - agent-sdk
  - python
  - learning
  - feature
draft: true
---

In [Part 5](/posts/2026/02-09-claude-agent-sdk-part-5/), I added file checkpointing with a `/rewind` command. But `/rewind` isn't a real slash command - it's just my Python code pattern-matching on the input string. Claude has no idea the capability exists. If something goes wrong with an edit, Claude can't decide to rewind on its own.

In this post, I'm fixing that by exposing rewind as a proper MCP tool that Claude can call directly.

## What MCP Tools Are (And Aren't)

MCP stands for Model Context Protocol. The SDK lets you create "MCP servers" - but don't let the name mislead you. These aren't separate processes listening on ports. They're in-process collections of tool definitions that get registered with Claude.

The pattern:
1. Define functions with the `@tool` decorator
2. Bundle them into a "server" with `create_sdk_mcp_server()`
3. Pass the server to `ClaudeAgentOptions`
4. Claude can now call your functions like any other tool

## The Rewind Tool

Here's the tool definition:

```python
from claude_agent_sdk import tool, create_sdk_mcp_server
from typing import Any

@tool(
    "rewind_files",
    "Rewind edited files to a previous checkpoint. Use this to undo mistakes.",
    {"checkpoint_index": int}
)
async def rewind_files_tool(args: dict[str, Any]) -> dict[str, Any]:
    """Rewind to a specific checkpoint."""
    index = args["checkpoint_index"]

    if index < 0 or index >= len(state.checkpoints):
        return {
            "content": [{
                "type": "text",
                "text": f"Invalid checkpoint index. Available: 0-{len(state.checkpoints)-1}"
            }]
        }

    target = state.checkpoints[index]

    try:
        await state.client.rewind_files(target.uuid)
        return {
            "content": [{
                "type": "text",
                "text": f"Rewound to checkpoint {index}: {target.summary}"
            }]
        }
    except Exception as e:
        return {
            "content": [{
                "type": "text",
                "text": f"Rewind failed: {str(e)}"
            }]
        }
```

The `@tool` decorator takes three arguments:
- **Name**: How Claude refers to the tool (`"rewind_files"`)
- **Description**: Helps Claude understand when to use it
- **Schema**: The expected arguments - here just `{"checkpoint_index": int}`

The return format is specific to MCP - a dict with a `content` array containing text blocks. This is how tool results get passed back to Claude.

## Creating the Server

Bundle the tool into a server:

```python
writing_agent_server = create_sdk_mcp_server(
    name="writing-agent-tools",
    version="1.0.0",
    tools=[rewind_files_tool]
)
```

The server name matters - it becomes part of the tool's full name. Claude will see this tool as `mcp__writing-agent-tools__rewind_files`.

## Wiring It Up

Add the server to your agent options:

```python
options = ClaudeAgentOptions(
    system_prompt=system_prompt,
    mcp_servers={"writing-agent-tools": writing_agent_server},
    allowed_tools=[
        "Read", "Write", "Edit", "Glob", "Grep",
        "mcp__writing-agent-tools__rewind_files"
    ],
    # ... other options
)
```

The `mcp_servers` parameter is a dictionary mapping server names to server objects. The `allowed_tools` list now includes our custom tool using the `mcp__server-name__tool-name` format.

## Adding Permission Control

Rewind is destructive - it overwrites files. I don't want Claude auto-rewinding without asking. Using the same hook pattern from [Part 6](/posts/2026/02-16-claude-agent-sdk-part-6/):

```python
async def rewind_permission_hook(
    input_data: HookInput,
    tool_use_id: str | None,
    context: HookContext
) -> HookJSONOutput:
    """Prompt user before rewinding."""
    if input_data.get("hook_event_name") != "PreToolUse":
        return {}
    if input_data.get("tool_name") != "mcp__writing-agent-tools__rewind_files":
        return {}

    tool_input = input_data.get("tool_input", {})
    index = tool_input.get("checkpoint_index", 0)

    if index < 0 or index >= len(state.checkpoints):
        print(f"\n{ERROR}Invalid checkpoint index: {index}{RESET}")
        return {
            "continue_": False,
            "stopReason": "Invalid checkpoint"
        }

    target = state.checkpoints[index]

    print(f"\n{META}Rewind requested:{RESET}")
    print(f"{CODE}  Checkpoint {index}: Turn {target.turn} @ {target.timestamp.strftime('%H:%M:%S')}{RESET}")
    print(f"{CODE}  Summary: {target.summary}{RESET}")
    response = input(f"{USER}Allow rewind? [y/n]: {RESET}")

    if response.lower() == 'y':
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "allow",
            }
        }
    print(f"{META}(Rewind denied - returning to prompt){RESET}")
    return {
        "continue_": False,
        "stopReason": "User denied rewind"
    }
```

And add it to the hooks configuration:

```python
hooks={
    "PreToolUse": [
        HookMatcher(
            matcher="Bash",
            hooks=[bash_permission_hook],
            timeout=120
        ),
        HookMatcher(
            matcher="mcp__writing-agent-tools__rewind_files",
            hooks=[rewind_permission_hook],
            timeout=120
        )
    ]
}
```

Now when Claude decides to rewind, the user sees exactly which checkpoint it's targeting and can approve or deny.

## The Scope Problem

There's an issue with my implementation above. The `rewind_files_tool` function references `checkpoints` and `client` - but those are defined inside `run_agent()`, not at module scope where the tool is decorated.

The `@tool` decorator runs at module load time. The function body runs later when Claude calls the tool. At that point, it can only see module-level names - not local variables inside `run_agent()`.

The fix is a state object that lives at module level but gets populated at runtime:

```python
from dataclasses import dataclass, field

@dataclass
class AgentState:
    """Runtime state accessible to MCP tools."""
    checkpoints: list[Checkpoint] = field(default_factory=list)
    client: ClaudeSDKClient | None = None
    session_id: str | None = None

state = AgentState()
```

Now the tool function references `state.checkpoints` and `state.client`. Inside `run_agent()`, we populate the state:

```python
async def run_agent():
    state.checkpoints = []
    state.session_id = None

    async with ClaudeSDKClient(options=options) as client:
        state.client = client
        # ... rest of the code uses state.checkpoints instead of checkpoints
```

This avoids raw globals (no `global` keyword needed) and makes it clear what's runtime state versus constants.

## Testing It

With the tool wired up, Claude can now decide to rewind on its own:

<!-- TODO: Screenshot of Claude using the rewind tool -->

If I ask Claude to make an edit and it goes wrong, Claude can recognise the mistake and offer to rewind - something it couldn't do before when rewind was just a Python string match.

## What's Next

The rewind tool is just the start. The same pattern works for any Python function I want to expose to Claude:
- Starting/stopping the Hugo dev server
- Running the build script to deploy
- Checking git status
- Opening files in VS Code

MCP tools turn the agent from a passenger into someone who can actually operate the controls.

---

*This is Part 7 of my series on learning the Claude Agent SDK. [Part 1](/posts/2026/01-12-exploring-claude-agent-sdk/) covers initial exploration, [Part 2](/posts/2026/01-19-claude-agent-sdk-part-2/) builds the first working agent, [Part 3](/posts/2026/01-26-claude-agent-sdk-part-3/) tackles context control, [Part 4](/posts/2026/02-02-claude-agent-sdk-part-4/) adds usage tracking, [Part 5](/posts/2026/02-09-claude-agent-sdk-part-5/) introduces checkpointing, and [Part 6](/posts/2026/02-16-claude-agent-sdk-part-6/) fixes the Bash bypass problem.*
