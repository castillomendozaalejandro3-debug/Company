"""
Pydantic Schemas for Helios AI Engine

Provides strict base models and validated schemas for all API endpoints.
All models use strict validation to prevent injection attacks and data corruption.
"""

import re
from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, ConfigDict, field_validator, Field


class StrictBaseModel(BaseModel):
    """
    Base Pydantic model with strict configuration.
    
    Features:
    - extra='forbid': Rejects unknown fields
    - strict=True: Enforces strict type checking
    - validate_assignment: Validates on attribute assignment
    """
    model_config = ConfigDict(
        extra='forbid',
        strict=True,
        validate_assignment=True,
    )


def sanitize_string(value: str) -> str:
    """
    Sanitize a string by removing potentially dangerous characters.
    
    - Removes null bytes
    - Strips leading/trailing whitespace
    - Limits consecutive whitespace
    
    Args:
        value: Input string
        
    Returns:
        Sanitized string
    """
    if not value:
        return value
    
    # Remove null bytes
    sanitized = value.replace('\x00', '')
    
    # Strip whitespace
    sanitized = sanitized.strip()
    
    # Collapse multiple whitespace to single space
    sanitized = re.sub(r'\s+', ' ', sanitized)
    
    return sanitized


# Regex patterns for validation
IP_PATTERN = r'^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$|^(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}$|^(?:[0-9a-fA-F]{1,4}:){1,7}:$|^(?:[0-9a-fA-F]{1,4}:){1,6}:[0-9a-fA-F]{1,4}$|^(?:[0-9a-fA-F]{1,4}:){1,5}(?::[0-9a-fA-F]{1,4}){1,2}$|^(?:[0-9a-fA-F]{1,4}:){1,4}(?::[0-9a-fA-F]{1,4}){1,3}$|^(?:[0-9a-fA-F]{1,4}:){1,3}(?::[0-9a-fA-F]{1,4}){1,4}$|^(?:[0-9a-fA-F]{1,4}:){1,2}(?::[0-9a-fA-F]{1,4}){1,5}$|^[0-9a-fA-F]{1,4}:(?::[0-9a-fA-F]{1,4}){1,6}$|^:(?::[0-9a-fA-F]{1,4}){1,7}$|^::$'
PATH_PATTERN = r'^[a-zA-Z0-9_\-./]+$'  # Safe path characters only
SAFE_STRING_PATTERN = r'^[\w\s\-\_\.\,\;\:\!\?\(\)\[\]\{\}\"\'\@\#\$\%\&\*\+\=\<\>\|\~\`\^\°]+$'


class ExecuteRequest(StrictBaseModel):
    """
    Request model for executing commands through the AI engine.
    
    All string fields are sanitized and validated.
    """
    request: str = Field(
        ...,
        min_length=1,
        max_length=10000,
        description="The command or request to execute"
    )
    user_id: Optional[str] = Field(
        default="anonymous",
        max_length=128,
        pattern=r'^[\w\-]+$',
        description="User identifier"
    )
    context: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Additional context for the request"
    )
    
    @field_validator('request')
    @classmethod
    def sanitize_request(cls, v: str) -> str:
        """Sanitize the request string."""
        return sanitize_string(v)
    
    @field_validator('user_id')
    @classmethod
    def sanitize_user_id(cls, v: Optional[str]) -> Optional[str]:
        """Sanitize the user ID."""
        if v is None:
            return "anonymous"
        return sanitize_string(v)


class ExecuteResponse(StrictBaseModel):
    """
    Response model for command execution results.
    """
    success: bool
    message: str = Field(..., max_length=5000)
    data: Optional[Any] = None
    error: Optional[str] = Field(default=None, max_length=2000)
    
    @field_validator('message', 'error')
    @classmethod
    def sanitize_strings(cls, v: Optional[str]) -> Optional[str]:
        """Sanitize string fields."""
        if v is None:
            return v
        return sanitize_string(v)


class HealthResponse(StrictBaseModel):
    """
    Response model for health check endpoint.
    """
    status: str = Field(..., pattern=r'^(healthy|degraded|unhealthy)$')
    python_server: bool
    rust_core: bool
    orchestrator: bool
    details: Dict[str, Any] = Field(default_factory=dict)


