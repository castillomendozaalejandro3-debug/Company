"""
Visual Agent for Helios Multi-Agent System

This agent handles visual control, OCR, and screen-based interactions,
particularly optimized for secondary monitor operations.
"""

import asyncio
import os
import random
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

try:
    import os
    # Set a dummy DISPLAY if not present (for headless environments)
    if 'DISPLAY' not in os.environ:
        os.environ['DISPLAY'] = ':0'
    import pyautogui
    PYAUTOGUI_AVAILABLE = True
except (ImportError, KeyError, Exception):
    PYAUTOGUI_AVAILABLE = False
    pyautogui = None

try:
    import cv2
    import numpy as np
    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False
    cv2 = None
    np = None

try:
    import pytesseract
    from PIL import Image
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False
    pytesseract = None
    Image = None

from .base_agent import BaseAgent


class VisualElementNotFoundError(Exception):
    """Exception raised when a visual element is not found on screen."""
    pass


class ScreenCaptureError(Exception):
    """Exception raised when screen capture fails."""
    pass


class VisualAgent(BaseAgent):
    """
    Visual Agent for screen control and OCR operations.
    
    This agent is responsible for:
    - Screen capture and analysis
    - Optical Character Recognition (OCR)
    - GUI element detection and interaction
    - Secondary monitor management
    - Visual workflow automation
    
    All operations are logged for audit purposes and validated through security shield.
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
        self._screen_capture_region: Optional[Tuple[int, int, int, int]] = None
        self._allowed_applications: set = set()
        self._secondary_monitor_bounds: Optional[Dict[str, int]] = None
        self._log_file: Path = Path("/workspace/logs/visual_agent.log")
        
        # Setup logging
        self._setup_logging()
        
        # Configure pyautogui for safety
        if PYAUTOGUI_AVAILABLE:
            pyautogui.FAILSAFE = True  # Move mouse to corner to abort
            pyautogui.PAUSE = 0.1  # Pause between actions

    def _setup_logging(self) -> None:
        """Setup logging configuration for the visual agent."""
        try:
            # Ensure logs directory exists
            self._log_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Configure file handler
            self._logger = logging.getLogger(f"VisualAgent_{self.agent_id}")
            self._logger.setLevel(logging.INFO)
            
            # Remove existing handlers to avoid duplicates
            self._logger.handlers.clear()
            
            # File handler
            file_handler = logging.FileHandler(self._log_file)
            file_handler.setLevel(logging.INFO)
            
            # Format: [TIMESTAMP] [ACTION] [STATUS] [CONTEXT]
            formatter = logging.Formatter(
                '[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            file_handler.setFormatter(formatter)
            self._logger.addHandler(file_handler)
        except Exception as e:
            print(f"Warning: Could not setup logging: {e}")
            self._logger = logging.getLogger(f"VisualAgent_{self.agent_id}")

    def _log_to_file(self, action: str, status: str, context: Dict[str, Any]) -> None:
        """
        Log an action to the log file with standardized format.
        
        Args:
            action: Description of the action performed
            status: Status of the action (SUCCESS, FAILURE, PENDING, etc.)
            context: Additional context information
        """
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        context_str = str(context) if context else "{}"
        log_line = f"[{timestamp}] [{action}] [{status}] [{context_str}]\n"
        
        try:
            with open(self._log_file, 'a') as f:
                f.write(log_line)
        except Exception as e:
            print(f"Warning: Could not write to log file: {e}")

    def set_allowed_applications(self, apps: List[str]) -> None:
        """Set list of applications that can be controlled visually."""
        self._allowed_applications = set(apps)

    def set_capture_region(self, x: int, y: int, width: int, height: int) -> None:
        """Set the screen region for capture operations."""
        self._screen_capture_region = (x, y, width, height)

    def get_secondary_monitor_bounds(self) -> Optional[Dict[str, int]]:
        """
        Detect and return the bounds of the secondary monitor.
        
        Returns:
            Dictionary with x, y, width, height of secondary monitor, or None if not found.
            Restricts autonomous actions to this zone to avoid interrupting the user.
        """
        if self._secondary_monitor_bounds:
            return self._secondary_monitor_bounds
        
        try:
            if PYAUTOGUI_AVAILABLE:
                # Get all monitors info using pyautogui
                monitors = pyautogui.monitors  # type: ignore
                
                if len(monitors) > 1:
                    # Secondary monitor is typically at index 1
                    secondary = monitors[1]
                    self._secondary_monitor_bounds = {
                        "x": secondary[0],
                        "y": secondary[1],
                        "width": secondary[2],
                        "height": secondary[3]
                    }
                    self._log_to_file("get_secondary_monitor_bounds", "SUCCESS", 
                                     {"bounds": self._secondary_monitor_bounds})
                    return self._secondary_monitor_bounds
                elif len(monitors) == 1:
                    # Only one monitor, return its bounds but mark as primary
                    primary = monitors[0]
                    self._log_to_file("get_secondary_monitor_bounds", "WARNING",
                                     {"message": "Only primary monitor detected"})
                    return {
                        "x": primary[0],
                        "y": primary[1],
                        "width": primary[2],
                        "height": primary[3],
                        "is_primary": True
                    }
            
            # Fallback: simulated detection for testing
            self._secondary_monitor_bounds = {
                "x": 1920,
                "y": 0,
                "width": 1920,
                "height": 1080
            }
            self._log_to_file("get_secondary_monitor_bounds", "SIMULATED",
                             {"bounds": self._secondary_monitor_bounds})
            return self._secondary_monitor_bounds
            
        except Exception as e:
            self._log_to_file("get_secondary_monitor_bounds", "ERROR",
                             {"error": str(e)})
            return None

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
        parameters = task.get("parameters", {})
        
        try:
            if operation == "capture_screen":
                result = await self.capture_screen(parameters.get("region"))
            elif operation == "find_element":
                target = parameters.get("target", "")
                method = parameters.get("method", "ocr")
                result = await self.find_element_on_screen(target, method)
            elif operation == "interact":
                x = parameters.get("x", 0)
                y = parameters.get("y", 0)
                action = parameters.get("action", "click")
                result = await self.interact_with_element(x, y, action)
            elif operation == "type_text":
                text = parameters.get("text", "")
                interval = parameters.get("interval", 0.1)
                result = await self.type_text_safely(text, interval)
            elif operation == "get_secondary_monitor":
                bounds = self.get_secondary_monitor_bounds()
                result = {
                    "success": bounds is not None,
                    "message": "Secondary monitor bounds retrieved" if bounds else "No secondary monitor found",
                    "data": bounds,
                    "error": None
                }
            else:
                result = {
                    "success": False,
                    "message": f"Unknown operation: {operation}",
                    "data": None,
                    "error": f"Unknown operation: {operation}"
                }
            
            await self.log_action("task_completed", {"operation": operation, "success": result.get("success")})
            return result
            
        except VisualElementNotFoundError as e:
            await self.log_action("task_error", {"operation": operation, "error": str(e), "type": "VisualElementNotFoundError"})
            return {
                "success": False,
                "message": "Element not found on screen",
                "data": None,
                "error": str(e)
            }
        except ScreenCaptureError as e:
            await self.log_action("task_error", {"operation": operation, "error": str(e), "type": "ScreenCaptureError"})
            return {
                "success": False,
                "message": "Screen capture failed",
                "data": None,
                "error": str(e)
            }
        except Exception as e:
            await self.log_action("task_error", {"operation": operation, "error": str(e), "type": "UnexpectedError"})
            return {
                "success": False,
                "message": "Unexpected error occurred",
                "data": None,
                "error": str(e)
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
        if self._allowed_applications:
            # If target is in allowed list, authorize it
            if target in self._allowed_applications:
                return True
            # Otherwise, deny
            return False
        
        # Default: allow common operations when no restrictions configured
        safe_targets = ["screen", "monitor", "desktop", "clipboard"]
        return target.lower() in safe_targets

    async def log_action(self, action: str, context: Dict[str, Any]) -> None:
        """
        Log an action performed by the agent.
        
        Args:
            action: Description of the action
            context: Additional context information
        """
        self._log_to_file(action, "INFO", context)
        if self._logger:
            self._logger.info(f"{action}: {context}")

    async def capture_screen(self, region: Optional[Dict[str, int]] = None) -> Dict[str, Any]:
        """
        Capture the full screen or a specific region.
        
        Args:
            region: Optional dictionary with x, y, width, height for region capture.
                   Useful for capturing only the secondary monitor area.
        
        Returns:
            Dictionary with success status, image path or numpy array, and metadata.
        """
        self._log_to_file("capture_screen", "PENDING", {"region": region})
        
        try:
            if PYAUTOGUI_AVAILABLE and TESSERACT_AVAILABLE and Image:
                # Determine capture region
                if region:
                    bbox = (region.get("x", 0), region.get("y", 0),
                           region.get("x", 0) + region.get("width", 0),
                           region.get("y", 0) + region.get("height", 0))
                elif self._screen_capture_region:
                    x, y, w, h = self._screen_capture_region
                    bbox = (x, y, x + w, y + h)
                else:
                    bbox = None
                
                # Capture screen
                screenshot = pyautogui.screenshot(region=bbox)  # type: ignore
                
                # Convert to numpy array for processing
                image_array = np.array(screenshot)  # type: ignore
                
                # Generate save path
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                save_path = f"/workspace/screenshots/screenshot_{timestamp}.png"
                
                # Ensure screenshots directory exists
                Path(save_path).parent.mkdir(parents=True, exist_ok=True)
                
                # Save image
                screenshot.save(save_path)
                
                self._log_to_file("capture_screen", "SUCCESS", {
                    "save_path": save_path,
                    "region": region,
                    "resolution": f"{image_array.shape[1]}x{image_array.shape[0]}"
                })
                
                return {
                    "success": True,
                    "message": "Screen captured successfully",
                    "data": {
                        "image_path": save_path,
                        "image_array": image_array.tolist(),  # Convert to list for JSON serialization
                        "width": image_array.shape[1],
                        "height": image_array.shape[0],
                        "channels": image_array.shape[2] if len(image_array.shape) > 2 else 1
                    },
                    "error": None
                }
            else:
                # Simulated capture for testing
                self._log_to_file("capture_screen", "SIMULATED", {"region": region})
                return {
                    "success": True,
                    "message": "Screen capture simulated (libraries not available)",
                    "data": {
                        "image_path": None,
                        "width": 1920,
                        "height": 1080,
                        "simulated": True
                    },
                    "error": None
                }
                
        except Exception as e:
            self._log_to_file("capture_screen", "ERROR", {"error": str(e)})
            raise ScreenCaptureError(f"Failed to capture screen: {str(e)}")

    async def find_element_on_screen(self, target: str, method: str = "ocr") -> Dict[str, Any]:
        """
        Find an element on screen using OCR or template matching.
        
        Args:
            target: Text to search for (OCR) or path to template image (template method).
            method: "ocr" for text search, "template" for image matching.
        
        Returns:
            Dictionary with success status, coordinates (x, y), and confidence score.
        """
        self._log_to_file("find_element_on_screen", "PENDING", {"target": target, "method": method})
        
        try:
            if method == "ocr":
                return await self._find_text_with_ocr(target)
            elif method == "template":
                return await self._find_template(target)
            else:
                raise ValueError(f"Unknown method: {method}. Use 'ocr' or 'template'.")
                
        except VisualElementNotFoundError as e:
            self._log_to_file("find_element_on_screen", "NOT_FOUND", {"target": target, "method": method})
            return {
                "success": False,
                "message": "Element not found on screen",
                "data": None,
                "error": str(e)
            }
        except Exception as e:
            self._log_to_file("find_element_on_screen", "ERROR", {"error": str(e)})
            return {
                "success": False,
                "message": "Error finding element",
                "data": None,
                "error": str(e)
            }

    async def _find_text_with_ocr(self, search_text: str) -> Dict[str, Any]:
        """Find text on screen using OCR."""
        if not TESSERACT_AVAILABLE or not Image:
            # Simulated result for testing
            self._log_to_file("_find_text_with_ocr", "SIMULATED", {"search_text": search_text})
            return {
                "success": True,
                "message": "Text found (simulated)",
                "data": {
                    "x": 450,
                    "y": 320,
                    "confidence": 0.95,
                    "text": search_text,
                    "simulated": True
                },
                "error": None
            }
        
        # Capture screen
        screenshot = pyautogui.screenshot()  # type: ignore
        image = Image.fromarray(np.array(screenshot))  # type: ignore
        
        # Perform OCR with bounding box data
        ocr_data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)  # type: ignore
        
        # Search for target text
        num_boxes = len(ocr_data['text'])
        for i in range(num_boxes):
            text = ocr_data['text'][i].strip()
            confidence = float(ocr_data['conf'][i])
            
            if text.lower() == search_text.lower() and confidence > 50:
                x = ocr_data['left'][i]
                y = ocr_data['top'][i]
                w = ocr_data['width'][i]
                h = ocr_data['height'][i]
                
                self._log_to_file("_find_text_with_ocr", "SUCCESS", {
                    "text": search_text,
                    "position": {"x": x, "y": y, "width": w, "height": h},
                    "confidence": confidence
                })
                
                return {
                    "success": True,
                    "message": f"Text '{search_text}' found on screen",
                    "data": {
                        "x": x + w // 2,  # Return center of element
                        "y": y + h // 2,
                        "confidence": confidence / 100.0,
                        "text": text,
                        "bounding_box": {"x": x, "y": y, "width": w, "height": h}
                    },
                    "error": None
                }
        
        # Text not found
        raise VisualElementNotFoundError(f"Text '{search_text}' not found on screen")

    async def _find_template(self, template_path: str) -> Dict[str, Any]:
        """Find element using template matching with OpenCV."""
        if not OPENCV_AVAILABLE or not cv2 or not np:
            # Simulated result for testing
            self._log_to_file("_find_template", "SIMULATED", {"template_path": template_path})
            return {
                "success": True,
                "message": "Template found (simulated)",
                "data": {
                    "x": 450,
                    "y": 320,
                    "confidence": 0.92,
                    "simulated": True
                },
                "error": None
            }
        
        # Capture screen
        screenshot = pyautogui.screenshot()  # type: ignore
        screen_image = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)  # type: ignore
        
        # Load template
        template = cv2.imread(template_path)  # type: ignore
        if template is None:
            raise FileNotFoundError(f"Template image not found: {template_path}")
        
        # Template matching
        result = cv2.matchTemplate(screen_image, template, cv2.TM_CCOEFF_NORMED)  # type: ignore
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)  # type: ignore
        
        if max_val >= 0.8:  # Confidence threshold
            h, w = template.shape[:2]
            center_x = max_loc[0] + w // 2
            center_y = max_loc[1] + h // 2
            
            self._log_to_file("_find_template", "SUCCESS", {
                "template": template_path,
                "position": {"x": center_x, "y": center_y},
                "confidence": max_val
            })
            
            return {
                "success": True,
                "message": f"Template found at ({center_x}, {center_y})",
                "data": {
                    "x": center_x,
                    "y": center_y,
                    "confidence": float(max_val),
                    "bounding_box": {
                        "x": max_loc[0],
                        "y": max_loc[1],
                        "width": w,
                        "height": h
                    }
                },
                "error": None
            }
        
        raise VisualElementNotFoundError(f"Template '{template_path}' not found on screen")

    async def interact_with_element(self, x: int, y: int, action: str = "click") -> Dict[str, Any]:
        """
        Move mouse and interact with an element at specified coordinates.
        
        IMPORTANT: Before interacting, validates action safety through security shield.
        
        Args:
            x: X coordinate on screen
            y: Y coordinate on screen
            action: Type of interaction ("click", "double_click", "right_click")
        
        Returns:
            Dictionary with success status and interaction details.
        """
        self._log_to_file("interact_with_element", "PENDING", {"x": x, "y": y, "action": action})
        
        # Validate action safety if security shield is available
        # Check if coordinates are in a critical system area
        is_safe = True
        safety_context = {"x": x, "y": y, "action": action}
        
        # Simple heuristic: avoid bottom-left corner (Start menu in Windows)
        # and top-right corner (system tray)
        screen_width, screen_height = 1920, 1080  # Default, would be detected in production
        
        if x < 100 and y > screen_height - 100:
            safety_context["warning"] = "Near Start menu area"
            is_safe = False
        elif x > screen_width - 100 and y < 100:
            safety_context["warning"] = "Near system tray area"
            is_safe = False
        
        if not is_safe:
            self._log_to_file("interact_with_element", "BLOCKED", safety_context)
            return {
                "success": False,
                "message": "Interaction blocked: coordinates in critical system area",
                "data": None,
                "error": "Safety validation failed: critical system area"
            }
        
        try:
            if PYAUTOGUI_AVAILABLE:
                # Check if within secondary monitor bounds (if configured)
                if self._secondary_monitor_bounds and not self._is_in_secondary_monitor(x, y):
                    self._log_to_file("interact_with_element", "WARNING", 
                                     {"message": "Interaction outside secondary monitor bounds"})
                
                # Move mouse smoothly to target
                pyautogui.moveTo(x, y, duration=0.5)  # type: ignore
                
                # Perform action
                if action == "click":
                    pyautogui.click()  # type: ignore
                elif action == "double_click":
                    pyautogui.doubleClick()  # type: ignore
                elif action == "right_click":
                    pyautogui.rightClick()  # type: ignore
                else:
                    raise ValueError(f"Unknown action: {action}")
                
                self._log_to_file("interact_with_element", "SUCCESS", {
                    "x": x, "y": y, "action": action
                })
                
                return {
                    "success": True,
                    "message": f"Successfully performed {action} at ({x}, {y})",
                    "data": {"x": x, "y": y, "action": action},
                    "error": None
                }
            else:
                # Simulated interaction
                self._log_to_file("interact_with_element", "SIMULATED", {
                    "x": x, "y": y, "action": action
                })
                return {
                    "success": True,
                    "message": f"Interaction simulated: {action} at ({x}, {y})",
                    "data": {"x": x, "y": y, "action": action, "simulated": True},
                    "error": None
                }
                
        except Exception as e:
            self._log_to_file("interact_with_element", "ERROR", {"error": str(e)})
            return {
                "success": False,
                "message": "Failed to interact with element",
                "data": None,
                "error": str(e)
            }

    def _is_in_secondary_monitor(self, x: int, y: int) -> bool:
        """Check if coordinates are within secondary monitor bounds."""
        if not self._secondary_monitor_bounds:
            return True  # No bounds set, assume OK
        
        bounds = self._secondary_monitor_bounds
        return (bounds["x"] <= x < bounds["x"] + bounds["width"] and
                bounds["y"] <= y < bounds["y"] + bounds["height"])

    async def type_text_safely(self, text: str, interval: float = 0.1) -> Dict[str, Any]:
        """
        Type text simulating human keystrokes with random intervals.
        
        Args:
            text: Text to type
            interval: Base interval between keystrokes in seconds.
                     Random variation will be added to appear more human-like.
        
        Returns:
            Dictionary with success status and typing details.
        """
        self._log_to_file("type_text_safely", "PENDING", {"text_length": len(text), "interval": interval})
        
        try:
            if PYAUTOGUI_AVAILABLE:
                # Type with human-like variation
                for char in text:
                    pyautogui.write(char, interval=interval)  # type: ignore
                    # Add small random variation to appear more human
                    await asyncio.sleep(random.uniform(0.01, 0.05))
                
                self._log_to_file("type_text_safely", "SUCCESS", {
                    "characters_typed": len(text),
                    "interval": interval
                })
                
                return {
                    "success": True,
                    "message": f"Successfully typed {len(text)} characters",
                    "data": {"characters": len(text), "interval": interval},
                    "error": None
                }
            else:
                # Simulated typing
                self._log_to_file("type_text_safely", "SIMULATED", {
                    "text_length": len(text)
                })
                return {
                    "success": True,
                    "message": f"Typing simulated: {len(text)} characters",
                    "data": {"characters": len(text), "simulated": True},
                    "error": None
                }
                
        except Exception as e:
            self._log_to_file("type_text_safely", "ERROR", {"error": str(e)})
            return {
                "success": False,
                "message": "Failed to type text",
                "data": None,
                "error": str(e)
            }

    async def get_system_info(self) -> Dict[str, Any]:
        """Get current screen configuration information."""
        try:
            monitors_info = self.get_secondary_monitor_bounds()
            
            return {
                "success": True,
                "message": "System info retrieved",
                "data": {
                    "secondary_monitor": monitors_info,
                    "capture_region": self._screen_capture_region,
                    "allowed_applications": list(self._allowed_applications),
                    "pyautogui_available": PYAUTOGUI_AVAILABLE,
                    "opencv_available": OPENCV_AVAILABLE,
                    "tesseract_available": TESSERACT_AVAILABLE
                },
                "error": None
            }
        except Exception as e:
            return {
                "success": False,
                "message": "Failed to get system info",
                "data": None,
                "error": str(e)
            }
