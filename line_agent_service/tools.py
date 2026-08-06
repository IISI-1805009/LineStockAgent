import os
from pathlib import Path
from pydantic import BaseModel, Field

BASE_WORKSPACE = "/Users/hank/Project/LineStockAgent"

def _is_safe_path(target_path: str) -> bool:
    """Check if the target path is within the allowed base workspace."""
    try:
        # Resolve to absolute path, resolving symlinks and relative parts
        abs_path = os.path.abspath(target_path)
        return abs_path.startswith(os.path.abspath(BASE_WORKSPACE))
    except Exception:
        return False

# Pydantic models for function arguments

class ReadFileArgs(BaseModel):
    path: str = Field(description="The absolute or relative path to the file to read.")

class WriteFileArgs(BaseModel):
    path: str = Field(description="The absolute or relative path to the file to write.")
    content: str = Field(description="The content to write to the file.")

class ListDirArgs(BaseModel):
    path: str = Field(description="The absolute or relative path to the directory to list.")

# Tool functions

def read_file(path: str) -> str:
    """Read the contents of a file in the workspace."""
    if not os.path.isabs(path):
        path = os.path.join(BASE_WORKSPACE, path)
    if not _is_safe_path(path):
        return f"Error: Access denied. Path {path} is outside the allowed workspace."
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Error reading file: {e}"

def write_file(path: str, content: str) -> str:
    """Write content to a file in the workspace."""
    if not os.path.isabs(path):
        path = os.path.join(BASE_WORKSPACE, path)
    if not _is_safe_path(path):
        return f"Error: Access denied. Path {path} is outside the allowed workspace."
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Successfully wrote to {path}"
    except Exception as e:
        return f"Error writing file: {e}"

def list_dir(path: str) -> str:
    """List the contents of a directory in the workspace."""
    if not os.path.isabs(path):
        path = os.path.join(BASE_WORKSPACE, path)
    if not _is_safe_path(path):
        return f"Error: Access denied. Path {path} is outside the allowed workspace."
    try:
        items = os.listdir(path)
        if not items:
            return f"Directory {path} is empty."
        return "\n".join(items)
    except Exception as e:
        return f"Error listing directory: {e}"
