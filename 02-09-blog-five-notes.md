# Blog 5 Notes - Template Handling & Slash Commands

**Target date:** 2026-02-09

## Architecture Decision

Everything lives in the writing-agent repo (not split across repos). This keeps the complete working system trackable in one place.

## Proposed Structure

```
writing-agent/
├── .claude/
│   └── commands/
│       ├── new-post.md      # /new-post command
│       └── publish.md       # /publish command (future)
├── config.yaml              # Blog path, templates, etc.
├── src/writing_agent/
│   ├── main.py
│   ├── context.py
│   └── usage.py
└── pyproject.toml
```

## The `/new-post` Command

- Read blog path from config (or use a default)
- Use the Write tool to create the post file
- Apply front matter template from config
- Be fully checkpoint-compliant (Write/Edit tools only, no Bash for file ops)

## Config Approach

```yaml
# config.yaml
blog:
  path: /Users/david/git/ai-sandbox/projects/websites/thingsithinkithink.blog
  posts_folder: content/posts
  images_folder: assets/images
  front_matter_template: |
    title: "$TITLE"
    date: $DATE
    slug: /$SLUG/
    description: ""
    image: images/$YEAR/$SLUG.png
    caption: "TBD"
    categories: []
    tags: []
    draft: true
```

## Key Documentation