class PathRequest(StrictBaseModel):
    """
    Request model for operations involving file paths.
    
    Includes path traversal protection.
    """
    workspace_path: str = Field(
        ...,
        min_length=1,
        max_length=500,
        pattern=PATH_PATTERN,
        description="Base workspace directory"
    )
    target_path: str = Field(
        ...,
        min_length=1,
        max_length=500,
        pattern=PATH_PATTERN,
        description="Target path within workspace"
    )
    
    @field_validator('workspace_path', 'target_path')
    @classmethod
    def sanitize_paths(cls, v: str) -> str:
        """Sanitize and validate paths."""
        sanitized = sanitize_string(v)
        # Additional path security checks
        if '..' in sanitized:
            raise ValueError("Path traversal sequences (..) are not allowed")
        if sanitized.startswith('/') and '..' in sanitized:
            raise ValueError("Absolute paths with traversal are not allowed")
        return sanitized


class CommandRequest(StrictBaseModel):
    """
    Request model for executing system commands.
    """
    command: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Command to execute"
    )
    requires_confirmation: bool = Field(
        default=True,
        description="Whether user confirmation is required"
    )
    
    @field_validator('command')
    @classmethod
    def sanitize_command(cls, v: str) -> str:
        """Sanitize command string."""
        sanitized = sanitize_string(v)
        # Block dangerous patterns
        dangerous_patterns = [
            'rm -rf /', 'format c:', 'del /s', 'mkfs',
            'dd if=/dev/zero', '> /dev/sda'
        ]
        for pattern in dangerous_patterns:
            if pattern.lower() in sanitized.lower():
                raise ValueError(f"Dangerous command pattern detected: {pattern}")
        return sanitized


class AgentTaskRequest(StrictBaseModel):
    """
    Request model for agent task execution.
    """
    agent_id: str = Field(
        ...,
        min_length=1,
        max_length=128,
        pattern=r'^[\w\-]+$',
        description="Agent identifier"
    )
    operation: str = Field(
        ...,
        min_length=1,
        max_length=256,
        pattern=r'^[\w\_]+$',
        description="Operation to perform"
    )
    target: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Target of the operation"
    )
    parameters: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Operation parameters"
    )
    
    @field_validator('agent_id', 'operation', 'target')
    @classmethod
    def sanitize_fields(cls, v: Optional[str]) -> Optional[str]:
        """Sanitize string fields."""
        if v is None:
            return v
        return sanitize_string(v)


class LogRequest(StrictBaseModel):
    """
    Request model for retrieving logs.
    """
    lines: int = Field(
        default=50,
        ge=1,
        le=1000,
        description="Number of log lines to retrieve"
    )
    source: Optional[str] = Field(
        default=None,
        max_length=128,
        pattern=r'^[\w\-\.]+$',
        description="Specific log source file"
    )


class SecurityScanRequest(StrictBaseModel):
    """
    Request model for security scanning operations.
    """
    target: str = Field(
        ...,
        min_length=1,
        max_length=500,
        pattern=PATH_PATTERN,
        description="Target to scan"
    )
    scan_type: str = Field(
        default="quick",
        pattern=r'^(quick|full|deep|custom)$',
        description="Type of scan to perform"
    )
    options: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Additional scan options"
    )
    
    @field_validator('target')
    @classmethod
    def sanitize_target(cls, v: str) -> str:
        """Sanitize target path."""
        sanitized = sanitize_string(v)
        if '..' in sanitized:
            raise ValueError("Path traversal not allowed in scan target")
        return sanitized


# =============================================================================
# WhatsApp Integration Schemas
# =============================================================================

class WhatsAppSendRequest(StrictBaseModel):
    """Request model for sending WhatsApp messages."""
    to_number: str = Field(
        ...,
        min_length=8,
        max_length=20,
        pattern=r'^\+[1-9]\d{6,14}$',
        description="Destination phone number in international format"
    )
    message: str = Field(
        ...,
        min_length=1,
        max_length=4096,
        description="Message body"
    )
    media_url: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Optional media URL"
    )
    
    @field_validator('to_number', 'message')
    @classmethod
    def sanitize_fields(cls, v: str) -> str:
        """Sanitize string fields."""
        return sanitize_string(v)


