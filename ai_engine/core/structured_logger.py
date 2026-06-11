"""
Helios AI Engine - Structured Logger
Enterprise-grade JSON structured logging for ELK Stack integration.

Author: Helios Architecture Team
Version: 2.0.0
"""

import json
import logging
import sys
import traceback
from datetime import datetime, timezone
from typing import Any, Dict, Optional, List, Union
from pathlib import Path
from dataclasses import dataclass, asdict
from enum import Enum
import threading


class LogLevel(str, Enum):
    """Log level enumeration."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


@dataclass
class LogRecord:
    """Structured log record data class."""
    
    timestamp: str
    level: str
    module: str
    action: str
    message: str
    duration_ms: Optional[float] = None
    error_code: Optional[str] = None
    error_type: Optional[str] = None
    stack_trace: Optional[str] = None
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    agent_name: Optional[str] = None
    request_id: Optional[str] = None
    correlation_id: Optional[str] = None
    extra_fields: Dict[str, Any] = None
    
    def to_json(self) -> str:
        """Convert log record to JSON string."""
        data = asdict(self)
        # Remove None values
        data = {k: v for k, v in data.items() if v is not None}
        return json.dumps(data, ensure_ascii=False, default=str)


class JSONFormatter(logging.Formatter):
    """
    Custom JSON formatter for structured logging.
    
    Produces JSON output compatible with ELK Stack,
    Splunk, and other log aggregation systems.
    """
    
    def __init__(
        self,
        include_stack_trace: bool = True,
        include_location: bool = True
    ):
        super().__init__()
        self.include_stack_trace = include_stack_trace
        self.include_location = include_location
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        
        # Extract extra fields from record
        extra_fields = {}
        for key, value in record.__dict__.items():
            if key not in (
                'name', 'msg', 'args', 'created', 'filename', 'funcName',
                'levelname', 'levelno', 'lineno', 'module', 'msecs',
                'pathname', 'process', 'processName', 'relativeCreated',
                'stack_info', 'exc_info', 'exc_text', 'thread', 'threadName',
                'message', 'asctime'
            ):
                extra_fields[key] = value
        
        # Build error information
        error_code = None
        error_type = None
        stack_trace = None
        
        if record.exc_info:
            error_type = type(record.exc_info[0]).__name__ if record.exc_info[0] else "Unknown"
            error_code = getattr(record.exc_info[0], 'code', None) if record.exc_info[0] else None
            
            if self.include_stack_trace:
                stack_trace = ''.join(traceback.format_exception(*record.exc_info))
        
        # Calculate duration if present
        duration_ms = getattr(record, 'duration_ms', None)
        
        # Build log record
        log_record = LogRecord(
            timestamp=datetime.now(timezone.utc).isoformat(),
            level=record.levelname,
            module=record.name,
            action=getattr(record, 'action', record.funcName or 'unknown'),
            message=record.getMessage(),
            duration_ms=duration_ms,
            error_code=str(error_code) if error_code else None,
            error_type=error_type,
            stack_trace=stack_trace,
            session_id=getattr(record, 'session_id', None),
            user_id=getattr(record, 'user_id', None),
            agent_name=getattr(record, 'agent_name', None),
            request_id=getattr(record, 'request_id', None),
            correlation_id=getattr(record, 'correlation_id', None),
            extra_fields=extra_fields if extra_fields else None
        )
        
        return log_record.to_json()


class StructuredLogger:
    """
    Enterprise structured logger with ELK Stack integration.
    
    Features:
    - JSON structured output
    - Correlation ID tracking
    - Session and user context
    - Performance timing
    - Error categorization
    - Thread-safe operation
    """
    
    _loggers: Dict[str, logging.Logger] = {}
    _lock = threading.Lock()
    _default_handlers_initialized = False
    
    @classmethod
    def get_logger(
        cls,
        name: str,
        level: Union[str, int] = logging.INFO,
        log_file: Optional[str] = None,
        console_output: bool = True,
        elk_compatible: bool = True
    ) -> logging.Logger:
        """
        Get or create a structured logger instance.
        
        Args:
            name: Logger name (typically __name__)
            level: Logging level
            log_file: Optional file path for log output
            console_output: Whether to output to console
            elk_compatible: Use ELK-compatible JSON format
        
        Returns:
            Configured logger instance
        """
        with cls._lock:
            if name in cls._loggers:
                return cls._loggers[name]
            
            logger = logging.getLogger(name)
            logger.setLevel(level)
            
            # Clear existing handlers
            logger.handlers.clear()
            
            # Create formatter
            if elk_compatible:
                formatter = JSONFormatter()
            else:
                formatter = logging.Formatter(
                    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
                )
            
            # Console handler
            if console_output:
                console_handler = logging.StreamHandler(sys.stdout)
                console_handler.setFormatter(formatter)
                logger.addHandler(console_handler)
            
            # File handler
            if log_file:
                log_path = Path(log_file)
                log_path.parent.mkdir(parents=True, exist_ok=True)
                file_handler = logging.FileHandler(log_file, encoding='utf-8')
                file_handler.setFormatter(formatter)
                logger.addHandler(file_handler)
            
            cls._loggers[name] = logger
            return logger
    
    @classmethod
    def configure_root_logger(
        cls,
        level: Union[str, int] = logging.INFO,
        log_dir: Optional[str] = "logs",
        max_bytes: int = 10485760,  # 10MB
        backup_count: int = 5
    ) -> None:
        """
        Configure the root logger with rotating file handlers.
        
        Args:
            level: Root logging level
            log_dir: Directory for log files
            max_bytes: Maximum size per log file
            backup_count: Number of backup files to keep
        """
        with cls._lock:
            if cls._default_handlers_initialized:
                return
            
            root_logger = logging.getLogger()
            root_logger.setLevel(level)
            
            # Clear existing handlers
            root_logger.handlers.clear()
            
            # JSON formatter
            formatter = JSONFormatter()
            
            # Console handler
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(formatter)
            root_logger.addHandler(console_handler)
            
            # Rotating file handler
            if log_dir:
                from logging.handlers import RotatingFileHandler
                
                log_path = Path(log_dir)
                log_path.mkdir(parents=True, exist_ok=True)
                
                file_handler = RotatingFileHandler(
                    log_path / "helios.log",
                    maxBytes=max_bytes,
                    backupCount=backup_count,
                    encoding='utf-8'
                )
                file_handler.setFormatter(formatter)
                root_logger.addHandler(file_handler)
                
                # Error-specific log file
                error_handler = RotatingFileHandler(
                    log_path / "helios_errors.log",
                    maxBytes=max_bytes,
                    backupCount=backup_count,
                    encoding='utf-8'
                )
                error_handler.setLevel(logging.ERROR)
                error_handler.setFormatter(formatter)
                root_logger.addHandler(error_handler)
            
            cls._default_handlers_initialized = True


def get_logger(
    name: str,
    level: Union[str, int] = logging.INFO,
    log_file: Optional[str] = None
) -> logging.Logger:
    """
    Convenience function to get a structured logger.
    
    Usage:
        logger = get_logger(__name__)
        logger.info("Message", extra={"action": "my_action", "duration_ms": 123})
    
    Args:
        name: Logger name
        level: Logging level
        log_file: Optional log file path
    
    Returns:
        Configured logger instance
    """
    return StructuredLogger.get_logger(name, level, log_file)


def log_async_operation(
    logger: logging.Logger,
    action: str,
    start_time: float,
    success: bool = True,
    error: Optional[Exception] = None,
    **extra_kwargs
):
    """
    Log an async operation with timing information.
    
    Usage:
        start = time.perf_counter()
        try:
            result = await some_operation()
            log_async_operation(logger, "some_operation", start, success=True)
        except Exception as e:
            log_async_operation(logger, "some_operation", start, success=False, error=e)
    
    Args:
        logger: Logger instance
        action: Action name
        start_time: Start time from perf_counter()
        success: Whether operation succeeded
        error: Optional exception if failed
        **extra_kwargs: Additional fields to include
    """
    import time
    
    duration_ms = (time.perf_counter() - start_time) * 1000
    
    extra = {
        "action": action,
        "duration_ms": round(duration_ms, 2),
        **extra_kwargs
    }
    
    if success:
        logger.info(f"Completed {action}", extra=extra)
    else:
        extra["error"] = str(error) if error else None
        extra["error_type"] = type(error).__name__ if error else None
        logger.error(f"Failed {action}", exc_info=error, extra=extra)


class LogContext:
    """
    Context manager for adding contextual information to logs.
    
    Usage:
        with LogContext(session_id="abc123", user_id="user456"):
            logger.info("Operation in context")
    """
    
    _context: Dict[str, Any] = {}
    _lock = threading.Lock()
    
    def __init__(self, **context_kwargs):
        self.context = context_kwargs
        self.previous_context: Dict[str, Any] = {}
    
    def __enter__(self):
        with self._lock:
            # Save previous context
            self.previous_context = self._context.copy()
            # Merge new context
            self._context.update(self.context)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        with self._lock:
            # Restore previous context
            self._context.clear()
            self._context.update(self.previous_context)
        return False
    
    @classmethod
    def get_context(cls) -> Dict[str, Any]:
        """Get current log context."""
        with cls._lock:
            return cls._context.copy()
    
    @classmethod
    def clear_context(cls) -> None:
        """Clear all log context."""
        with cls._lock:
            cls._context.clear()


class FilterSensitiveData(logging.Filter):
    """
    Logging filter to redact sensitive information.
    
    Prevents passwords, API keys, tokens, etc. from appearing in logs.
    """
    
    SENSITIVE_PATTERNS = [
        "password",
        "passwd",
        "secret",
        "api_key",
        "apikey",
        "token",
        "authorization",
        "bearer",
        "credential",
        "private_key",
        "access_token",
        "refresh_token",
    ]
    
    REDACTED_VALUE = "***REDACTED***"
    
    def filter(self, record: logging.LogRecord) -> bool:
        """Filter out sensitive data from log record."""
        # Check message
        record.msg = self._redact_sensitive(str(record.msg))
        
        # Check args
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: self._redact_sensitive(v) if isinstance(v, str) else v
                    for k, v in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    self._redact_sensitive(arg) if isinstance(arg, str) else arg
                    for arg in record.args
                )
        
        # Check extra fields
        for key in dir(record):
            if key.startswith('_'):
                continue
            try:
                value = getattr(record, key)
                if isinstance(value, str):
                    setattr(record, key, self._redact_sensitive(value))
            except (AttributeError, TypeError):
                pass
        
        return True
    
    def _redact_sensitive(self, value: str) -> str:
        """Redact sensitive patterns from a string value."""
        if not value:
            return value
        
        result = value
        for pattern in self.SENSITIVE_PATTERNS:
            if pattern.lower() in result.lower():
                # Simple redaction - in production use regex for better matching
                result = self.REDACTED_VALUE
                break
        
        return result


# Initialize root logger on module import
StructuredLogger.configure_root_logger()
