"""
Visual Agent for Helios Multi-Agent System

This agent handles visual control, OCR, and screen-based interactions,
particularly optimized for secondary monitor operations.
"""

import asyncio
from typing import Dict, Any, List, Optional, Tuple

from .base_agent import BaseAgent


class VisualAgent(BaseAgent):
    """
    Visual Agent for screen control and OCR operations.
    
    This agent is responsible for:
    - Screen capture and analysis
    - Optical Character Recognition (OCR)
    - GUI element detection and interaction
    - Secondary monitor management
    - Visual workflow automation
    
    All operations are logged for audit purposes.
    """

    def __init__(self, agent_name: str = "VisualAgent", agent_id: str = "visual-001"):
        """
        Initialize the Visual Agent.
        
        Args:
            agent_name: Name of the agent
            agent_id: Unique identifier for the agent
        """
        super().__init__(agent_name, agent_id)
        self._monitors: List[Dict[str, Any]] = []
        self._ocr_engine: Optional[Any] = None
        self._screen_capture_region: Optional[Tuple[int, int, int, int]] = None
        self._allowed_applications: set = set()

    def set_allowed_applications(self, apps: List[str]) -> None:
        """Set list of applications that can be controlled visually."""
        self._allowed_applications = set(apps)

    def set_capture_region(self, x: int, y: int, width: int, height: int) -> None:
        """Set the screen region for capture operations."""
        self._screen_capture_region = (x, y, width, height)

    async def execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a visual control task.
        
        Args:
            task: Dictionary containing task parameters
            
        Returns:
            Dictionary containing execution results
        """
        await self.log_action("task_received", {"task": task})
        
        operation = task.get("operation", "").lower()
        target = task.get("target", "")
        parameters = task.get("parameters", {})
        
        try:
            if operation == "capture_screen":
                result = await self._capture_screen(**parameters)
            elif operation == "ocr":
                result = await self._perform_ocr(target, **parameters)
            elif operation == "find_element":
                result = await self._find_element(target, **parameters)
            elif operation == "click":
                result = await self._click(target, **parameters)
            elif operation == "type_text":
                result = await self._type_text(target, **parameters)
            elif operation == "detect_monitor":
                result = await self._detect_monitors()
            elif operation == "move_to_monitor":
                result = await self._move_to_monitor(target, **parameters)
            else:
                result = {
                    "status": "unknown_operation",
                    "error": f"Unknown visual operation: {operation}"
                }
            
            await self.log_action("task_completed", {"operation": operation, "result_status": result.get("status")})
            return result
            
        except Exception as e:
            await self.log_action("task_error", {"operation": operation, "error": str(e)})
            return {
                "status": "error",
                "error": str(e),
                "operation": operation
            }

    async def check_authorization(self, target: str) -> bool:
        """
        Check if the agent is authorized to perform visual operations on a target.
        
        Args:
            target: The target application or screen region
            
        Returns:
            True if authorized, False otherwise
        """
        # If allowed applications are configured, check against them
        if self._allowed_applications and target not in self._allowed_applications:
            return False
        
        # Default: allow common operations
        safe_targets = ["screen", "monitor", "desktop", "clipboard"]
        return target.lower() in safe_targets or not self._allowed_applications

    async def log_action(self, action: str, context: Dict[str, Any]) -> None:
        """
        Log an action performed by the agent.
        
        Args:
            action: Description of the action
            context: Additional context information
        """
        log_entry = {
            "timestamp": asyncio.get_event_loop().time(),
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "action": action,
            "context": context
        }
        print(f"[LOG] {self.agent_name}: {action} - {context}")

    async def _capture_screen(self, monitor_index: int = 0, region: Optional[List[int]] = None, 
                              save_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Capture a screenshot of the specified monitor or region.
        
        Args:
            monitor_index: Index of the monitor to capture (0 for primary)
            region: Optional [x, y, width, height] region to capture
            save_path: Optional path to save the screenshot
            
        Returns:
            Dictionary containing capture results
        """
        await self.log_action("capture_screen", {
            "monitor_index": monitor_index,
            "region": region,
            "save_path": save_path
        })
        
        # Simulated screen capture
        # In production, this would use libraries like pyautogui, mss, or PIL
        capture_result = {
            "status": "simulated",
            "message": "Screen capture prepared (simulated for safety)",
            "monitor_index": monitor_index,
            "resolution": "1920x1080",
            "format": "PNG",
            "region": region or self._screen_capture_region,
            "file_size_estimate": "2.5 MB"
        }
        
        if save_path:
            capture_result["save_path"] = save_path
        
        return capture_result

    async def _perform_ocr(self, image_source: str, language: str = "eng", 
                           **kwargs) -> Dict[str, Any]:
        """
        Perform OCR on an image or screen region.
        
        Args:
            image_source: Path to image file or 'screen' for current screen
            language: OCR language code (default: English)
            
        Returns:
            Dictionary containing OCR results
        """
        await self.log_action("perform_ocr", {
            "image_source": image_source,
            "language": language
        })
        
        # Simulated OCR results
        # In production, this would use Tesseract, Google Vision API, or Azure OCR
        ocr_result = {
            "status": "simulated",
            "message": "OCR processing completed (simulated)",
            "source": image_source,
            "language": language,
            "text": "Simulated OCR output text. In production, this would contain the actual recognized text from the image.",
            "confidence": 0.95,
            "words_detected": 18,
            "processing_time_ms": 245
        }
        
        return ocr_result

    async def _find_element(self, target: str, template_path: Optional[str] = None,
                            confidence: float = 0.9, **kwargs) -> Dict[str, Any]:
        """
        Find a UI element on screen by template matching or description.
        
        Args:
            target: Description of the element to find
            template_path: Optional path to template image
            confidence: Matching confidence threshold (0-1)
            
        Returns:
            Dictionary containing element location and metadata
        """
        await self.log_action("find_element", {
            "target": target,
            "template_path": template_path,
            "confidence": confidence
        })
        
        # Simulated element detection
        find_result = {
            "status": "simulated",
            "found": True,
            "location": {
                "x": 450,
                "y": 320,
                "width": 120,
                "height": 40
            },
            "confidence": 0.97,
            "element_type": "button",
            "description": target
        }
        
        return find_result

    async def _click(self, target: str, button: str = "left", 
                     double: bool = False, **kwargs) -> Dict[str, Any]:
        """
        Click on a screen element or coordinates.
        
        Args:
            target: Element description or coordinates [x, y]
            button: Mouse button ('left', 'right', 'middle')
            double: Whether to perform a double-click
            
        Returns:
            Dictionary containing click results
        """
        await self.log_action("click", {
            "target": target,
            "button": button,
            "double": double
        })
        
        # Simulated click
        click_result = {
            "status": "simulated",
            "message": "Click action prepared (simulated for safety)",
            "target": target,
            "button": button,
            "double_click": double,
            "coordinates": {"x": 450, "y": 320}
        }
        
        return click_result

    async def _type_text(self, target: str, text: str, delay: float = 0.05,
                         **kwargs) -> Dict[str, Any]:
        """
        Type text into a target field or at current cursor position.
        
        Args:
            target: Target field description or coordinates
            text: Text to type
            delay: Delay between keystrokes in seconds
            
        Returns:
            Dictionary containing typing results
        """
        await self.log_action("type_text", {
            "target": target,
            "text_length": len(text),
            "delay": delay
        })
        
        # Simulated typing
        type_result = {
            "status": "simulated",
            "message": "Text input prepared (simulated for safety)",
            "target": target,
            "characters": len(text),
            "estimated_duration_ms": len(text) * delay * 1000
        }
        
        return type_result

    async def _detect_monitors(self) -> Dict[str, Any]:
        """
        Detect all connected monitors and their properties.
        
        Returns:
            Dictionary containing monitor information
        """
        await self.log_action("detect_monitors", {})
        
        # Simulated monitor detection
        # In production, this would use screeninfo or similar libraries
        monitor_info = {
            "status": "simulated",
            "message": "Monitor detection completed (simulated)",
            "total_monitors": 2,
            "monitors": [
                {
                    "index": 0,
                    "name": "Primary Monitor",
                    "resolution": "1920x1080",
                    "position": {"x": 0, "y": 0},
                    "is_primary": True
                },
                {
                    "index": 1,
                    "name": "Secondary Monitor",
                    "resolution": "1920x1080",
                    "position": {"x": 1920, "y": 0},
                    "is_primary": False
                }
            ]
        }
        
        self._monitors = monitor_info["monitors"]
        return monitor_info

    async def _move_to_monitor(self, monitor_index: int, **kwargs) -> Dict[str, Any]:
        """
        Move focus or window to a specific monitor.
        
        Args:
            monitor_index: Index of the target monitor
            
        Returns:
            Dictionary containing move results
        """
        await self.log_action("move_to_monitor", {"monitor_index": monitor_index})
        
        if monitor_index >= len(self._monitors):
            return {
                "status": "error",
                "error": f"Monitor index {monitor_index} not found"
            }
        
        move_result = {
            "status": "simulated",
            "message": "Move to monitor prepared (simulated for safety)",
            "monitor_index": monitor_index,
            "monitor_info": self._monitors[monitor_index] if monitor_index < len(self._monitors) else None
        }
        
        return move_result

    async def get_screen_info(self) -> Dict[str, Any]:
        """Get current screen configuration information."""
        return await self._detect_monitors()

    async def wait_for_element(self, target: str, timeout: int = 30,
                               check_interval: float = 1.0) -> Dict[str, Any]:
        """
        Wait for an element to appear on screen.
        
        Args:
            target: Element description to wait for
            timeout: Maximum time to wait in seconds
            check_interval: Time between checks in seconds
            
        Returns:
            Dictionary containing wait results
        """
        await self.log_action("wait_for_element", {
            "target": target,
            "timeout": timeout
        })
        
        # Simulated wait
        wait_result = {
            "status": "simulated",
            "found": True,
            "waited_seconds": 2.5,
            "target": target
        }
        
        return wait_result