class WhatsAppReadRequest(StrictBaseModel):
    """Request model for reading WhatsApp messages."""
    limit: int = Field(
        default=50,
        ge=1,
        le=100,
        description="Maximum number of messages to retrieve"
    )
    direction: str = Field(
        default="inbound",
        pattern=r'^(inbound|outbound|both)$',
        description="Message direction filter"
    )


# =============================================================================
# Instagram Integration Schemas
# =============================================================================

class InstagramSendMessageRequest(StrictBaseModel):
    """Request model for sending Instagram DMs."""
    recipient_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Instagram user ID"
    )
    message: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Message text"
    )
    
    @field_validator('message')
    @classmethod
    def sanitize_message(cls, v: str) -> str:
        """Sanitize message text."""
        return sanitize_string(v)


class InstagramCommentRequest(StrictBaseModel):
    """Request model for Instagram comment operations."""
    comment_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Comment ID"
    )
    reply_text: Optional[str] = Field(
        default=None,
        max_length=2000,
        description="Reply text"
    )
    
    @field_validator('reply_text')
    @classmethod
    def sanitize_reply(cls, v: Optional[str]) -> Optional[str]:
        """Sanitize reply text."""
        if v is None:
            return v
        return sanitize_string(v)


# =============================================================================
# Google Classroom Integration Schemas
# =============================================================================

class ClassroomCourseRequest(StrictBaseModel):
    """Request model for Classroom course operations."""
    course_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Course ID"
    )


class ClassroomAssignmentRequest(StrictBaseModel):
    """Request model for Classroom assignment operations."""
    course_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Course ID"
    )
    assignment_id: Optional[str] = Field(
        default=None,
        max_length=64,
        description="Assignment ID"
    )
    work_types: Optional[List[str]] = Field(
        default=None,
        description="Filter by work types"
    )


class ClassroomSyncRequest(StrictBaseModel):
    """Request model for Classroom agenda sync."""
    output_path: str = Field(
        default="agenda.json",
        max_length=500,
        pattern=r'^[a-zA-Z0-9_\-./]+$',
        description="Output file path"
    )
    course_ids: Optional[List[str]] = Field(
        default=None,
        description="Specific course IDs to sync"
    )


# =============================================================================
# Task Manager Integration Schemas
# =============================================================================

class TaskManagerListRequest(StrictBaseModel):
    """Request model for listing tasks."""
    board_id: Optional[str] = Field(
        default=None,
        max_length=64,
        description="Board/project ID"
    )
    status_filter: Optional[List[str]] = Field(
        default=None,
        description="Filter by task statuses"
    )


class TaskManagerCreateRequest(StrictBaseModel):
    """Request model for creating tasks."""
    title: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Task title"
    )
    description: Optional[str] = Field(
        default=None,
        max_length=10000,
        description="Task description"
    )
    due_date: Optional[datetime] = Field(
        default=None,
        description="Due date"
    )
    priority: str = Field(
        default="medium",
        pattern=r'^(low|medium|high|urgent)$',
        description="Task priority"
    )
    assignee_ids: Optional[List[str]] = Field(
        default=None,
        description="Assignee user IDs"
    )
    
    @field_validator('title', 'description')
    @classmethod
    def sanitize_fields(cls, v: Optional[str]) -> Optional[str]:
        """Sanitize string fields."""
        if v is None:
            return v
        return sanitize_string(v)


class TaskManagerUpdateRequest(StrictBaseModel):
    """Request model for updating task status."""
    task_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Task ID"
    )
    new_status: str = Field(
        ...,
        pattern=r'^(todo|in_progress|review|done|blocked)$',
        description="New task status"
    )


class ProductivityReportRequest(StrictBaseModel):
    """Request model for productivity reports."""
    days: int = Field(
        default=30,
        ge=1,
        le=365,
        description="Number of days for the report"
    )
    board_id: Optional[str] = Field(
        default=None,
        max_length=64,
        description="Specific board ID"
    )
