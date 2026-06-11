"""
Tests for Path Validator Module

Tests the path validation functionality to prevent path traversal attacks.
"""

import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

# Import the module under test
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from ai_engine.core.security.path_validator import (
    validate_path,
    is_safe_path,
    sanitize_path,
    PathValidationError,
)


class TestValidatePath:
    """Tests for validate_path function."""
    
    def test_valid_path_within_workspace(self, tmp_path):
        """Test that valid paths within workspace are accepted."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        target_file = workspace / "file.txt"
        target_file.write_text("test")
        
        result = validate_path(workspace, target_file)
        assert result == target_file.resolve()
    
    def test_valid_subdirectory(self, tmp_path):
        """Test paths in subdirectories are accepted."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        subdir = workspace / "subdir"
        subdir.mkdir()
        target_file = subdir / "file.txt"
        target_file.write_text("test")
        
        result = validate_path(workspace, target_file)
        assert result == target_file.resolve()
    
    def test_path_traversal_with_dots(self, tmp_path):
        """Test that path traversal with .. is blocked."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        outside_file = tmp_path / "secret.txt"
        outside_file.write_text("secret")
        
        # Attempt path traversal
        target_path = workspace / ".." / "secret.txt"
        
        with pytest.raises(PermissionError) as exc_info:
            validate_path(workspace, target_path)
        
        assert "VIOLACIÓN DE PERÍMETRO" in str(exc_info.value)
        assert "Path Traversal detectado" in str(exc_info.value)
    
    def test_absolute_path_outside_workspace(self, tmp_path):
        """Test that absolute paths outside workspace are blocked."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        outside_file = tmp_path / "secret.txt"
        outside_file.write_text("secret")
        
        with pytest.raises(PermissionError) as exc_info:
            validate_path(workspace, outside_file)
        
        assert "VIOLACIÓN DE PERÍMETRO" in str(exc_info.value)
    
    def test_symlink_to_outside(self, tmp_path):
        """Test that symlinks pointing outside workspace are blocked."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        outside_file = tmp_path / "secret.txt"
        outside_file.write_text("secret")
        
        # Create symlink inside workspace pointing outside
        symlink = workspace / "link.txt"
        try:
            symlink.symlink_to(outside_file)
            
            # This should be blocked because resolved path is outside
            with pytest.raises(PermissionError):
                validate_path(workspace, symlink)
        except (OSError, NotImplementedError):
            # Symlinks not supported on this system, skip test
            pytest.skip("Symlinks not supported")
    
    def test_nonexistent_file_within_workspace(self, tmp_path):
        """Test that non-existent files within workspace are accepted."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        target_file = workspace / "new_file.txt"
        
        result = validate_path(workspace, target_file)
        # Should resolve to the expected path even if file doesn't exist
        assert str(result).startswith(str(workspace.resolve()))
    
    def test_windows_style_path(self, tmp_path):
        """Test Windows-style paths with backslashes."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        target_file = workspace / "file.txt"
        target_file.write_text("test")
        
        # Use string with backslashes (simulating Windows)
        result = validate_path(str(workspace), str(target_file).replace('/', '\\'))
        assert result == target_file.resolve()
    
    def test_string_paths(self, tmp_path):
        """Test that string paths work correctly."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        target_file = workspace / "file.txt"
        target_file.write_text("test")
        
        result = validate_path(str(workspace), str(target_file))
        assert result == target_file.resolve()
    
    def test_same_path(self, tmp_path):
        """Test that workspace path itself is valid."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        
        result = validate_path(workspace, workspace)
        assert result == workspace.resolve()


class TestIsSafePath:
    """Tests for is_safe_path function."""
    
    def test_safe_path_returns_true(self, tmp_path):
        """Test that safe paths return True."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        target_file = workspace / "file.txt"
        target_file.write_text("test")
        
        assert is_safe_path(workspace, target_file) is True
    
    def test_unsafe_path_returns_false(self, tmp_path):
        """Test that unsafe paths return False."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        outside_file = tmp_path / "secret.txt"
        outside_file.write_text("secret")
        
        assert is_safe_path(workspace, outside_file) is False
    
    def test_traversal_returns_false(self, tmp_path):
        """Test that path traversal returns False."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        target_path = workspace / ".." / "secret.txt"
        
        assert is_safe_path(workspace, target_path) is False


