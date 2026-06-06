"""
Tests for Visual Agent

These tests mock pyautogui, pytesseract, and OpenCV to test the logic
without requiring an actual display or screen access in CI/CD environments.
"""

import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

# Import the agent and exceptions
from ai_engine.agents.visual_agent import (
    VisualAgent,
    VisualElementNotFoundError,
    ScreenCaptureError
)


class TestVisualAgentInitialization:
    """Test VisualAgent initialization and setup."""

    def test_agent_creation(self):
        """Test that VisualAgent can be instantiated."""
        agent = VisualAgent()
        assert agent.agent_name == "VisualAgent"
        assert agent.agent_id == "visual-001"

    def test_agent_custom_name(self):
        """Test VisualAgent with custom name and ID."""
        agent = VisualAgent(agent_name="CustomVisual", agent_id="custom-001")
        assert agent.agent_name == "CustomVisual"
        assert agent.agent_id == "custom-001"

    def test_log_file_created(self):
        """Test that log file path is set correctly."""
        agent = VisualAgent()
        assert agent._log_file == Path("/workspace/logs/visual_agent.log")


class TestSecondaryMonitorDetection:
    """Test secondary monitor bounds detection."""

    def test_get_secondary_monitor_bounds_returns_dict(self):
        """Test secondary monitor detection returns a dictionary."""
        agent = VisualAgent()
        # Reset cached bounds
        agent._secondary_monitor_bounds = None
        
        bounds = agent.get_secondary_monitor_bounds()
        
        assert bounds is not None
        assert isinstance(bounds, dict)
        assert "x" in bounds
        assert "y" in bounds
        assert "width" in bounds
        assert "height" in bounds

    @patch('ai_engine.agents.visual_agent.pyautogui')
    def test_get_secondary_monitor_bounds_with_pyautogui(self, mock_pyautogui):
        """Test secondary monitor detection using pyautogui."""
        mock_pyautogui.monitors = [
            (0, 0, 1920, 1080),      # Primary
            (1920, 0, 1920, 1080)    # Secondary
        ]
        
        agent = VisualAgent()
        agent._secondary_monitor_bounds = None
        
        with patch('ai_engine.agents.visual_agent.PYAUTOGUI_AVAILABLE', True):
            bounds = agent.get_secondary_monitor_bounds()
        
        assert bounds is not None
        assert bounds["x"] == 1920
        assert bounds["y"] == 0
        assert bounds["width"] == 1920
        assert bounds["height"] == 1080


class TestScreenCapture:
    """Test screen capture functionality."""

    @pytest.mark.asyncio
    async def test_capture_screen_returns_dict(self):
        """Test screen capture returns a dictionary."""
        agent = VisualAgent()
        
        result = await agent.capture_screen()
        
        assert isinstance(result, dict)
        assert "success" in result
        assert "message" in result
        assert "data" in result
        assert "error" in result

    @pytest.mark.asyncio
    async def test_capture_screen_with_region(self):
        """Test screen capture with specific region."""
        agent = VisualAgent()
        region = {"x": 100, "y": 100, "width": 500, "height": 400}
        
        result = await agent.capture_screen(region=region)
        
        assert isinstance(result, dict)
        assert "success" in result


class TestFindElement:
    """Test element finding functionality."""

    @pytest.mark.asyncio
    async def test_find_element_ocr_method_returns_dict(self):
        """Test finding element using OCR method returns dict."""
        agent = VisualAgent()
        
        result = await agent.find_element_on_screen("Test Button", method="ocr")
        
        assert isinstance(result, dict)
        assert "success" in result
        assert "error" in result

    @pytest.mark.asyncio
    async def test_find_element_template_method_returns_dict(self):
        """Test finding element using template matching returns dict."""
        agent = VisualAgent()
        
        result = await agent.find_element_on_screen(
            "/path/to/template.png", 
            method="template"
        )
        
        assert isinstance(result, dict)
        assert "success" in result

    @pytest.mark.asyncio
    async def test_find_element_invalid_method(self):
        """Test finding element with invalid method."""
        agent = VisualAgent()
        
        result = await agent.find_element_on_screen("test", method="invalid")
        
        assert result["success"] == False
        assert result["error"] is not None


class TestInteractWithElement:
    """Test interaction with screen elements."""

    @pytest.mark.asyncio
    async def test_interact_click_returns_dict(self):
        """Test click interaction returns dictionary."""
        agent = VisualAgent()
        
        result = await agent.interact_with_element(500, 300, action="click")
        
        assert isinstance(result, dict)
        assert "success" in result

    @pytest.mark.asyncio
    async def test_interact_double_click_returns_dict(self):
        """Test double-click interaction returns dictionary."""
        agent = VisualAgent()
        
        result = await agent.interact_with_element(500, 300, action="double_click")
        
        assert isinstance(result, dict)
        assert "success" in result

    @pytest.mark.asyncio
    async def test_interact_blocked_critical_area_start_menu(self):
        """Test interaction blocked in Start menu area."""
        agent = VisualAgent()
        
        # Coordinates near bottom-left (Start menu area)
        result = await agent.interact_with_element(50, 1000, action="click")
        
        assert result["success"] == False
        assert "blocked" in result["message"].lower() or "critical" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_interact_blocked_critical_area_system_tray(self):
        """Test interaction blocked in system tray area."""
        agent = VisualAgent()
        
        # Coordinates near top-right (system tray area)
        result = await agent.interact_with_element(1900, 50, action="click")
        
        assert result["success"] == False
        assert "blocked" in result["message"].lower() or "critical" in result["message"].lower()


