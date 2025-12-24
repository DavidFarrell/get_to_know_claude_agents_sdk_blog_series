# Writing Agent - Blog One

A minimal Claude-powered writing assistant built with the Claude Agent SDK.

## Prerequisites

- Python 3.10+
- Claude Code installed and authenticated (the SDK will use your existing Claude Code credentials)

To check if Claude Code is installed:
```bash
claude --version
```

If not installed, see: https://docs.anthropic.com/en/docs/claude-code/getting-started

## Setup

1. **Navigate to this folder**
   ```bash
   cd blog_code/blog_one
   ```

2. **Create a virtual environment**
   ```bash
   python3 -m venv .venv
   ```

3. **Activate the virtual environment**
   ```bash
   # On macOS/Linux:
   source .venv/bin/activate

   # On Windows:
   .venv\Scripts\activate
   ```

4. **Install dependencies**
   ```bash
   pip install -e .
   ```

## Running the Agent

Once installed, you can run it two ways:

**Option A: As a module**
```bash
python -m writing_agent.main /path/to/your/blog
```

**Option B: As a command (after pip install)**
```bash
writing-agent /path/to/your/blog
```

If you omit the path, it uses the current directory.

## Usage

Once running, you'll see a prompt:
```
Writing Agent starting...
Working directory: /path/to/your/blog
Type 'quit' or 'exit' to stop, 'clear' to reset conversation

You:
```

Try commands like:
- `What files are in this folder?`
- `Read the README`
- `Find all markdown files`
- `What's the git status?`

Type `quit` or `exit` to stop, or press Ctrl+C.

## What This Agent Can Do

It has access to these tools:
- **Read** - Read files
- **Write** - Create/overwrite files
- **Edit** - Modify existing files
- **Bash** - Run shell commands
- **Glob** - Find files by pattern
- **Grep** - Search file contents

## Learn More

This code accompanies the blog post: [Exploring the Claude Agent SDK](#)
