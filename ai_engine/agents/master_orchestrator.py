"""
Master Orchestrator Agent for Helios Multi-Agent System

This agent coordinates all specialized agents, routing tasks to the appropriate
agent based on task type and managing inter-agent communication via gRPC.
"""

import asyncio
import re
from typing import Dict, Any, Optional, List
from enum import Enum
from datetime import datetime
from pathlib import Path
import logging

from .base_agent import BaseAgent
from .pc_controller import PCControllerAgent
from .pentest_agent import PentestAgent
from .visual_agent import VisualAgent
from .security_shield import SecurityShieldAgent


# Custom Exception
class OrchestrationError(Exception):
    """Raised when orchestration fails."""
    pass


class TaskType(Enum):
    """Enumeration of supported task types."""
    PC_CONTROL = "pc_control"
    PENTEST = "pentest"
    VISUAL = "visual"
    SECURITY = "security"
    UNKNOWN = "unknown"


class MasterOrchestrator(BaseAgent):
    """
    Master Orchestrator Agent that coordinates all specialized agents.
    
    This agent is responsible for:
    - Receiving tasks from users or external systems
    - Classifying tasks using intelligent rules (LLM-simulated)
    - Validating authorization before delegation
    - Delegating tasks to specialized agents
    - Aggregating results and returning unified responses
    - Managing agent lifecycle and health monitoring
    - Error handling and recovery
    """

    # Classification keywords for each task type
    PC_CONTROL_KEYWORDS = [
        "apaga", "apagar", "reinicia", "reiniciar", "abre", "abrir", 
        "cierra", "cerrar", "app", "application", "programa", "program",
        "shutdown", "restart", "reboot", "open", "close", "kill",
        "ejecuta", "ejecutar", "comando", "command", "shell",
        "informacion", "info", "sistema", "system", "cpu", "ram", "disco"
    ]
    
    PENTEST_KEYWORDS = [
        "escanea", "escanear", "scan", "vulnerability", "vulnerabilidad",
        "exploit", "pentest", "security audit", "auditoria", "owasp",
        "nmap", "masscan", "enumera", "enumerate", "puertos", "ports",
        "intrusion", "penetration", "testing", "prueba", "ataque",
        "fuerza bruta", "brute force", "sql injection", "xss"
    ]
    
    VISUAL_KEYWORDS = [
        "captura", "capture", "pantalla", "screen", "ocr", "visual",
        "monitor", "image", "imagen", "leer texto", "read text",
        "click", "escribe", "type", "tecleo", "mouse", "raton",
        "ventana", "window", "elemento", "element", "boton", "button"
    ]
    
    SECURITY_KEYWORDS = [
        "analiza", "analyze", "archivo", "file", "virus", "malware",
        "protege", "protect", "antivirus", "threat", "amenaza",
        "cuarentena", "quarantine", "aisla", "isolate", "red", "network",
        "credenciales", "credentials", "password", "contraseña",
        "inyeccion", "injection", "prompt", "rollback", "restaurar"
    ]

    def __init__(self, agent_name: str = "MasterOrchestrator", agent_id: str = "orchestrator-001"):
        """
        Initialize the Master Orchestrator.
        
        Args:
            agent_name: Name of the orchestrator agent
            agent_id: Unique identifier for the orchestrator
        """
        super().__init__(agent_name, agent_id)
        self._agents: Dict[TaskType, BaseAgent] = {}
        self._task_queue: asyncio.Queue = asyncio.Queue()
        self._action_log: List[Dict[str, Any]] = []
        self._grpc_channels: Dict[str, Any] = {}
        self._setup_logging()
        self._initialize_agents()

    def _setup_logging(self) -> None:
        """Setup logging configuration for the orchestrator."""
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        
        log_file = log_dir / "orchestrator.log"
        
        self.logger = logging.getLogger(f"MasterOrchestrator.{self.agent_id}")
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

    def _initialize_agents(self) -> None:
        """Initialize and register all specialized agents."""
        try:
            self.register_agent(TaskType.PC_CONTROL, PCControllerAgent())
            self.register_agent(TaskType.PENTEST, PentestAgent())
            self.register_agent(TaskType.VISUAL, VisualAgent())
            self.register_agent(TaskType.SECURITY, SecurityShieldAgent())
            self._log_action("agents_initialized", "SUCCESS", {
                "agents": [task_type.value for task_type in self._agents.keys()]
            })
        except Exception as e:
            self._log_action("agents_initialized", "ERROR", {"error": str(e)})
            raise OrchestrationError(f"Failed to initialize agents: {str(e)}")

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
        
        # Also store in memory
        log_entry = {
            "timestamp": timestamp,
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "action": action,
            "status": status,
            "context": context
        }
        self._action_log.append(log_entry)

    def register_agent(self, task_type: TaskType, agent: BaseAgent) -> None:
        """
        Register a specialized agent for a specific task type.
        
        Args:
            task_type: The type of task this agent handles
            agent: The agent instance to register
        """
        self._agents[task_type] = agent
        self._log_action("agent_registered", "SUCCESS", {
            "task_type": task_type.value,
            "agent_name": agent.agent_name
        })

    def unregister_agent(self, task_type: TaskType) -> None:
        """
        Unregister an agent for a specific task type.
        
        Args:
            task_type: The type of task to unregister the agent for
        """
        if task_type in self._agents:
            del self._agents[task_type]
            self._log_action("agent_unregistered", "SUCCESS", {
                "task_type": task_type.value
            })

    async def classify_task(self, user_request: str) -> Dict[str, Any]:
        """
        Classify a user request into a task type using rule-based classification.
        (Simulates LLM-based classification with keyword matching)
        
        Args:
            user_request: The user's natural language request
            
        Returns:
            Dictionary containing classification results
        """
        request_lower = user_request.lower()
        
        # Count keyword matches for each category
        scores = {
            TaskType.PC_CONTROL: 0,
            TaskType.PENTEST: 0,
            TaskType.VISUAL: 0,
            TaskType.SECURITY: 0
        }
        
        # Score each category based on keyword matches
        for keyword in self.PC_CONTROL_KEYWORDS:
            if keyword in request_lower:
                scores[TaskType.PC_CONTROL] += 1
        
        for keyword in self.PENTEST_KEYWORDS:
            if keyword in request_lower:
                scores[TaskType.PENTEST] += 1
        
        for keyword in self.VISUAL_KEYWORDS:
            if keyword in request_lower:
                scores[TaskType.VISUAL] += 1
        
        for keyword in self.SECURITY_KEYWORDS:
            if keyword in request_lower:
                scores[TaskType.SECURITY] += 1
        
        # Determine the best matching category
        max_score = max(scores.values())
        
        if max_score == 0:
            classified_type = TaskType.UNKNOWN
            confidence = 0.0
        else:
            # Get all categories with the max score
            top_categories = [t for t, s in scores.items() if s == max_score]
            
            if len(top_categories) == 1:
                classified_type = top_categories[0]
                confidence = min(1.0, max_score / 5.0)  # Normalize confidence
            else:
                # Tie-breaker: use priority order (PC_CONTROL > SECURITY > PENTEST > VISUAL)
                priority_order = [TaskType.PC_CONTROL, TaskType.SECURITY, TaskType.PENTEST, TaskType.VISUAL]
                for task_type in priority_order:
                    if task_type in top_categories:
                        classified_type = task_type
                        break
                confidence = min(1.0, max_score / 5.0)
        
        result = {
            "task_type": classified_type.value,
            "confidence": confidence,
            "scores": {t.value: s for t, s in scores.items()},
            "user_request": user_request[:100]  # Truncate for logging
        }
        
        self._log_action("task_classified", "SUCCESS", result)
        
        return {
            "success": True,
            "task_type": classified_type,
            "confidence": confidence,
            "message": f"Task classified as '{classified_type.value}' with {confidence:.2%} confidence"
        }

    async def delegate_to_agent(self, task_type: TaskType, task_details: Dict[str, Any]) -> Dict[str, Any]:
        """
        Delegate a task to the appropriate specialized agent.
        
        Args:
            task_type: The type of task to delegate
            task_details: Dictionary containing task parameters
            
        Returns:
            Dictionary containing the agent's response
            
        Raises:
            OrchestrationError: If delegation fails
        """
        self._log_action("delegation_started", "PENDING", {
            "task_type": task_type.value,
            "task_details": task_details
        })
        
        # Get the appropriate agent
        agent = self._agents.get(task_type)
        
        if agent is None:
            error_msg = f"No agent registered for task type: {task_type.value}"
            self._log_action("delegation_failed", "ERROR", {"error": error_msg})
            raise OrchestrationError(error_msg)
        
        try:
            # Execute the task through the agent
            result = await agent.execute_task(task_details)
            
            self._log_action("delegation_completed", "SUCCESS", {
                "task_type": task_type.value,
                "agent_name": agent.agent_name,
                "result_success": result.get("success", result.get("status") != "error")
            })
            
            return result
            
        except Exception as e:
            self._log_action("delegation_error", "ERROR", {
                "task_type": task_type.value,
                "agent_name": agent.agent_name,
                "error": str(e),
                "error_type": type(e).__name__
            })
            
            # Attempt basic recovery
            recovery_result = await self._attempt_recovery(task_type, task_details, e)
            
            if recovery_result:
                return recovery_result
            
            raise OrchestrationError(f"Agent execution failed: {str(e)}")

    async def _attempt_recovery(self, task_type: TaskType, task_details: Dict[str, Any], 
                                 error: Exception) -> Optional[Dict[str, Any]]:
        """
        Attempt basic recovery after an agent failure.
        
        Args:
            task_type: The type of task that failed
            task_details: Original task details
            error: The exception that was raised
            
        Returns:
            Recovery result if successful, None otherwise
        """
        self._log_action("recovery_attempted", "PENDING", {
            "task_type": task_type.value,
            "error": str(error)
        })
        
        # Basic recovery strategies:
        # 1. For PC_CONTROL errors, return safe simulated response
        if task_type == TaskType.PC_CONTROL:
            return {
                "success": False,
                "message": "Operation could not be completed. Recovery mode activated.",
                "data": {"recovery_mode": True, "original_error": str(error)},
                "error": str(error)
            }
        
        # 2. For other types, log and return error
        return None

    async def check_authorization(self, target: str) -> bool:
        """
        Check if the orchestrator is authorized to perform actions on a target.
        
        Args:
            target: The target resource or system
            
        Returns:
            True if authorized, False otherwise
        """
        # Implement authorization logic here
        authorized_targets = ["local_system", "network", "applications", "files", "localhost"]
        
        # For now, allow common targets (in production, implement proper RBAC)
        is_allowed = any(
            allowed in target.lower() 
            for allowed in authorized_targets
        ) or "localhost" in target.lower()
        
        self._log_action("authorization_check", "SUCCESS" if is_allowed else "DENIED", {
            "target": target,
            "authorized": is_allowed
        })
        
        return is_allowed

    async def log_action(self, action: str, context: Dict[str, Any]) -> None:
        """
        Log an action performed by the orchestrator.
        
        Args:
            action: Description of the action
            context: Additional context information
        """
        self._log_action(action, "INFO", context)

    async def process_user_request(self, user_request: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Process a complete user request through the full orchestration flow.
        
        This is the main entry point for user requests. It:
        1. Classifies the task
        2. Validates authorization
        3. Delegates to the appropriate agent
        4. Logs the entire process
        5. Returns a structured response
        
        Args:
            user_request: The user's natural language request
            context: Optional context dictionary (user info, session data, etc.)
            
        Returns:
            Dictionary containing the final response to the user
        """
        context = context or {}
        start_time = datetime.now()
        
        self._log_action("request_received", "PENDING", {
            "user_request": user_request[:100],
            "context_keys": list(context.keys()),
            "timestamp": start_time.isoformat()
        })
        
        try:
            # Step 1: Classify the task
            classification_result = await self.classify_task(user_request)
            
            if not classification_result["success"]:
                return {
                    "success": False,
                    "message": "Failed to classify the request",
                    "data": None,
                    "error": classification_result.get("message", "Unknown classification error")
                }
            
            task_type = classification_result["task_type"]
            
            # Handle unknown task types
            if task_type == TaskType.UNKNOWN:
                self._log_action("request_completed", "FAILED", {
                    "reason": "unknown_task_type",
                    "user_request": user_request[:100]
                })
                return {
                    "success": False,
                    "message": "I couldn't understand what type of task you're requesting. Please be more specific.",
                    "data": {
                        "supported_types": ["pc_control", "pentest", "visual", "security"],
                        "examples": {
                            "pc_control": "Apaga el PC, abre Chrome, reinicia el sistema",
                            "pentest": "Escanea la red, busca vulnerabilidades, ejecuta nmap",
                            "visual": "Captura pantalla, lee este texto, haz click aquí",
                            "security": "Analiza este archivo, protege contra virus, aisla la red"
                        }
                    },
                    "error": "unknown_task_type"
                }
            
            # Step 2: Validate authorization
            target = context.get("target", "local_system")
            is_authorized = await self.check_authorization(target)
            
            if not is_authorized:
                self._log_action("request_completed", "DENIED", {
                    "reason": "unauthorized",
                    "target": target
                })
                return {
                    "success": False,
                    "message": "You are not authorized to perform this action on the specified target.",
                    "data": {"target": target},
                    "error": "unauthorized"
                }
            
            # Step 3: Prepare task details for the agent
            task_details = {
                "operation": self._extract_operation(user_request),
                "target": target,
                "parameters": self._extract_parameters(user_request, task_type),
                "context": context,
                "original_request": user_request
            }
            
            # Step 4: Delegate to the appropriate agent
            agent_result = await self.delegate_to_agent(task_type, task_details)
            
            # Step 5: Calculate processing time and log completion
            end_time = datetime.now()
            processing_time_ms = (end_time - start_time).total_seconds() * 1000
            
            self._log_action("request_completed", "SUCCESS", {
                "task_type": task_type.value,
                "processing_time_ms": processing_time_ms,
                "result_success": agent_result.get("success", True)
            })
            
            # Return the agent's result wrapped in a standard response format
            return {
                "success": agent_result.get("success", True),
                "message": agent_result.get("message", "Task completed successfully"),
                "data": agent_result.get("data"),
                "error": agent_result.get("error"),
                "metadata": {
                    "task_type": task_type.value,
                    "classification_confidence": classification_result["confidence"],
                    "processing_time_ms": processing_time_ms,
                    "agent_used": self._agents[task_type].agent_name if task_type in self._agents else None
                }
            }
            
        except OrchestrationError as e:
            self._log_action("request_completed", "ERROR", {
                "error": str(e),
                "error_type": "OrchestrationError"
            })
            return {
                "success": False,
                "message": "An orchestration error occurred while processing your request.",
                "data": None,
                "error": str(e)
            }
        except Exception as e:
            self._log_action("request_completed", "ERROR", {
                "error": str(e),
                "error_type": type(e).__name__
            })
            return {
                "success": False,
                "message": "An unexpected error occurred while processing your request.",
                "data": None,
                "error": f"{type(e).__name__}: {str(e)}"
            }

    def _extract_operation(self, user_request: str) -> str:
        """
        Extract the operation type from a user request.
        
        Args:
            user_request: The user's natural language request
            
        Returns:
            The extracted operation name
        """
        request_lower = user_request.lower()
        
        # PC Control operations
        if any(word in request_lower for word in ["apaga", "apagar", "shutdown"]):
            return "shutdown"
        elif any(word in request_lower for word in ["reinicia", "reiniciar", "restart"]):
            return "restart"
        elif any(word in request_lower for word in ["abre", "abrir", "open"]):
            return "open_app"
        elif any(word in request_lower for word in ["ejecuta", "ejecutar", "comando", "command"]):
            return "execute_command"
        elif any(word in request_lower for word in ["informacion", "info", "sistema", "system"]):
            return "get_system_info"
        
        # Pentest operations
        elif any(word in request_lower for word in ["escanea", "escanear", "scan"]):
            return "vulnerability_scan"
        elif any(word in request_lower for word in ["vulnerabilidad", "vulnerability"]):
            return "vulnerability_scan"
        elif any(word in request_lower for word in ["nmap", "puertos", "ports"]):
            return "reconnaissance"
        elif any(word in request_lower for word in ["owasp"]):
            return "owasp_scan"
        elif any(word in request_lower for word in ["reporte", "report", "informe"]):
            return "generate_report"
        
        # Visual operations
        elif any(word in request_lower for word in ["captura", "capture", "pantalla", "screen"]):
            return "capture_screen"
        elif any(word in request_lower for word in ["ocr", "lee texto", "read text"]):
            return "ocr"
        elif any(word in request_lower for word in ["click", "presiona", "press"]):
            return "click"
        elif any(word in request_lower for word in ["escribe", "type", "teclea"]):
            return "type_text"
        elif any(word in request_lower for word in ["monitor", "monitores"]):
            return "detect_monitor"
        
        # Security operations
        elif any(word in request_lower for word in ["analiza", "analyze", "archivo", "file"]):
            return "scan_file"
        elif any(word in request_lower for word in ["virus", "malware", "antivirus"]):
            return "scan_system"
        elif any(word in request_lower for word in ["inyeccion", "injection", "prompt"]):
            return "check_prompt_injection"
        elif any(word in request_lower for word in ["aisla", "isolate", "red", "network"]):
            return "isolate_network"
        elif any(word in request_lower for word in ["credenciales", "credentials", "password"]):
            return "audit_credentials"
        elif any(word in request_lower for word in ["rollback", "restaurar", "restaurar"]):
            return "rollback_system"
        
        return "unknown"

    def _extract_parameters(self, user_request: str, task_type: TaskType) -> Dict[str, Any]:
        """
        Extract parameters from a user request based on task type.
        
        Args:
            user_request: The user's natural language request
            task_type: The classified task type
            
        Returns:
            Dictionary of extracted parameters
        """
        parameters = {}
        request_lower = user_request.lower()
        
        # Extract delay for shutdown/restart
        delay_match = re.search(r'en\s+(\d+)\s*(segundos|seconds|secs?)', request_lower)
        if delay_match:
            parameters["delay_seconds"] = int(delay_match.group(1))
        
        # Extract app name for open_application
        app_match = re.search(r'abre(?:\s+la)?(?:\s+el)?\s+(?:aplicacion|app|programa)?\s*["\']?([^\s"\']+)', request_lower)
        if app_match and task_type == TaskType.PC_CONTROL:
            parameters["app_name"] = app_match.group(1).strip()
        
        # Extract command for execute_command
        cmd_match = re.search(r'ejecuta(?:\s+el)?\s+(?:comando|command)?\s*["\']?([^"\']+)', request_lower)
        if cmd_match:
            parameters["command"] = cmd_match.group(1).strip()
        
        # Extract file path for security scan
        file_match = re.search(r'(?:archivo|file|path)\s*["\']?([^\s"\']+)', request_lower)
        if file_match:
            parameters["file_path"] = file_match.group(1).strip()
        
        # Extract target for pentest
        target_match = re.search(r'(?:\d{1,3}\.){3}\d{1,3}', request_lower)  # IP address pattern
        if target_match and task_type == TaskType.PENTEST:
            parameters["target_ip"] = target_match.group(0)
        
        return parameters

    async def broadcast_task(self, task: Dict[str, Any], exclude_types: Optional[List[TaskType]] = None) -> Dict[str, Dict[str, Any]]:
        """
        Broadcast a task to all registered agents (or all except excluded types).
        
        Args:
            task: Task to broadcast
            exclude_types: List of task types to exclude from broadcasting
            
        Returns:
            Dictionary mapping agent names to their results
        """
        exclude_types = exclude_types or []
        results = {}
        
        tasks = []
        agent_mapping = []
        
        for task_type, agent in self._agents.items():
            if task_type not in exclude_types:
                tasks.append(agent.execute_task(task))
                agent_mapping.append((task_type, agent))
        
        task_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for (task_type, agent), result in zip(agent_mapping, task_results):
            if isinstance(result, Exception):
                results[agent.agent_name] = {
                    "status": "error",
                    "error": str(result),
                    "task_type": task_type.value
                }
            else:
                results[agent.agent_name] = result
                results[agent.agent_name]["task_type"] = task_type.value
        
        self._log_action("broadcast_completed", "SUCCESS", {
            "results_count": len(results),
            "successful": sum(1 for r in results.values() if r.get("success", True))
        })
        
        return results

    def get_agent_health_status(self) -> Dict[str, bool]:
        """
        Get the health status of all registered agents.
        
        Returns:
            Dictionary mapping agent names to their active status
        """
        return {
            agent.agent_name: agent.is_active
            for agent in self._agents.values()
        }

    def get_registered_agents(self) -> Dict[str, str]:
        """
        Get a list of all registered agents.
        
        Returns:
            Dictionary mapping task types to agent names
        """
        return {
            task_type.value: agent.agent_name
            for task_type, agent in self._agents.items()
        }

    async def execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a task by delegating it to the appropriate specialized agent.
        
        This is the main entry point for task execution, implementing the BaseAgent interface.
        
        Args:
            task: Dictionary containing task parameters and context
            
        Returns:
            Dictionary containing execution results from the delegated agent
        """
        # Extract user request from task
        user_request = task.get("user_request", task.get("description", ""))
        context = task.get("context", {})
        
        # Process through the full orchestration flow
        return await self.process_user_request(user_request, context)

    async def shutdown(self) -> None:
        """Gracefully shutdown all registered agents."""
        self._log_action("shutdown_initiated", "PENDING", {
            "agents_count": len(self._agents)
        })
        
        for task_type, agent in self._agents.items():
            agent.deactivate()
            self._log_action("agent_shutdown", "SUCCESS", {
                "agent": agent.agent_name,
                "task_type": task_type.value
            })
        
        self._log_action("shutdown_completed", "SUCCESS", {})
