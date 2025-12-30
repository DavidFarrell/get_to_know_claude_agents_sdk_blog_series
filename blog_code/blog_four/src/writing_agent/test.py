from claude_agent_sdk import ToolUseBlock
import inspect

# Try to find source or show class info
print('Type:', type(ToolUseBlock))
print('MRO:', ToolUseBlock.__mro__)

# Check if it's a dataclass or has annotations
if hasattr(ToolUseBlock, '__annotations__'):
    print('Annotations:', ToolUseBlock.__annotations__)
if hasattr(ToolUseBlock, '__dataclass_fields__'):
    print('Dataclass fields:', list(ToolUseBlock.__dataclass_fields__.keys()))
if hasattr(ToolUseBlock, 'model_fields'):
    print('Pydantic fields:', list(ToolUseBlock.model_fields.keys()))
