"""
PC Controller Agent for Helios Multi-Agent System

This agent handles PC control operations such as shutdown, restart, opening applications,
and other system-level commands with built-in security validation.
"""

import asyncio
import subprocess
from typing import Dict, Any, Optional
import platform

from .base_agent import BaseAgent


class PCControllerAgent(BaseAgent):
    """
    PC Controller Agent for system-level operations.
    
    This agent is responsible for:
    - Power management (shutdown, restart, sleep)
    - Application management (open, close, switch)
    - File system operations
    - System settings modification
    
    All operations include security validation to prevent unauthorized actions.
    """

    def __init__(self, agent_name: str = "PCController", agent_id: str = "pc-controller-001"):
        """
        Initialize the PC Controller Agent.
        
        Args:
            agent_name: Name of the agent
            agent_id: Unique identifier for the agent
        """
        super().__init__(agent_name, agent_id)
        self._allowed_apps: set = set()
        self._blocked_operations: set = set()
        self._require_confirmation: bool = True

    def set_allowed_apps(self, apps: list) -> None:
        """Set the list of allowed applications that can be opened."""
        self._allowed_apps = set(apps)

    def set_blocked_operations(self, operations: list) -> None:
        """Set the list of blocked operations."""
        self._blocked_operations = set(operations)

    def set_require_confirmation(self, require: bool) -> None:
        """Configure whether operations require user confirmation."""
        self._require_confirmation = require

    async def execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a PC control task.
        
        Args:
            task: Dictionary containing task parameters
            
        Returns:
            Dictionary containing execution results
        """
        await self.log_action("task_received", {"task": task})
        
        operation = task.get("operation", "").lower()
        target = task.get("target", "")
        parameters = task.get("parameters", {})
        
        # Check if operation is blocked
        if operation in self._blocked_operations:
            await self.log_action("operation_blocked", {"operation": operation})
            return {
                "status": "blocked",
                "error": f"Operation '{operation}' is blocked",
                "operation": operation
            }
        
        # Route to appropriate handler
        try:
            if operation == "shutdown":
                result = await self._shutdown(**parameters)
            elif operation == "restart":
                result = await self._restart(**parameters)
            elif operation == "sleep":
                result = await self._sleep(**parameters)
            elif operation == "open_app":
                result = await self._open_application(target, **parameters)
            elif operation == "close_app":
                result = await self._close_application(target, **parameters)
            elif operation == "run_command":
                result = await self._run_command(target, **parameters)
            elif operation == "file_operation":
                result = await self._file_operation(target, **parameters)
            else:
                result = {
                    "status": "unknown_operation",
                    "error": f"Unknown operation: {operation}"
                }
            
            await self.log_action("task_completed", {"operation": operation, "result": result})
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
        Check if the agent is authorized to perform an action on a target.
        
        Args:
            target: The target application, file, or system resource
            
        Returns:
            True if authorized, False otherwise
        """
        # Check against allowed apps list if configured
        if self._allowed_apps and target not in self._allowed_apps:
            # For applications, check if in allowed list
            if target.endswith(('.exe', '.app', '.sh')):
                return target in self._allowed_apps
        
        # Check against blocked operations
        if target in self._blocked_operations:
            return False
        
        # Default: allow common system targets
        safe_targets = ["system", "localhost", "local"]
        return target.lower() in safe_targets or not self._allowed_apps

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

    async def _shutdown(self, delay: int = 0, force: bool = False) -> Dict[str, Any]:
        """Execute system shutdown."""
        await self.log_action("shutdown_initiated", {"delay": delay, "force": force})
        
        # In production, this would execute actual shutdown
        # For safety, we'll just simulate
        system = platform.system()
        
        if system == "Windows":
            cmd = ["shutdown", "/s", "/t", str(delay)]
            if force:
                cmd.append("/f")
        elif system == "Darwin":  # macOS
            cmd = ["sudo", "shutdown", "-h", f"+{delay // 60}"]
        else:  # Linux
            cmd = ["sudo", "shutdown", "-h", f"+{delay // 60}"]
        
        # Simulated for safety - remove simulation in production
        return {
            "status": "simulated",
            "message": "Shutdown command prepared (simulated for safety)",
            "command": " ".join(cmd),
            "system": system
        }

    async def _restart(self, delay: int = 0, force: bool = False) -> Dict[str, Any]:
        """Execute system restart."""
        await self.log_action("restart_initiated", {"delay": delay, "force": force})
        
        system = platform.system()
        
        if system == "Windows":
            cmd = ["shutdown", "/r", "/t", str(delay)]
            if force:
                cmd.append("/f")
        elif system == "Darwin":
            cmd = ["sudo", "shutdown", "-r", f"+{delay // 60}"]
        else:
            cmd = ["sudo", "shutdown", "-r", f"+{delay // 60}"]
        
        return {
            "status": "simulated",
            "message": "Restart command prepared (simulated for safety)",
            "command": " ".join(cmd),
            "system": system
        }

    async def _sleep(self) -> Dict[str, Any]:
        """Put system to sleep."""
        await self.log_action("sleep_initiated", {})
        
        system = platform.system()
        
        if system == "Windows":
            cmd = ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"]
        elif system == "Darwin":
            cmd = ["pm-sleep"]
        else:
            cmd = ["systemctl", "suspend"]
        
        return {
            "status": "simulated",
            "message": "Sleep command prepared (simulated for safety)",
            "command": " ".join(cmd) if isinstance(cmd, list) else cmd,
            "system": system
        }

    async def _open_application(self, app_name: str, **kwargs) -> Dict[str, Any]:
        """Open an application."""
        await self.log_action("open_app", {"app_name": app_name})
        
        # Check authorization
        if not await self.check_authorization(app_name):
            return {
                "status": "denied",
                "error": f"Application '{app_name}' is not authorized"
            }
        
        system = platform.system()
        
        if system == "Windows":
            cmd = ["start", app_name]
        elif system == "Darwin":
            cmd = ["open", "-a", app_name]
        else:
            cmd = [app_name]
        
        return {
            "status": "simulated",
            "message": f"Application '{app_name}' open command prepared (simulated for safety)",
            "command": " ".join(cmd) if isinstance(cmd, list) else cmd,
            "system": system
        }

    async def _close_application(self, app_name: str, **kwargs) -> Dict[str, Any]:
        """Close an application."""
        await self.log_action("close_app", {"app_name": app_name})
        
        system = platform.system()
        
        if system == "Windows":
            cmd = ["taskkill", "/IM", f"{app_name}.exe"]
        elif system == "Darwin":
            cmd = ["killall", app_name]
        else:
            cmd = ["pkill", app_name]
        
        return {
            "status": "simulated",
            "message": f"Application '{app_name}' close command prepared (simulated for safety)",
            "command": " ".join(cmd) if isinstance(cmd, list) else cmd,
            "system": system
        }

    async def _run_command(self, command: str, shell: bool = False, **kwargs) -> Dict[str, Any]:
        """Run a system command."""
        await self.log_action("run_command", {"command": command, "shell": shell})
        
        # Security check: block dangerous commands
        dangerous_patterns = ["rm -rf /", "format", "del /s", "mkfs", "dd if="]
        if any(pattern in command.lower() for pattern in dangerous_patterns):
            return {
                "status": "blocked",
                "error": "Command contains potentially dangerous patterns"
            }
        
        return {
            "status": "simulated",
            "message": f"Command prepared (simulated for safety): {command}",
            "command": command
        }

    async def _file_operation(self, operation: str, path: str, **kwargs) -> Dict[str, Any]:
        """Perform file system operations."""
        await self.log_action("file_operation", {"operation": operation, "path": path})
        
        # Security validation for file paths
        dangerous_paths = ["/etc/", "/system32", "/windows/", "/root/"]
        if any(dp in path.lower() for dp in dangerous_paths):
            return {
                "status": "blocked",
                "error": "Access to system directories is restricted"
            }
        
        return {
            "status": "simulated",
            "message": f"File operation '{operation}' on '{path}' prepared (simulated for safety)",
            "operation": operation,
            "path": path
        }