class TestSanitizePath:
    """Tests for sanitize_path function."""
    
    def test_removes_null_bytes(self):
        """Test that null bytes are removed."""
        malicious = "/workspace/file\x00.txt"
        result = sanitize_path(malicious)
        assert '\x00' not in result
        assert result == "/workspace/file.txt"
    
    def test_normalizes_backslashes(self):
        """Test that backslashes are normalized to forward slashes."""
        windows_path = "C:\\Users\\file.txt"
        result = sanitize_path(windows_path)
        assert '\\' not in result
        assert result == "C:/Users/file.txt"
    
    def test_strips_whitespace(self):
        """Test that leading/trailing whitespace is removed."""
        path = "  /workspace/file.txt  "
        result = sanitize_path(path)
        assert result == "/workspace/file.txt"
    
    def test_collapses_multiple_slashes(self):
        """Test that multiple slashes are collapsed."""
        path = "/workspace//subdir///file.txt"
        result = sanitize_path(path)
        assert "//" not in result
        assert result == "/workspace/subdir/file.txt"
    
    def test_path_object_input(self):
        """Test that Path objects are handled correctly."""
        path = Path("/workspace/file.txt")
        result = sanitize_path(path)
        assert isinstance(result, str)
        assert result == "/workspace/file.txt"


class TestPerformance:
    """Performance tests for path validation."""
    
    def test_validation_under_10ms(self, tmp_path):
        """Test that path validation completes in under 10ms."""
        import time
        
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        for i in range(10):
            subdir = workspace / f"subdir_{i}"
            subdir.mkdir()
            target_file = subdir / "file.txt"
            target_file.write_text("test")
        
        target = workspace / "subdir_5" / "file.txt"
        
        start = time.time()
        for _ in range(100):
            validate_path(workspace, target)
        elapsed = (time.time() - start) * 1000 / 100  # Average ms per call
        
        assert elapsed < 10, f"Validation took {elapsed}ms, expected < 10ms"


class TestEdgeCases:
    """Tests for edge cases and special scenarios."""
    
    def test_empty_workspace_path(self):
        """Test behavior with empty workspace path."""
        with pytest.raises((PathValidationError, PermissionError)):
            validate_path("", "/some/path")
    
    def test_relative_paths(self, tmp_path):
        """Test that relative paths are resolved correctly."""
        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            
            workspace = tmp_path / "workspace"
            workspace.mkdir()
            target_file = workspace / "file.txt"
            target_file.write_text("test")
            
            # Use relative path
            result = validate_path("workspace", "workspace/file.txt")
            assert result.is_absolute()
            assert result.exists()
        finally:
            os.chdir(original_cwd)
    
    def test_unicode_paths(self, tmp_path):
        """Test paths with unicode characters."""
        workspace = tmp_path / "workspace_ñoño"
        workspace.mkdir()
        target_file = workspace / "archivo_日本語.txt"
        target_file.write_text("test")
        
        result = validate_path(workspace, target_file)
        assert result == target_file.resolve()
    
    def test_very_long_paths(self, tmp_path):
        """Test handling of very long paths."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        
        # Create deep directory structure
        deep_path = workspace
        for i in range(50):
            deep_path = deep_path / f"level_{i}"
            deep_path.mkdir(exist_ok=True)
        
        target_file = deep_path / "file.txt"
        target_file.write_text("test")
        
        result = validate_path(workspace, target_file)
        assert result == target_file.resolve()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
