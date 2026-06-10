"""
Path Validator Module for Helios Security

Provides secure path validation to prevent path traversal attacks.
All paths are validated to ensure they remain within the workspace perimeter.
"""

import os
from pathlib import Path
from typing import Optional, Union


class PathValidationError(Exception):
    """Exception raised when path validation fails."""
    pass


def validate_path(workspace_path: Union[str, Path], target_path: Union[str, Path]) -> Path:
    """
    Validate that target_path is safely contained within workspace_path.
    
    This function prevents path traversal attacks by:
    1. Resolving both paths to absolute paths (resolving symlinks)
    2. Verifying target_path is a child of workspace_path using .parents
    3. Handling Windows and Unix path separators correctly
    
    Args:
        workspace_path: The base/allowed directory (workspace root)
        target_path: The target path to validate
        
    Returns:
        Path: The resolved target_path if validation passes
        
    Raises:
        PermissionError: If target_path is outside workspace_path
        PathValidationError: If paths are invalid or cannot be resolved
        
    Examples:
        >>> validate_path("/workspace", "/workspace/file.txt")
        PosixPath('/workspace/file.txt')
        
        >>> validate_path("/workspace", "/workspace/../etc/passwd")
        PermissionError: VIOLACIÓN DE PERÍMETRO: Path Traversal detectado
    """
    try:
        # Convert to Path objects if strings
        workspace = Path(workspace_path)
        target = Path(target_path)
        
        # Resolve to absolute paths (resolve symlinks and normalize)
        # For workspace, we resolve first then check if it exists
        # For target, we need to handle non-existent files too
        try:
            workspace_resolved = workspace.resolve(strict=True)
        except (FileNotFoundError, RuntimeError):
            # If workspace doesn't exist, try to resolve without strict mode
            workspace_resolved = workspace.absolute()
        
        # For target path, handle both existing and non-existing files
        if target.exists():
            target_resolved = target.resolve(strict=True)
        else:
            # For non-existent files, resolve parent and reconstruct
            try:
                target_resolved = target.resolve(strict=False)
            except (FileNotFoundError, RuntimeError):
                # Fallback: manual resolution
                target_resolved = target.absolute()
        
        # Normalize path separators for cross-platform compatibility
        workspace_str = str(workspace_resolved).replace('\\', '/')
        target_str = str(target_resolved).replace('\\', '/')
        
        # Ensure workspace ends without separator for consistent comparison
        workspace_str = workspace_str.rstrip('/')
        
        # Check if target is within workspace using parents tuple
        # This is more secure than string comparison alone
        target_parents = [str(p).replace('\\', '/') for p in target_resolved.parents]
        
        # Direct match or parent match
        is_within = (
            target_str == workspace_str or 
            target_str.startswith(workspace_str + '/') or
            workspace_str in target_parents
        )
        
        # Additional check: ensure no '..' components remain after resolution
        # This catches edge cases where path traversal might slip through
        if '..' in target_resolved.parts:
            raise PermissionError("VIOLACIÓN DE PERÍMETRO: Path Traversal detectado")
        
        if not is_within:
            raise PermissionError("VIOLACIÓN DE PERÍMETRO: Path Traversal detectado")
        
        return target_resolved
        
    except PermissionError:
        # Re-raise permission errors as-is
        raise
    except Exception as e:
        # Wrap other exceptions in PathValidationError
        raise PathValidationError(f"Error validating path: {str(e)}")


def is_safe_path(workspace_path: Union[str, Path], target_path: Union[str, Path]) -> bool:
    """
    Check if target_path is safely contained within workspace_path.
    
    Non-raising version of validate_path. Returns False instead of raising.
    
    Args:
        workspace_path: The base/allowed directory (workspace root)
        target_path: The target path to validate
        
    Returns:
        bool: True if target_path is within workspace_path, False otherwise
    """
    try:
        validate_path(workspace_path, target_path)
        return True
    except (PermissionError, PathValidationError):
        return False


def sanitize_path(path: Union[str, Path]) -> str:
    """
    Sanitize a path by removing potentially dangerous characters.
    
    This function:
    - Removes null bytes
    - Normalizes path separators
    - Removes leading/trailing whitespace
    
    Args:
        path: The path to sanitize
        
    Returns:
        str: Sanitized path string
    """
    if isinstance(path, Path):
        path = str(path)
    
    # Remove null bytes (common injection vector)
    sanitized = path.replace('\x00', '')
    
    # Normalize separators (convert backslash to forward slash for consistency)
    sanitized = sanitized.replace('\\', '/')
    
    # Remove leading/trailing whitespace
    sanitized = sanitized.strip()
    
    # Collapse multiple slashes
    while '//' in sanitized:
        sanitized = sanitized.replace('//', '/')
    
    return sanitized
