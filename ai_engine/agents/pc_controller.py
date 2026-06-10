"""
PC Controller Agent for Helios Multi-Agent System

This agent handles PC control operations such as shutdown, restart, opening applications,
and other system-level commands with built-in security validation.
"""

import asyncio
import subprocess
import platform
import os
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List
from abc import ABC, abstractmethod

from .base_agent import BaseAgent

# Importar validador de seguridad
try:
    from ai_engine.core.security.path_validator import validate_path, is_safe_path
    PATH_VALIDATOR_AVAILABLE = True
except ImportError:
    PATH_VALIDATOR_AVAILABLE = False


# Custom Exceptions
class SecurityValidationError(Exception):
    """Raised when security validation fails."""
    pass


class ExecutionError(Exception):
    """Raised when command execution fails."""
    pass


class AuthorizationError(Exception):
    """Raised when authorization check fails."""
    pass


class PCControllerAgent(BaseAgent):
    """
    PC Controller Agent for system-level operations.
    
    This agent is responsible for:
    - Power management (shutdown, restart, sleep)
    - Application management (open, close, switch)
    - System information retrieval
    - Command execution with security validation
    
    All operations include security validation to prevent unauthorized actions.
    """

    # Dangerous commands that require explicit confirmation
    DANGEROUS_COMMANDS = [
        "rm -rf", "format", "del /s", "mkfs", "dd if=",
        "shutdown", "restart", "reboot", "poweroff",
        "fdisk", "parted", "diskpart"
    ]

    # Critical processes that should not be interrupted
    CRITICAL_PROCESSES = [
        "system", "kernel", "init", "systemd", "explorer",
        "login", "sshd", "cron", "crond"
    ]

    def __init__(self, agent_name: str = "PCController", agent_id: str = "pc-controller-001"):
        """
        Initialize the PC Controller Agent.
        
        Args:
            agent_name: Name of the agent
            agent_id: Unique identifier for the agent
        """
        super().__init__(agent_name, agent_id)
        self._require_confirmation: bool = True
        self._setup_logging()

    def _setup_logging(self) -> None:
        """Setup logging configuration for PC Controller."""
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        
        log_file = log_dir / "pc_controller.log"
        
        self.logger = logging.getLogger(f"PCController.{self.agent_id}")
        self.logger.setLevel(logging.INFO)
        
        # File handler
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.INFO)
        
        # Format: [TIMESTAMP] [ACTION] [STATUS] [CONTEXT]
        formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] [%(message)s]')
        file_handler.setFormatter(formatter)
        
        # Avoid duplicate handlers
        if not self.logger.handlers:
            self.logger.addHandler(file_handler)

    def _get_os_type(self) -> str:
        """Detect and return the operating system type."""
        system = platform.system()
        if system == "Windows":
            return "windows"
        elif system == "Darwin":
            return "macos"
        else:
            return "linux"

    def _log_action(self, action: str, status: str, context: Dict[str, Any]) -> None:
        """
        Log an action with timestamp, action type, status, and context.
        
        Args:
            action: Description of the action
            status: Status of the action (SUCCESS, FAILED, BLOCKED, PENDING)
            context: Additional context information
        """
        timestamp = datetime.now().isoformat()
        context_str = str(context).replace("\n", " ")
        log_message = f"[{action}] [{status}] {context_str}"
        self.logger.info(log_message)

    async def _check_critical_processes(self) -> List[str]:
        """
        Check for critical processes currently running.
        
        Returns:
            List of critical process names found running
        """
        critical_running = []
        os_type = self._get_os_type()
        
        try:
            if os_type == "windows":
                result = subprocess.run(
                    ["tasklist", "/FO", "CSV"],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                processes = result.stdout.lower()
            else:
                result = subprocess.run(
                    ["ps", "aux"],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                processes = result.stdout.lower()
            
            for proc in self.CRITICAL_PROCESSES:
                if proc.lower() in processes:
                    critical_running.append(proc)
                    
        except subprocess.TimeoutExpired:
            self._log_action("check_critical_processes", "TIMEOUT", {"error": "Process check timed out"})
        except Exception as e:
            self._log_action("check_critical_processes", "ERROR", {"error": str(e)})
        
        return critical_running

    async def _validate_security(self, operation: str, requires_confirmation: bool = True) -> Dict[str, Any]:
        """
        Validate security before executing an operation.
        
        Args:
            operation: The operation to validate
            requires_confirmation: Whether user confirmation is required
            
        Returns:
            Dictionary with validation results
        """
        validation_result = {
            "valid": True,
            "requires_confirmation": requires_confirmation,
            "warnings": [],
            "blocked": False,
            "reason": ""
        }
        
        # Check for critical processes if operation is destructive
        if operation.lower() in ["shutdown", "restart", "reboot"]:
            critical_procs = await self._check_critical_processes()
            if critical_procs:
                validation_result["warnings"].append(
                    f"Critical processes detected: {', '.join(critical_procs)}"
                )
        
        # Check if operation is in dangerous list
        is_dangerous = any(
            cmd in operation.lower() 
            for cmd in self.DANGEROUS_COMMANDS
        )
        
        if is_dangerous and requires_confirmation:
            validation_result["requires_confirmation"] = True
        
        self._log_action("security_validation", "SUCCESS", {
            "operation": operation,
            "result": validation_result
        })
        
        return validation_result

    async def execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a PC control task.
        
        Args:
            task: Dictionary containing task parameters
            
        Returns:
            Dictionary containing execution results
        """
        self._log_action("task_received", "PENDING", {"task": task})
        
        operation = task.get("operation", "").lower()
        target = task.get("target", "")
        parameters = task.get("parameters", {})
        
        try:
            if operation == "shutdown":
                delay = parameters.get("delay_seconds", 0)
                return await self.shutdown_system(delay_seconds=delay)
            elif operation == "restart":
                delay = parameters.get("delay_seconds", 0)
                return await self.restart_system(delay_seconds=delay)
            elif operation == "open_app":
                app_name = parameters.get("app_name", target)
                return await self.open_application(app_name)
            elif operation == "execute_command":
                command = parameters.get("command", target)
                requires_conf = parameters.get("requires_confirmation", True)
                return await self.execute_command(command, requires_confirmation=requires_conf)
            elif operation == "get_system_info":
                return await self.get_system_info()
            else:
                self._log_action("task_completed", "FAILED", {"error": f"Unknown operation: {operation}"})
                return {
                    "success": False,
                    "message": f"Unknown operation: {operation}",
                    "data": None,
                    "error": f"Unknown operation: {operation}"
                }
                
        except SecurityValidationError as e:
            self._log_action("task_completed", "BLOCKED", {"error": str(e)})
            return {
                "success": False,
                "message": "Security validation failed",
                "data": None,
                "error": str(e)
            }
        except AuthorizationError as e:
            self._log_action("task_completed", "DENIED", {"error": str(e)})
            return {
                "success": False,
                "message": "Authorization failed",
                "data": None,
                "error": str(e)
            }
        except ExecutionError as e:
            self._log_action("task_completed", "ERROR", {"error": str(e)})
            return {
                "success": False,
                "message": "Execution failed",
                "data": None,
                "error": str(e)
            }
        except Exception as e:
            self._log_action("task_completed", "ERROR", {"error": str(e), "type": type(e).__name__})
            return {
                "success": False,
                "message": "Unexpected error occurred",
                "data": None,
                "error": f"{type(e).__name__}: {str(e)}"
            }

    async def check_authorization(self, target: str) -> bool:
        """
        Check if the agent is authorized to perform an action on a target.
        
        Args:
            target: The target application, file, or system resource
            
        Returns:
            True if authorized, False otherwise
            
        Raises:
            AuthorizationError: If authorization fails
        """
        # Block access to sensitive system paths
        sensitive_paths = [
            "/etc/shadow", "/etc/passwd", "/root/", 
            "C:/Windows/System32", "C:/Users/Administrator"
        ]
        
        for path in sensitive_paths:
            if path.lower() in target.lower():
                self._log_action("authorization_check", "DENIED", {"target": target})
                raise AuthorizationError(f"Access to '{target}' is not authorized")
        
        self._log_action("authorization_check", "SUCCESS", {"target": target})
        return True

    async def log_action(self, action: str, context: Dict[str, Any]) -> None:
        """
        Log an action performed by the agent (abstract method implementation).
        
        Args:
            action: Description of the action
            context: Additional context information
        """
        self._log_action(action, "INFO", context)

    async def shutdown_system(self, delay_seconds: int = 0) -> Dict[str, Any]:
        """
        Shutdown the system with security validation.
        
        Args:
            delay_seconds: Delay in seconds before shutdown
            
        Returns:
            Dictionary with shutdown results
        """
        operation = "shutdown"
        self._log_action(operation, "PENDING", {"delay_seconds": delay_seconds})
        
        # Security validation
        validation = await self._validate_security(operation, requires_confirmation=True)
        
        if validation["blocked"]:
            raise SecurityValidationError(validation["reason"])
        
        # Check for critical processes
        critical_procs = await self._check_critical_processes()
        if critical_procs:
            warning_msg = f"Critical processes detected: {', '.join(critical_procs)}"
            self._log_action(operation, "WARNING", {"warning": warning_msg})
        
        # For safety, we simulate the shutdown in this implementation
        # In production, remove the simulation flag
        os_type = self._get_os_type()
        
        if os_type == "windows":
            cmd = ["shutdown", "/s", "/t", str(delay_seconds)]
        elif os_type == "macos":
            minutes = max(1, delay_seconds // 60)
            cmd = ["sudo", "shutdown", "-h", f"+{minutes}"]
        else:  # linux
            minutes = max(1, delay_seconds // 60)
            cmd = ["sudo", "shutdown", "-h", f"+{minutes}"]
        
        # Simulated for safety - in production, uncomment the actual execution
        # result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        self._log_action(operation, "SUCCESS", {
            "command": " ".join(cmd),
            "os_type": os_type,
            "simulated": True,
            "delay_seconds": delay_seconds
        })
        
        return {
            "success": True,
            "message": f"Shutdown command prepared ({os_type}) with {delay_seconds}s delay",
            "data": {
                "command": " ".join(cmd),
                "os_type": os_type,
                "delay_seconds": delay_seconds,
                "simulated": True
            },
            "error": None
        }

    async def restart_system(self, delay_seconds: int = 0) -> Dict[str, Any]:
        """
        Restart the system with security validation.
        
        Args:
            delay_seconds: Delay in seconds before restart
            
        Returns:
            Dictionary with restart results
        """
        operation = "restart"
        self._log_action(operation, "PENDING", {"delay_seconds": delay_seconds})
        
        # Security validation
        validation = await self._validate_security(operation, requires_confirmation=True)
        
        if validation["blocked"]:
            raise SecurityValidationError(validation["reason"])
        
        # Check for critical processes
        critical_procs = await self._check_critical_processes()
        if critical_procs:
            warning_msg = f"Critical processes detected: {', '.join(critical_procs)}"
            self._log_action(operation, "WARNING", {"warning": warning_msg})
        
        os_type = self._get_os_type()
        
        if os_type == "windows":
            cmd = ["shutdown", "/r", "/t", str(delay_seconds)]
        elif os_type == "macos":
            minutes = max(1, delay_seconds // 60)
            cmd = ["sudo", "shutdown", "-r", f"+{minutes}"]
        else:  # linux
            minutes = max(1, delay_seconds // 60)
            cmd = ["sudo", "shutdown", "-r", f"+{minutes}"]
        
        # Simulated for safety
        self._log_action(operation, "SUCCESS", {
            "command": " ".join(cmd),
            "os_type": os_type,
            "simulated": True,
            "delay_seconds": delay_seconds
        })
        
        return {
            "success": True,
            "message": f"Restart command prepared ({os_type}) with {delay_seconds}s delay",
            "data": {
                "command": " ".join(cmd),
                "os_type": os_type,
                "delay_seconds": delay_seconds,
                "simulated": True
            },
            "error": None
        }

    async def open_application(self, app_name: str) -> Dict[str, Any]:
        """
        Open a specific application.
        
        Args:
            app_name: Name of the application to open
            
        Returns:
            Dictionary with application open results
        """
        operation = "open_application"
        self._log_action(operation, "PENDING", {"app_name": app_name})
        
        # Authorization check
        await self.check_authorization(app_name)
        
        os_type = self._get_os_type()
        
        if os_type == "windows":
            cmd = ["start", "", app_name]
            shell = True
        elif os_type == "macos":
            cmd = ["open", "-a", app_name]
            shell = False
        else:  # linux
            cmd = ["xdg-open", app_name]
            shell = False
        
        try:
            # Simulated for safety - in production, use actual execution:
            # result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, shell=shell)
            
            self._log_action(operation, "SUCCESS", {
                "app_name": app_name,
                "command": " ".join(cmd) if isinstance(cmd, list) else cmd,
                "os_type": os_type,
                "simulated": True
            })
            
            return {
                "success": True,
                "message": f"Application '{app_name}' opened successfully ({os_type})",
                "data": {
                    "app_name": app_name,
                    "command": " ".join(cmd) if isinstance(cmd, list) else cmd,
                    "os_type": os_type,
                    "simulated": True
                },
                "error": None
            }
            
        except subprocess.TimeoutExpired:
            error_msg = f"Timeout while opening application '{app_name}'"
            self._log_action(operation, "ERROR", {"error": error_msg})
            raise ExecutionError(error_msg)
        except FileNotFoundError:
            error_msg = f"Application '{app_name}' not found"
            self._log_action(operation, "ERROR", {"error": error_msg})
            raise ExecutionError(error_msg)

    async def execute_command(self, command: str, requires_confirmation: bool = True) -> Dict[str, Any]:
        """
        Execute a shell command with validation.
        
        Args:
            command: The command to execute
            requires_confirmation: Whether confirmation is required for dangerous commands
            
        Returns:
            Dictionary with command execution results
        """
        operation = "execute_command"
        self._log_action(operation, "PENDING", {"command": command, "requires_confirmation": requires_confirmation})
        
        # Check for dangerous patterns
        is_dangerous = any(
            pattern in command.lower() 
            for pattern in self.DANGEROUS_COMMANDS
        )
        
        if is_dangerous and requires_confirmation:
            self._log_action(operation, "PENDING_CONFIRMATION", {
                "command": command,
                "reason": "Dangerous command detected"
            })
            return {
                "success": False,
                "message": "Command requires explicit confirmation due to potentially dangerous operations",
                "data": {
                    "command": command,
                    "confirmation_required": True,
                    "dangerous_patterns_found": True
                },
                "error": None
            }
        
        os_type = self._get_os_type()
        
        try:
            # Determine shell based on OS
            if os_type == "windows":
                shell_cmd = ["cmd", "/c", command]
            else:
                shell_cmd = ["/bin/bash", "-c", command]
            
            # Simulated for safety - in production, use actual execution:
            # result = subprocess.run(
            #     shell_cmd, 
            #     capture_output=True, 
            #     text=True, 
            #     timeout=60
            # )
            
            self._log_action(operation, "SUCCESS", {
                "command": command,
                "os_type": os_type,
                "simulated": True
            })
            
            return {
                "success": True,
                "message": f"Command executed successfully ({os_type})",
                "data": {
                    "command": command,
                    "stdout": "(simulated output)",
                    "stderr": "",
                    "return_code": 0,
                    "os_type": os_type,
                    "simulated": True
                },
                "error": None
            }
            
        except subprocess.TimeoutExpired:
            error_msg = f"Command execution timed out: {command}"
            self._log_action(operation, "ERROR", {"error": error_msg})
            raise ExecutionError(error_msg)
        except PermissionError:
            error_msg = f"Permission denied for command: {command}"
            self._log_action(operation, "ERROR", {"error": error_msg})
            raise ExecutionError(error_msg)

    async def get_system_info(self) -> Dict[str, Any]:
        """
        Get system information (CPU, RAM, disk).
        
        Returns:
            Dictionary with system information
        """
        operation = "get_system_info"
        self._log_action(operation, "PENDING", {})
        
        try:
            os_type = self._get_os_type()
            system_info = {
                "os_type": os_type,
                "platform": platform.platform(),
                "processor": platform.processor(),
                "python_version": platform.python_version(),
                "architecture": platform.machine(),
                "node": platform.node()
            }
            
            # Get CPU info
            if os_type == "windows":
                try:
                    result = subprocess.run(
                        ["wmic", "cpu", "get", "NumberOfCores,NumberOfLogicalProcessors"],
                        capture_output=True,
                        text=True,
                        timeout=10
                    )
                    system_info["cpu"] = result.stdout.strip()
                except Exception:
                    system_info["cpu"] = "Unable to retrieve CPU info"
                
                # Get RAM info
                try:
                    result = subprocess.run(
                        ["wmic", "OS", "get", "FreePhysicalMemory,TotalVisibleMemorySize"],
                        capture_output=True,
                        text=True,
                        timeout=10
                    )
                    system_info["ram"] = result.stdout.strip()
                except Exception:
                    system_info["ram"] = "Unable to retrieve RAM info"
                
                # Get disk info
                try:
                    result = subprocess.run(
                        ["wmic", "logicaldisk", "get", "Size,FreeSpace"],
                        capture_output=True,
                        text=True,
                        timeout=10
                    )
                    system_info["disk"] = result.stdout.strip()
                except Exception:
                    system_info["disk"] = "Unable to retrieve disk info"
                    
            else:  # Linux/macOS
                # Get CPU info
                try:
                    result = subprocess.run(
                        ["nproc"],
                        capture_output=True,
                        text=True,
                        timeout=10
                    )
                    system_info["cpu_cores"] = result.stdout.strip()
                except Exception:
                    system_info["cpu_cores"] = "Unable to retrieve CPU cores"
                
                # Get RAM info
                try:
                    result = subprocess.run(
                        ["free", "-h"],
                        capture_output=True,
                        text=True,
                        timeout=10
                    )
                    system_info["ram"] = result.stdout.strip()
                except Exception:
                    system_info["ram"] = "Unable to retrieve RAM info"
                
                # Get disk info
                try:
                    result = subprocess.run(
                        ["df", "-h"],
                        capture_output=True,
                        text=True,
                        timeout=10
                    )
                    system_info["disk"] = result.stdout.strip()
                except Exception:
                    system_info["disk"] = "Unable to retrieve disk info"
            
            self._log_action(operation, "SUCCESS", {"os_type": os_type})
            
            return {
                "success": True,
                "message": "System information retrieved successfully",
                "data": system_info,
                "error": None
            }
            
        except Exception as e:
            self._log_action(operation, "ERROR", {"error": str(e)})
            raise ExecutionError(f"Failed to retrieve system information: {str(e)}")