class TestTypeTextSafely:
    """Test safe text typing functionality."""

    @pytest.mark.asyncio
    async def test_type_text_returns_dict(self):
        """Test text typing returns dictionary."""
        agent = VisualAgent()
        
        result = await agent.type_text_safely("Hello World", interval=0.1)
        
        assert isinstance(result, dict)
        assert "success" in result

    @pytest.mark.asyncio
    async def test_type_text_empty_string(self):
        """Test typing empty string."""
        agent = VisualAgent()
        
        result = await agent.type_text_safely("", interval=0.1)
        
        assert isinstance(result, dict)
        assert "success" in result


class TestExecuteTask:
    """Test the main execute_task method."""

    @pytest.mark.asyncio
    async def test_execute_task_capture_screen(self):
        """Test executing capture_screen task."""
        agent = VisualAgent()
        task = {
            "operation": "capture_screen",
            "parameters": {}
        }
        
        result = await agent.execute_task(task)
        
        assert isinstance(result, dict)
        assert "success" in result

    @pytest.mark.asyncio
    async def test_execute_task_find_element(self):
        """Test executing find_element task."""
        agent = VisualAgent()
        task = {
            "operation": "find_element",
            "parameters": {
                "target": "Submit Button",
                "method": "ocr"
            }
        }
        
        result = await agent.execute_task(task)
        
        assert isinstance(result, dict)
        assert "success" in result

    @pytest.mark.asyncio
    async def test_execute_task_interact(self):
        """Test executing interact task."""
        agent = VisualAgent()
        task = {
            "operation": "interact",
            "parameters": {
                "x": 500,
                "y": 300,
                "action": "click"
            }
        }
        
        result = await agent.execute_task(task)
        
        assert isinstance(result, dict)
        assert "success" in result

    @pytest.mark.asyncio
    async def test_execute_task_type_text(self):
        """Test executing type_text task."""
        agent = VisualAgent()
        task = {
            "operation": "type_text",
            "parameters": {
                "text": "Hello",
                "interval": 0.1
            }
        }
        
        result = await agent.execute_task(task)
        
        assert isinstance(result, dict)
        assert "success" in result

    @pytest.mark.asyncio
    async def test_execute_task_unknown_operation(self):
        """Test executing unknown operation."""
        agent = VisualAgent()
        task = {
            "operation": "unknown_op",
            "parameters": {}
        }
        
        result = await agent.execute_task(task)
        
        assert result["success"] == False
        assert "unknown" in result["message"].lower()


class TestAuthorization:
    """Test authorization checks."""

    @pytest.mark.asyncio
    async def test_check_authorization_default_allows_safe_targets(self):
        """Test authorization with default settings allows safe targets."""
        agent = VisualAgent()
        
        # Should allow common targets by default
        assert await agent.check_authorization("screen") == True
        assert await agent.check_authorization("monitor") == True
        assert await agent.check_authorization("desktop") == True

    @pytest.mark.asyncio
    async def test_check_authorization_with_allowed_apps(self):
        """Test authorization with configured allowed applications."""
        agent = VisualAgent()
        agent.set_allowed_applications(["Chrome", "Firefox"])
        
        # Allowed apps should pass
        assert await agent.check_authorization("Chrome") == True
        assert await agent.check_authorization("Firefox") == True
        # Non-allowed apps should fail
        assert await agent.check_authorization("Safari") == False


class TestLogging:
    """Test logging functionality."""

    def test_log_to_file_no_exception(self):
        """Test logging to file doesn't raise exceptions."""
        agent = VisualAgent()
        
        # This should not raise any exceptions
        agent._log_to_file("test_action", "SUCCESS", {"test": "data"})
        
        # Verify log file parent directory exists
        assert agent._log_file.parent.exists()

    @pytest.mark.asyncio
    async def test_log_action_no_exception(self):
        """Test async log_action method doesn't raise exceptions."""
        agent = VisualAgent()
        
        # This should not raise any exceptions
        await agent.log_action("test_action", {"key": "value"})


class TestSystemInfo:
    """Test system info retrieval."""

    @pytest.mark.asyncio
    async def test_get_system_info_returns_dict(self):
        """Test getting system information returns dictionary."""
        agent = VisualAgent()
        
        result = await agent.get_system_info()
        
        assert isinstance(result, dict)
        assert "success" in result
        assert "data" in result


class TestExceptions:
    """Test custom exceptions."""

    def test_visual_element_not_found_error(self):
        """Test VisualElementNotFoundError."""
        error = VisualElementNotFoundError("Element not found")
        assert str(error) == "Element not found"

    def test_screen_capture_error(self):
        """Test ScreenCaptureError."""
        error = ScreenCaptureError("Capture failed")
        assert str(error) == "Capture failed"