- [Slash Commands in Agent SDK](https://platform.claude.com/docs/en/agent-sdk/slash-commands)
- [File Checkpointing](https://platform.claude.com/docs/en/agent-sdk/file-checkpointing)

## Slash Command Features We Can Use

From the docs:
- `$1`, `$2` for positional args, `$ARGUMENTS` for all args
- `@filename` to include file contents (e.g., `@config.yaml`)
- `!`command`` to include bash output
- `allowed-tools` frontmatter to restrict tools
- `argument-hint` for usage hints

## Blog Post Writing Notes

Things to explain in the blog post:

1. **The `.claude/commands/` folder**
   - Where custom slash commands live
   - Project-specific vs personal (`~/.claude/commands/`)
   - Filename becomes the command name (e.g., `new-post.md` → `/new-post`)

2. **Slash command file format**
   - Has its own YAML frontmatter (meta-frontmatter!)
   - `allowed-tools`: Restrict which tools the command can use
   - `argument-hint`: Shows users what args are expected
   - `description`: Appears in command listings

3. **Why we chose `allowed-tools: Write, Read, Glob`**
   - **Write**: Obviously needed to create the post file (and checkpoint-compliant)
   - **Read**: Claude might need to read other posts for context - e.g., "create a new post continuing this series, using the same format as previous posts" or checking what was promised in a "What's Next" section
   - **Glob**: Useful for discovering existing posts - e.g., finding the date pattern to suggest "next Monday in the series"
   - **Excluded Bash**: Intentionally, for checkpoint compliance - all file ops go through Write/Edit

4. **Arguments are AI-interpreted**
   - Unlike traditional CLI parsers, arguments don't need to be perfectly structured
   - Claude reads and interprets `$ARGUMENTS` based on the instructions
   - This means flexible input: `/new-post My Title 2026-03-15` works without strict parsing
   - Trade-off: Less rigid, but more forgiving and natural

5. **The `@filename` syntax**
   - Include file contents directly in the command prompt
   - Our command uses `@config.yaml` to read blog settings

6. **The `cwd` gotcha - slash commands need the right working directory**
   - Claude Code looks for `.claude/commands/` in the `cwd` specified in `ClaudeAgentOptions`
   - If your agent's `cwd` is set to a target folder (like the blog), Claude won't find commands in your agent's folder
   - **The tension:** We want Claude to **find commands** in writing-agent but **work on files** in the blog folder
   - **Solution:** Set `cwd` to the agent's home folder (use `Path(__file__).parent.parent.parent` for robustness), pass the blog path via system prompt
   - Claude can work with files anywhere using absolute paths - `cwd` just affects relative paths and command discovery
   - The blog path becomes configuration data, not the working directory

7. **The `setting_sources` gotcha - SDK doesn't load filesystem settings by default!**
   - **The problem:** Even with correct `cwd`, slash commands still weren't found
   - **Root cause:** By default, the SDK does NOT load any filesystem settings (for isolation)
   - **Documentation:** [Agent SDK reference - Python](https://platform.claude.com/docs/en/agent-sdk/python) - see `SettingSource` section
   - **The fix:** Add `setting_sources=["project"]` to `ClaudeAgentOptions`
   - Available sources:
     - `"user"` - Global settings from `~/.claude/`
     - `"project"` - Project settings from `.claude/` in cwd (includes slash commands!)
     - `"local"` - Local gitignored settings from `.claude-local/`
   - This is a deliberate security/isolation feature - SDK apps start clean, you opt into what you load

   ```python
   options = ClaudeAgentOptions(
       cwd=str(agent_home),           # Where .claude/commands/ lives
       setting_sources=["project"],   # Load project settings (including slash commands!)
       ...
   )
   ```

## Screenshots for Blog Post

- **`02-09-slash-command-working.png`** - Shows the agent finding `/new-post` after adding `setting_sources=["project"]`. Use this after explaining the setting_sources gotcha - it's the "success" moment. Shows:
  - Agent startup with correct Agent Home and Blog directory
  - User asking "Can you tell me what slash commands you have?"
  - Claude responding with the `/new-post` command, description, and examples
  - Usage stats visible

- **`02-09-new-post-agentic-workflow.png`** - Shows multiple agentic capabilities working together in one flow. This is the "wow" screenshot demonstrating the power of slash commands + tools + natural language. The story:
  1. **User asks:** "What have I named the blogs in my Claude Agent SDK series?"
  2. **Claude uses Glob** to search for posts (multiple patterns tried)
  3. **Claude uses Grep** to extract titles from the posts
  4. **Claude lists all 4 posts** with their dates: Jan 12, 19, 26, Feb 2 (all Mondays!)
  5. **User invokes `/new-post`** with natural language: "Give the new post a similar name. It's part five, and what I'm doing today is exploring slash commands and file checkpointing. And for the date, can you give it the next Monday in the sequence?"
  6. **Claude figures out the pattern** - recognizes the Monday sequence, calculates Feb 9, 2026
  7. **Claude uses Write tool** to create the post with proper front matter
  8. **Shows the result** - file path, generated front matter, and helpful reminders

  **Why this is cool:**
  - No rigid argument parsing - natural language worked fine
  - Claude used its tools (Glob, Grep) to gather context before acting
  - Pattern recognition on dates - understood "next Monday in the sequence"
  - Combined slash command with prior conversation context
  - Created well-structured output following the template

## Current Implementation Status

**Done:**
- ✅ `config.yaml` - blog path, templates, date formats
- ✅ `.claude/commands/new-post.md` - slash command created
- ✅ `main.py` loads config at startup
- ✅ `pyproject.toml` updated with pyyaml
- ✅ `enable_file_checkpointing=True` added to options
- ✅ Fixed `cwd` - now uses `agent_home = Path(__file__).parent.parent.parent`
- ✅ Blog path passed to Claude via system prompt

**Next steps:**
- [x] Add `setting_sources=["project"]` to ClaudeAgentOptions ✅
- [x] Test `/new-post` command is discovered ✅ (see screenshot 1)
- [x] Test `/new-post` command actually creates a post ✅ (see screenshot 2 - agentic workflow)
- [x] Implement file checkpointing with `/rewind` command ✅
- [x] Debug and fix checkpoint UUID capture (was capturing wrong UserMessage) ✅

**Key files:**
- `writing-agent/src/writing_agent/main.py` - main agent code
- `writing-agent/config.yaml` - blog configuration
- `writing-agent/.claude/commands/new-post.md` - slash command

## Architecture Insight: Slash Commands vs MCP Tools

**Key learning (for future blog post):**

Slash commands are just **markdown prompts** that get expanded for Claude. They can tell Claude *what to do*, but Claude can only do things it has *tools* for.

| Want Claude to... | Use... |
|-------------------|--------|
| Read/write files, run bash, etc. | Built-in tools (Read, Write, Bash) |
| Call your custom Python functions | Custom MCP tools |
| Follow a workflow with instructions | Slash commands |

**The `/rewind` problem:**
- Slash command can tell Claude "help the user rewind"
- But `rewind_files()` is a Python SDK method, not a Claude tool
- Checkpoints are stored in Python memory, not accessible to Claude

**Two approaches:**
1. **Simple:** Handle `/rewind` in Python directly (what we're doing now)
2. **Elegant:** Create custom MCP tools (`@tool` decorator) that Claude can call, wire slash command to them

The MCP approach is more powerful—it lets slash commands trigger your Python code through Claude. But it's more complex. Good topic for a future post.

**For Blog 5:** We're hard-coding `/rewind` in the Python input handler. It works, it's simple, and it demonstrates the concept.

## How File Checkpointing Actually Works

**Key insight: Checkpoints are tied to tool RESULTS, not prompts**

The Claude Code CLI internally tracks file state, but the crucial detail is WHEN the checkpoint is created and which message carries its UUID.

**The `replay-user-messages` flag:**
- Normally, the response stream only contains `AssistantMessage` and `ResultMessage`
- With `extra_args={"replay-user-messages": None}`, the CLI sends `UserMessage` objects into the stream
- These carry UUIDs that serve as checkpoint handles
- Without this flag, checkpoints still exist internally but you can't reference them

**The actual message flow (this took debugging to figure out!):**
```python
# You send:
await client.query("edit my file")

# You receive (with replay-user-messages):
UserMessage(uuid="abc-123")        # ← Your prompt echoed back (NOT the checkpoint!)
AssistantMessage(tool_use=Edit)    # ← Claude decides to edit
# [Tool executes, checkpoint created AFTER file changes]
UserMessage(uuid="def-456")        # ← Tool result message (THIS is the checkpoint!)
AssistantMessage(text="Done!")     # ← Claude's final response
ResultMessage(session_id="xyz")    # ← Final stats
```

**Critical insight:** The checkpoint is created AFTER the tool runs, and the UUID is on the `UserMessage` that carries the tool result—NOT the one that echoes your prompt.

**Implementation pattern:**
```python
pending_file_tool = False

async for msg in client.receive_response():
    # Capture checkpoint from UserMessage AFTER a file tool executes
    if isinstance(msg, UserMessage) and msg.uuid and pending_file_tool:
        checkpoints.append(Checkpoint(uuid=msg.uuid, ...))
        pending_file_tool = False

    if isinstance(msg, AssistantMessage):
        for block in msg.content:
            if isinstance(block, ToolUseBlock):
                # Mark that we're waiting for a file tool result
                if block.name in ("Write", "Edit", "NotebookEdit"):
                    pending_file_tool = True
```

**To rewind:**
```python
await client.rewind_files("def-456")  # The tool result UUID, not the prompt UUID!
```

**Why this design makes sense (in hindsight):**
- Checkpoint captures state AFTER the file change
- The tool result message is the natural place for this—it represents the completion of the file operation
- Multiple tool calls in one turn? Each gets its own checkpoint

## Problem: Agent Bypasses Checkpointing with Bash/Python

**Observed behavior:** When the Write tool fails (e.g., truncates content), the agent cleverly works around it using Bash heredocs or Python file I/O. But this **breaks checkpointing silently** - user thinks they have a safety net but they don't.

**The issue:**
- Write tool truncated at a code block pattern
- Agent tried Edit (same problem)
- Agent fell back to `cat >> file << 'EOF'` and `python3` with `open(...).write()`
- Those changes are NOT tracked by checkpointing
- User loses safety net without knowing

**Possible solutions:**

1. **System prompt instruction** (simplest):
   ```
   IMPORTANT: Only use Write, Edit, and NotebookEdit for file modifications.
   Do NOT use Bash commands (echo, cat, python) to write files.
   If Write/Edit fails, report the error - do not work around it.
   File checkpointing only tracks Write/Edit/NotebookEdit operations.
   ```

2. **Remove Bash from allowed_tools entirely:**
   - Pro: Fully checkpoint-compliant
   - Con: Lose git, running builds, etc.

3. **Two modes - "safe" vs "full":**
   - Safe mode: No Bash (fully checkpoint-compliant)
   - Full mode: Bash allowed (user understands risk)

4. **Hook to intercept Bash file writes:**
   - Detect patterns like `echo >`, `cat >`, `python -c`
   - Warn or block

5. **Track and warn:**
   - Log which tools were used each turn
   - If Bash touched files, show warning: "⚠ Some changes may not be rewindable"

**TODO:** Decide on solution and implement before shipping. This is a real footgun.

**Quotes for blog post text box:**

> "I see the write is still truncating. Let me write the complete blog post in a different approach - splitting it into the first part and the rest"

> "Let me try a different approach - I'll use Python to write the file"

These quotes show Claude's problem-solving working against us - it cleverly works around Write tool limitations, but bypasses checkpointing in the process.

## Debugging Journey: "No file checkpoint found for message"

**The symptom:** Getting "No file checkpoint found for message" even after only tracking checkpoints for Write/Edit/NotebookEdit turns.

**What we tried (didn't help):**
- Only tracking checkpoints when file tools were used ✓
- Correctly capturing session_id ✓
- Adding proper error handling ✓

**The actual root cause:** We were capturing the UUID from the WRONG UserMessage!

Initially, we captured the UUID from the first UserMessage in the response stream—thinking it was the checkpoint. But that's just your prompt echoed back. The checkpoint is tied to the UserMessage containing the **tool result**, which comes AFTER the tool executes.

**The fix:** Track when we see a Write/Edit/NotebookEdit tool call, then capture the UUID from the NEXT UserMessage that appears:

```python
pending_file_tool = False

# When we see a file tool being called:
if block.name in ("Write", "Edit", "NotebookEdit"):
    pending_file_tool = True

# When we see the next UserMessage (the tool result):
if isinstance(msg, UserMessage) and msg.uuid and pending_file_tool:
    checkpoints.append(Checkpoint(uuid=msg.uuid, ...))
    pending_file_tool = False
```

**Lesson learned:** When debugging SDK integrations, trace the actual message flow carefully. The mental model we had (prompt → checkpoint → response) was subtly wrong (prompt → tool call → tool executes → checkpoint on result → response).

## Future Sub-agents (not for Blog 5, but planned)

- Fact-checking sub-agent
- Research sub-agent
- Style matcher/editor sub-agent

These are reusable, not blog-specific.
