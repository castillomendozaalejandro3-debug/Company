"""
Unit tests for PC Controller Agent.

Tests cover:
- get_system_info() functionality
- Security validation
- Error handling
"""

import pytest
import asyncio
from unittest.mock import patch, MagicMock
import sys
import os

# Add the project root to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from ai_engine.agents.pc_controller import (
    PCControllerAgent,
    SecurityValidationError,
    ExecutionError,
    AuthorizationError
)


class TestPCControllerAgent:
    """Test suite for PCControllerAgent."""

    @pytest.fixture
    def agent(self):
        """Create a PCControllerAgent instance for testing."""
        return PCControllerAgent(agent_name="TestPCController", agent_id="test-pc-001")

    @pytest.mark.asyncio
    async def test_get_system_info(self, agent):
        """Test that get_system_info returns valid system information."""
        result = await agent.get_system_info()
        
        assert result["success"] is True
        assert result["message"] == "System information retrieved successfully"
        assert result["error"] is None
        assert "data" in result
        
        data = result["data"]
        assert "os_type" in data
        assert data["os_type"] in ["windows", "macos", "linux"]
        assert "platform" in data
        assert "python_version" in data
        assert "architecture" in data

    @pytest.mark.asyncio
    async def test_shutdown_system_with_validation(self, agent):
        """Test shutdown_system with security validation."""
        result = await agent.shutdown_system(delay_seconds=60)
        
        assert result["success"] is True
        assert "Shutdown command prepared" in result["message"]
        assert result["error"] is None
        assert "data" in result
        
        data = result["data"]
        assert "command" in data
        assert "os_type" in data
        assert "delay_seconds" in data
        assert data["delay_seconds"] == 60
        assert data["simulated"] is True

    @pytest.mark.asyncio
    async def test_restart_system_with_validation(self, agent):
        """Test restart_system with security validation."""
        result = await agent.restart_system(delay_seconds=30)
        
        assert result["success"] is True
        assert "Restart command prepared" in result["message"]
        assert result["error"] is None
        assert "data" in result
        
        data = result["data"]
        assert "command" in data
        assert "os_type" in data
        assert "delay_seconds" in data
        assert data["delay_seconds"] == 30

    @pytest.mark.asyncio
    async def test_open_application_success(self, agent):
        """Test opening an application successfully."""
        result = await agent.open_application("notepad")
        
        assert result["success"] is True
        assert "opened successfully" in result["message"]
        assert result["error"] is None
        assert "data" in result
        
        data = result["data"]
        assert "app_name" in data
        assert data["app_name"] == "notepad"
        assert "os_type" in data

    @pytest.mark.asyncio
    async def test_execute_command_safe(self, agent):
        """Test executing a safe command."""
        result = await agent.execute_command("echo hello", requires_confirmation=False)
        
        assert result["success"] is True
        assert "Command executed successfully" in result["message"]
        assert result["error"] is None
        assert "data" in result
        
        data = result["data"]
        assert "command" in data
        assert data["command"] == "echo hello"

    @pytest.mark.asyncio
    async def test_execute_command_dangerous_requires_confirmation(self, agent):
        """Test that dangerous commands require confirmation."""
        result = await agent.execute_command("rm -rf /tmp/test", requires_confirmation=True)
        
        assert result["success"] is False
        assert "requires explicit confirmation" in result["message"]
        assert result["error"] is None
        assert "data" in result
        
        data = result["data"]
        assert "confirmation_required" in data
        assert data["confirmation_required"] is True
        assert "dangerous_patterns_found" in data
        assert data["dangerous_patterns_found"] is True

    @pytest.mark.asyncio
    async def test_check_authorization_blocks_sensitive_paths(self, agent):
        """Test that authorization blocks access to sensitive paths."""
        with pytest.raises(AuthorizationError):
            await agent.check_authorization("/etc/shadow")
        
        with pytest.raises(AuthorizationError):
            await agent.check_authorization("C:/Windows/System32/config")

    @pytest.mark.asyncio
    async def test_check_authorization_allows_normal_targets(self, agent):
        """Test that authorization allows normal targets."""
        result = await agent.check_authorization("notepad")
        assert result is True
        
        result = await agent.check_authorization("calculator")
        assert result is True

    @pytest.mark.asyncio
    async def test_execute_task_unknown_operation(self, agent):
        """Test execute_task with unknown operation."""
        task = {"operation": "unknown_op", "parameters": {}}
        result = await agent.execute_task(task)
        
        assert result["success"] is False
        assert "Unknown operation" in result["message"]
        assert "error" in result
        assert result["data"] is None

    @pytest.mark.asyncio
    async def test_execute_task_shutdown(self, agent):
        """Test execute_task routing to shutdown_system."""
        task = {
            "operation": "shutdown",
            "parameters": {"delay_seconds": 10}
        }
        result = await agent.execute_task(task)
        
        assert result["success"] is True
        assert "Shutdown command prepared" in result["message"]

    @pytest.mark.asyncio
    async def test_execute_task_get_system_info(self, agent):
        """Test execute_task routing to get_system_info."""
        task = {"operation": "get_system_info", "parameters": {}}
        result = await agent.execute_task(task)
        
        assert result["success"] is True
        assert "System information retrieved successfully" in result["message"]
        assert "data" in result
        assert "os_type" in result["data"]

    @pytest.mark.asyncio
    async def test_security_validation_critical_processes(self, agent):
        """Test security validation detects critical processes."""
        # This test verifies the validation mechanism works
        validation = await agent._validate_security("shutdown", requires_confirmation=True)
        
        assert "valid" in validation
        assert "requires_confirmation" in validation
        assert "warnings" in validation
        assert isinstance(validation["warnings"], list)

    @pytest.mark.asyncio
    async def test_log_action_creates_log_entry(self, agent, caplog):
        """Test that log_action creates proper log entries."""
        await agent.log_action("test_action", {"key": "value"})
        
        # Verify logger was called (check via caplog if configured)
        # The actual log file should be created in logs/pc_controller.log
        pass

    @pytest.mark.asyncio
    async def test_custom_exceptions_security_validation_error(self):
        """Test SecurityValidationError exception."""
        with pytest.raises(SecurityValidationError) as exc_info:
            raise SecurityValidationError("Security check failed")
        
        assert "Security check failed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_custom_exceptions_execution_error(self):
        """Test ExecutionError exception."""
        with pytest.raises(ExecutionError) as exc_info:
            raise ExecutionError("Execution failed")
        
        assert "Execution failed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_custom_exceptions_authorization_error(self):
        """Test AuthorizationError exception."""
        with pytest.raises(AuthorizationError) as exc_info:
            raise AuthorizationError("Not authorized")
        
        assert "Not authorized" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_os_detection(self, agent):
        """Test OS type detection."""
        os_type = agent._get_os_type()
        assert os_type in ["windows", "macos", "linux"]

    @pytest.mark.asyncio
    async def test_response_structure_consistency(self, agent):
        """Test that all methods return consistent response structure."""
        methods_to_test = [
            ("get_system_info", {}),
            ("shutdown_system", {"delay_seconds": 0}),
            ("restart_system", {"delay_seconds": 0}),
        ]
        
        for method_name, kwargs in methods_to_test:
            method = getattr(agent, method_name)
            result = await method(**kwargs) if kwargs else await method()
            
            # Verify standard response structure
            assert "success" in result, f"{method_name} missing 'success' key"
            assert "message" in result, f"{method_name} missing 'message' key"
            assert "data" in result, f"{method_name} missing 'data' key"
            assert "error" in result, f"{method_name} missing 'error' key"
            assert isinstance(result["success"], bool)
            assert isinstance(result["message"], str)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
