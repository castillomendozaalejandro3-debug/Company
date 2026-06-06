"""
Master Orchestrator Agent for Helios Multi-Agent System

This agent coordinates all specialized agents, routing tasks to the appropriate
agent based on task type and managing inter-agent communication via gRPC.
"""

import asyncio
from typing import Dict, Any, Optional, List
from enum import Enum

from .base_agent import BaseAgent


class TaskType(Enum):
    """Enumeration of supported task types."""
    PC_CONTROL = "pc_control"
    PENTEST = "pentest"
    VISUAL = "visual"
    SECURITY = "security"
    GENERAL = "general"


class MasterOrchestrator(BaseAgent):
    """
    Master Orchestrator Agent that coordinates all specialized agents.
    
    This agent is responsible for:
    - Receiving tasks from users or external systems
    - Analyzing task requirements and determining the appropriate agent
    - Delegating tasks to specialized agents
    - Aggregating results and returning unified responses
    - Managing agent lifecycle and health monitoring
    """

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
        self._grpc_channels: Dict[str, Any] = {}
        self._action_log: List[Dict[str, Any]] = []

    def register_agent(self, task_type: TaskType, agent: BaseAgent) -> None:
        """
        Register a specialized agent for a specific task type.
        
        Args:
            task_type: The type of task this agent handles
            agent: The agent instance to register
        """
        self._agents[task_type] = agent

    def unregister_agent(self, task_type: TaskType) -> None:
        """
        Unregister an agent for a specific task type.
        
        Args:
            task_type: The type of task to unregister the agent for
        """
        if task_type in self._agents:
            del self._agents[task_type]

    def _determine_task_type(self, task: Dict[str, Any]) -> TaskType:
        """
        Determine the appropriate task type based on task parameters.
        
        Args:
            task: Dictionary containing task parameters
            
        Returns:
            TaskType enumeration value
        """
        task_category = task.get("category", "").lower()
        task_description = task.get("description", "").lower()
        
        # Map keywords to task types
        pc_control_keywords = ["apagar", "reiniciar", "abrir", "cerrar", "app", "application", "program"]
        pentest_keywords = ["scan", "vulnerability", "exploit", "pentest", "security audit", "owasp"]
        visual_keywords = ["ocr", "screen", "visual", "monitor", "image", "capture"]
        security_keywords = ["antivirus", "threat", "malware", "shield", "protect", "block"]
        
        combined_text = f"{task_category} {task_description}"
        
        if any(keyword in combined_text for keyword in pentest_keywords):
            return TaskType.PENTEST
        elif any(keyword in combined_text for keyword in security_keywords):
            return TaskType.SECURITY
        elif any(keyword in combined_text for keyword in visual_keywords):
            return TaskType.VISUAL
        elif any(keyword in combined_text for keyword in pc_control_keywords):
            return TaskType.PC_CONTROL
        else:
            return TaskType.GENERAL

    async def execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a task by delegating it to the appropriate specialized agent.
        
        Args:
            task: Dictionary containing task parameters and context
            
        Returns:
            Dictionary containing execution results from the delegated agent
        """
        await self.log_action("task_received", {"task": task})
        
        # Determine task type
        task_type = self._determine_task_type(task)
        
        # Check authorization
        target = task.get("target", str(task_type.value))
        is_authorized = await self.check_authorization(target)
        
        if not is_authorized:
            await self.log_action("task_denied", {"reason": "unauthorized", "task": task})
            return {
                "status": "denied",
                "error": "Task not authorized",
                "task_type": task_type.value
            }
        
        # Get the appropriate agent
        agent = self._agents.get(task_type)
        
        if agent is None:
            # Handle general tasks or unregistered task types
            if task_type == TaskType.GENERAL:
                await self.log_action("task_completed", {"task_type": "general", "task": task})
                return {
                    "status": "completed",
                    "result": "General task processed",
                    "task_type": task_type.value
                }
            else:
                error_msg = f"No agent registered for task type: {task_type.value}"
                await self.log_action("task_failed", {"error": error_msg, "task": task})
                return {
                    "status": "failed",
                    "error": error_msg,
                    "task_type": task_type.value
                }
        
        # Delegate to specialized agent
        try:
            result = await agent.execute_task(task)
            await self.log_action("task_delegated", {
                "task_type": task_type.value,
                "agent": agent.agent_name,
                "result_status": result.get("status", "unknown")
            })
            return result
        except Exception as e:
            await self.log_action("task_error", {"error": str(e), "task": task})
            return {
                "status": "error",
                "error": str(e),
                "task_type": task_type.value
            }

    async def check_authorization(self, target: str) -> bool:
        """
        Check if the orchestrator is authorized to perform actions on a target.
        
        Args:
            target: The target resource or system
            
        Returns:
            True if authorized, False otherwise
        """
        # Implement authorization logic here
        # This could integrate with RBAC, policy engines, or user confirmation systems
        authorized_targets = ["local_system", "network", "applications", "files"]
        
        # For now, allow common targets (in production, implement proper RBAC)
        is_allowed = target.lower() in authorized_targets or "localhost" in target.lower()
        
        await self.log_action("authorization_check", {
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
        log_entry = {
            "timestamp": asyncio.get_event_loop().time(),
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "action": action,
            "context": context
        }
        self._action_log.append(log_entry)
        
        # In production, this would write to a persistent log store
        print(f"[LOG] {self.agent_name}: {action} - {context}")

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
        for task_type, agent in self._agents.items():
            if task_type not in exclude_types:
                tasks.append(agent.execute_task(task))
        
        task_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for (task_type, agent), result in zip(self._agents.items(), task_results):
            if task_type not in exclude_types:
                if isinstance(result, Exception):
                    results[agent.agent_name] = {"status": "error", "error": str(result)}
                else:
                    results[agent.agent_name] = result
        
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

    async def shutdown(self) -> None:
        """Gracefully shutdown all registered agents."""
        for agent in self._agents.values():
            agent.deactivate()
            await self.log_action("agent_shutdown", {"agent": agent.agent_name})
