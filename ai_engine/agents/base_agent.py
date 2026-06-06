"""
Base Agent Module for Helios Multi-Agent System

This module defines the abstract base class that all specialized agents must implement.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any


class BaseAgent(ABC):
    """
    Abstract base class for all Helios agents.
    
    All specialized agents must implement the following methods:
    - execute_task: Execute a given task and return results
    - check_authorization: Verify if an action is authorized
    - log_action: Record actions for audit and compliance
    """

    def __init__(self, agent_name: str, agent_id: str):
        """
        Initialize the base agent.
        
        Args:
            agent_name: Human-readable name of the agent
            agent_id: Unique identifier for the agent
        """
        self.agent_name = agent_name
        self.agent_id = agent_id
        self._is_active = True

    @abstractmethod
    async def execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a given task and return the results.
        
        Args:
            task: Dictionary containing task parameters and context
            
        Returns:
            Dictionary containing execution results, status, and any output data
        """
        pass

    @abstractmethod
    async def check_authorization(self, target: str) -> bool:
        """
        Check if the agent is authorized to perform an action on a target.
        
        Args:
            target: The target resource, system, or action to verify authorization for
            
        Returns:
            True if authorized, False otherwise
        """
        pass

    @abstractmethod
    async def log_action(self, action: str, context: Dict[str, Any]) -> None:
        """
        Log an action performed by the agent for audit and compliance purposes.
        
        Args:
            action: Description of the action performed
            context: Additional context information about the action
        """
        pass

    def deactivate(self):
        """Deactivate the agent."""
        self._is_active = False

    def activate(self):
        """Activate the agent."""
        self._is_active = True

    @property
    def is_active(self) -> bool:
        """Check if the agent is currently active."""
        return self._is_active
