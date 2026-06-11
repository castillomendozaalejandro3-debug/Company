"""
Helios AI Engine - Metrics Collector for Prometheus
Enterprise-grade metrics collection and exposition layer.

Author: Helios Architecture Team
Version: 2.0.0
"""

import asyncio
import time
import threading
from typing import Dict, Optional, Any, List
from dataclasses import dataclass, field
from contextlib import contextmanager
from functools import wraps

from prometheus_client import (
    Counter,
    Gauge,
    Histogram,
    Summary,
    CollectorRegistry,
    generate_latest,
    CONTENT_TYPE_LATEST,
    start_http_server,
)
from prometheus_client.multiprocess import MultiProcessCollector

from ai_engine.core.structured_logger import get_logger

logger = get_logger(__name__)


@dataclass
class MetricConfig:
    """Configuration for metrics collection."""
    
    namespace: str = "helios"
    subsystem: str = "ai_engine"
    latency_buckets: tuple = field(
        default_factory=lambda: (
            0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0
        )
    )
    memory_buckets: tuple = field(
        default_factory=lambda: (
            1048576, 10485760, 104857600, 524288000, 1073741824, 2147483648
        )
    )
    token_buckets: tuple = field(
        default_factory=lambda: (
            10, 50, 100, 250, 500, 1000, 2500, 5000, 10000, 50000
        )
    )


class MetricsCollector:
    """
    Enterprise-grade metrics collector for Helios AI Engine.
    
    Exposes metrics in Prometheus format and provides decorators
    for automatic instrumentation of async functions.
    
    Thread-safe and compatible with async event loops.
    """
    
    _instance: Optional["MetricsCollector"] = None
    _lock = threading.Lock()
    
    def __new__(cls, config: Optional[MetricConfig] = None) -> "MetricsCollector":
        """Singleton pattern for metrics collector."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, config: Optional[MetricConfig] = None):
        """Initialize metrics collector with configuration."""
        if self._initialized:
            return
            
        self.config = config or MetricConfig()
        self.registry = CollectorRegistry()
        
        # Initialize all metrics
        self._init_llm_metrics()
        self._init_agent_metrics()
        self._init_resource_metrics()
        self._init_token_metrics()
        self._init_validation_metrics()
        self._init_security_metrics()
        self._init_session_metrics()
        
        self._initialized = True
        self._http_server_started = False
        self._server_thread: Optional[threading.Thread] = None
        
        logger.info("MetricsCollector initialized", extra={
            "namespace": self.config.namespace,
            "subsystem": self.config.subsystem
        })
    
    def _init_llm_metrics(self) -> None:
        """Initialize LLM-related metrics."""
        # Latency histogram for LLM responses
        self.llm_latency_histogram = Histogram(
            name="llm_response_latency_seconds",
            documentation="Latency of LLM response generation in seconds",
            labelnames=["model", "agent_type", "status"],
            buckets=self.config.latency_buckets,
            registry=self.registry
        )
        
        # Summary for LLM latency (for quantiles)
        self.llm_latency_summary = Summary(
            name="llm_response_latency_summary_seconds",
            documentation="Summary of LLM response latency with quantiles",
            labelnames=["model", "agent_type"],
            registry=self.registry
        )
        
        # Counter for LLM requests
        self.llm_requests_total = Counter(
            name="llm_requests_total",
            documentation="Total number of LLM requests",
            labelnames=["model", "agent_type", "status"],
            registry=self.registry
        )
        
        # Gauge for active LLM connections
        self.llm_active_connections = Gauge(
            name="llm_active_connections",
            documentation="Number of active LLM connections",
            labelnames=["model"],
            registry=self.registry
        )
    
    def _init_agent_metrics(self) -> None:
        """Initialize agent-specific metrics."""
        # Error rate by agent
        self.agent_errors_total = Counter(
            name="agent_errors_total",
            documentation="Total number of errors per agent",
            labelnames=["agent_name", "error_type", "severity"],
            registry=self.registry
        )
        
        # Agent execution count
        self.agent_executions_total = Counter(
            name="agent_executions_total",
            documentation="Total number of agent executions",
            labelnames=["agent_name", "action"],
            registry=self.registry
        )
        
        # Agent execution duration
        self.agent_execution_duration = Histogram(
            name="agent_execution_duration_seconds",
            documentation="Duration of agent execution in seconds",
            labelnames=["agent_name", "action", "status"],
            buckets=self.config.latency_buckets,
            registry=self.registry
        )
        
        # Active agents gauge
        self.active_agents = Gauge(
            name="active_agents_count",
            documentation="Number of currently active agents",
            labelnames=["agent_type"],
            registry=self.registry
        )
    
    def _init_resource_metrics(self) -> None:
        """Initialize system resource metrics."""
        # Memory usage
        self.memory_usage_bytes = Gauge(
            name="process_memory_usage_bytes",
            documentation="Current memory usage of the process in bytes",
            labelnames=["memory_type"],  # rss, vms, shared, etc.
            registry=self.registry
        )
        
        # CPU usage
        self.cpu_usage_percent = Gauge(
            name="process_cpu_usage_percent",
            documentation="Current CPU usage percentage",
            labelnames=["cpu_type"],  # user, system, total
            registry=self.registry
        )
        
        # Kernel resource usage
        self.kernel_cpu_usage = Gauge(
            name="kernel_cpu_usage_percent",
            documentation="CPU usage of the Helios Kernel",
            registry=self.registry
        )
        
        self.kernel_memory_usage = Gauge(
            name="kernel_memory_usage_bytes",
            documentation="Memory usage of the Helios Kernel",
            registry=self.registry
        )
        
        # Thread count
        self.thread_count = Gauge(
            name="process_thread_count",
            documentation="Number of active threads",
            registry=self.registry
        )
    
    def _init_token_metrics(self) -> None:
        """Initialize token consumption metrics."""
        # Tokens consumed per session
        self.tokens_consumed_total = Counter(
            name="llm_tokens_consumed_total",
            documentation="Total number of tokens consumed",
            labelnames=["model", "token_type", "session_id"],
            registry=self.registry
        )
        
        # Tokens per request
        self.tokens_per_request = Histogram(
            name="llm_tokens_per_request",
            documentation="Number of tokens per LLM request",
            labelnames=["model", "token_type"],
            buckets=self.config.token_buckets,
            registry=self.registry
        )
        
        # Token rate (tokens per second)
        self.token_rate = Gauge(
            name="llm_token_rate_per_second",
            documentation="Current token consumption rate",
            labelnames=["model"],
            registry=self.registry
        )
    
    def _init_validation_metrics(self) -> None:
        """Initialize validation error metrics."""
        # Pydantic validation errors
        self.pydantic_validation_errors = Counter(
            name="pydantic_validation_errors_total",
            documentation="Total number of Pydantic validation errors",
            labelnames=["model_name", "field_name", "error_type"],
            registry=self.registry
        )
        
        # Schema validation failures
        self.schema_validation_failures = Counter(
            name="schema_validation_failures_total",
            documentation="Total number of schema validation failures",
            labelnames=["schema_name", "validation_stage"],
            registry=self.registry
        )
        
        # Validation success rate
        self.validation_success_total = Counter(
            name="validation_success_total",
            documentation="Total number of successful validations",
            labelnames=["validator_name"],
            registry=self.registry
        )
    
    def _init_security_metrics(self) -> None:
        """Initialize security-related metrics."""
        # Path traversal attempts blocked
        self.path_traversal_blocked = Counter(
            name="security_path_traversal_blocked_total",
            documentation="Total number of blocked path traversal attempts",
            labelnames=["source_ip", "path_pattern", "agent"],
            registry=self.registry
        )
        
        # DPI violations detected
        self.dpi_violations_detected = Counter(
            name="security_dpi_violations_total",
            documentation="Total number of DPI policy violations detected",
            labelnames=["violation_type", "data_category", "agent"],
            registry=self.registry
        )
        
        # Authentication failures
        self.auth_failures_total = Counter(
            name="auth_failures_total",
            documentation="Total number of authentication failures",
            labelnames=["auth_method", "reason"],
            registry=self.registry
        )
        
        # Rate limit hits
        self.rate_limit_hits_total = Counter(
            name="rate_limit_hits_total",
            documentation="Total number of rate limit violations",
            labelnames=["endpoint", "client_id"],
            registry=self.registry
        )
        
        # Security alerts
        self.security_alerts_total = Counter(
            name="security_alerts_total",
            documentation="Total number of security alerts generated",
            labelnames=["alert_type", "severity"],
            registry=self.registry
        )
    
    def _init_session_metrics(self) -> None:
        """Initialize session-related metrics."""
        # Active sessions
        self.active_sessions = Gauge(
            name="active_sessions_count",
            documentation="Number of currently active sessions",
            registry=self.registry
        )
        
        # Session duration
        self.session_duration = Histogram(
            name="session_duration_seconds",
            documentation="Duration of user sessions",
            labelnames=["session_type"],
            buckets=(60, 300, 600, 1800, 3600, 7200, 14400, 28800, 86400),
            registry=self.registry
        )
        
        # Messages per session
        self.messages_per_session = Histogram(
            name="messages_per_session",
            documentation="Number of messages per session",
            labelnames=["session_type"],
            buckets=(1, 5, 10, 25, 50, 100, 250, 500, 1000),
            registry=self.registry
        )
    
    def start_http_server(self, port: int = 9090, addr: str = "0.0.0.0") -> None:
        """
        Start Prometheus HTTP server in a background thread.
        
        Args:
            port: Port to expose metrics on
            addr: Address to bind to
        """
        if self._http_server_started:
            logger.warning("Prometheus HTTP server already started")
            return
        
        def run_server():
            try:
                start_http_server(port=port, addr=addr, registry=self.registry)
                logger.info(f"Prometheus metrics server started on {addr}:{port}/metrics")
            except Exception as e:
                logger.error(f"Failed to start Prometheus server: {e}", extra={
                    "error": str(e),
                    "port": port
                })
        
        self._server_thread = threading.Thread(
            target=run_server,
            daemon=True,
            name="PrometheusMetricsServer"
        )
        self._server_thread.start()
        self._http_server_started = True
    
    def get_metrics(self) -> bytes:
        """
        Get current metrics in Prometheus format.
        
        Returns:
            Bytes containing Prometheus-formatted metrics
        """
        return generate_latest(self.registry)
    
    def get_content_type(self) -> str:
        """Get the content type for Prometheus metrics."""
        return CONTENT_TYPE_LATEST
    
    # =========================================================================
    # LLM Metrics Methods
    # =========================================================================
    
    def record_llm_latency(
        self,
        latency_seconds: float,
        model: str,
        agent_type: str,
        status: str = "success"
    ) -> None:
        """Record LLM response latency."""
        self.llm_latency_histogram.labels(
            model=model,
            agent_type=agent_type,
            status=status
        ).observe(latency_seconds)
        
        self.llm_latency_summary.labels(
            model=model,
            agent_type=agent_type
        ).observe(latency_seconds)
    
    def increment_llm_requests(
        self,
        model: str,
        agent_type: str,
        status: str = "success"
    ) -> None:
        """Increment LLM request counter."""
        self.llm_requests_total.labels(
            model=model,
            agent_type=agent_type,
            status=status
        ).inc()
    
    def set_llm_active_connections(self, model: str, count: int) -> None:
        """Set the number of active LLM connections."""
        self.llm_active_connections.labels(model=model).set(count)
    
    # =========================================================================
    # Agent Metrics Methods
    # =========================================================================
    
    def record_agent_error(
        self,
        agent_name: str,
        error_type: str,
        severity: str = "error"
    ) -> None:
        """Record an agent error."""
        self.agent_errors_total.labels(
            agent_name=agent_name,
            error_type=error_type,
            severity=severity
        ).inc()
    
    def increment_agent_execution(
        self,
        agent_name: str,
        action: str
    ) -> None:
        """Increment agent execution counter."""
        self.agent_executions_total.labels(
            agent_name=agent_name,
            action=action
        ).inc()
    
    def record_agent_execution_duration(
        self,
        agent_name: str,
        action: str,
        duration_seconds: float,
        status: str = "success"
    ) -> None:
        """Record agent execution duration."""
        self.agent_execution_duration.labels(
            agent_name=agent_name,
            action=action,
            status=status
        ).observe(duration_seconds)
    
    def set_active_agents(self, agent_type: str, count: int) -> None:
        """Set the number of active agents."""
        self.active_agents.labels(agent_type=agent_type).set(count)
    
    # =========================================================================
    # Resource Metrics Methods
    # =========================================================================
    
    def update_memory_usage(
        self,
        rss: int,
        vms: int,
        shared: Optional[int] = None
    ) -> None:
        """Update memory usage metrics."""
        self.memory_usage_bytes.labels(memory_type="rss").set(rss)
        self.memory_usage_bytes.labels(memory_type="vms").set(vms)
        if shared is not None:
            self.memory_usage_bytes.labels(memory_type="shared").set(shared)
    
    def update_cpu_usage(
        self,
        user_percent: float,
        system_percent: float,
        total_percent: float
    ) -> None:
        """Update CPU usage metrics."""
        self.cpu_usage_percent.labels(cpu_type="user").set(user_percent)
        self.cpu_usage_percent.labels(cpu_type="system").set(system_percent)
        self.cpu_usage_percent.labels(cpu_type="total").set(total_percent)
    
    def update_kernel_resources(
        self,
        cpu_percent: float,
        memory_bytes: int
    ) -> None:
        """Update kernel resource metrics."""
        self.kernel_cpu_usage.set(cpu_percent)
        self.kernel_memory_usage.set(memory_bytes)
    
    def update_thread_count(self, count: int) -> None:
        """Update thread count metric."""
        self.thread_count.set(count)
    
    # =========================================================================
    # Token Metrics Methods
    # =========================================================================
    
    def record_tokens_consumed(
        self,
        model: str,
        token_type: str,
        count: int,
        session_id: Optional[str] = None
    ) -> None:
        """Record tokens consumed."""
        session_label = session_id or "unknown"
        self.tokens_consumed_total.labels(
            model=model,
            token_type=token_type,
            session_id=session_label
        ).inc(count)
    
    def record_tokens_per_request(
        self,
        model: str,
        token_type: str,
        count: int
    ) -> None:
        """Record tokens per request."""
        self.tokens_per_request.labels(
            model=model,
            token_type=token_type
        ).observe(count)
    
    def update_token_rate(self, model: str, rate: float) -> None:
        """Update token consumption rate."""
        self.token_rate.labels(model=model).set(rate)
    
    # =========================================================================
    # Validation Metrics Methods
    # =========================================================================
    
    def record_pydantic_error(
        self,
        model_name: str,
        field_name: str,
        error_type: str
    ) -> None:
        """Record a Pydantic validation error."""
        self.pydantic_validation_errors.labels(
            model_name=model_name,
            field_name=field_name,
            error_type=error_type
        ).inc()
    
    def record_schema_validation_failure(
        self,
        schema_name: str,
        validation_stage: str
    ) -> None:
        """Record a schema validation failure."""
        self.schema_validation_failures.labels(
            schema_name=schema_name,
            validation_stage=validation_stage
        ).inc()
    
    def record_validation_success(self, validator_name: str) -> None:
        """Record a successful validation."""
        self.validation_success_total.labels(
            validator_name=validator_name
        ).inc()
    
    # =========================================================================
    # Security Metrics Methods
    # =========================================================================
    
    def record_path_traversal_blocked(
        self,
        source_ip: str,
        path_pattern: str,
        agent: str
    ) -> None:
        """Record a blocked path traversal attempt."""
        self.path_traversal_blocked.labels(
            source_ip=source_ip,
            path_pattern=path_pattern,
            agent=agent
        ).inc()
        self.security_alerts_total.labels(
            alert_type="path_traversal",
            severity="high"
        ).inc()
    
    def record_dpi_violation(
        self,
        violation_type: str,
        data_category: str,
        agent: str
    ) -> None:
        """Record a DPI policy violation."""
        self.dpi_violations_detected.labels(
            violation_type=violation_type,
            data_category=data_category,
            agent=agent
        ).inc()
        self.security_alerts_total.labels(
            alert_type="dpi_violation",
            severity="critical"
        ).inc()
    
    def record_auth_failure(
        self,
        auth_method: str,
        reason: str
    ) -> None:
        """Record an authentication failure."""
        self.auth_failures_total.labels(
            auth_method=auth_method,
            reason=reason
        ).inc()
    
    def record_rate_limit_hit(
        self,
        endpoint: str,
        client_id: str
    ) -> None:
        """Record a rate limit violation."""
        self.rate_limit_hits_total.labels(
            endpoint=endpoint,
            client_id=client_id
        ).inc()
    
    # =========================================================================
    # Session Metrics Methods
    # =========================================================================
    
    def update_active_sessions(self, count: int) -> None:
        """Update active session count."""
        self.active_sessions.set(count)
    
    def record_session_duration(
        self,
        duration_seconds: float,
        session_type: str = "default"
    ) -> None:
        """Record session duration."""
        self.session_duration.labels(session_type=session_type).observe(
            duration_seconds
        )
    
    def record_messages_per_session(
        self,
        count: int,
        session_type: str = "default"
    ) -> None:
        """Record messages per session."""
        self.messages_per_session.labels(session_type=session_type).observe(count)
    
    # =========================================================================
    # Context Manager and Decorator
    # =========================================================================
    
    @contextmanager
    def track_latency(self, metric_name: str = "custom_latency"):
        """
        Context manager to track latency of a code block.
        
        Usage:
            with metrics.track_latency("my_operation"):
                # do something
        """
        start_time = time.perf_counter()
        status = "success"
        try:
            yield
        except Exception:
            status = "error"
            raise
        finally:
            duration = time.perf_counter() - start_time
            # This would need custom metric registration for arbitrary names
            logger.debug(f"Tracked latency for {metric_name}: {duration:.4f}s", extra={
                "metric_name": metric_name,
                "duration_ms": duration * 1000,
                "status": status
            })
    
    def async_track_execution(
        self,
        agent_name: str,
        action: str
    ):
        """
        Decorator to track async function execution.
        
        Usage:
            @metrics.async_track_execution("whatsapp_agent", "send_message")
            async def send_message(...):
                ...
        """
        def decorator(func):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                start_time = time.perf_counter()
                status = "success"
                
                self.increment_agent_execution(agent_name, action)
                
                try:
                    result = await func(*args, **kwargs)
                    return result
                except Exception as e:
                    status = "error"
                    self.record_agent_error(agent_name, type(e).__name__)
                    raise
                finally:
                    duration = time.perf_counter() - start_time
                    self.record_agent_execution_duration(
                        agent_name, action, duration, status
                    )
            
            return wrapper
        return decorator


# Global instance
_metrics_collector: Optional[MetricsCollector] = None


def get_metrics_collector(config: Optional[MetricConfig] = None) -> MetricsCollector:
    """Get or create the global metrics collector instance."""
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = MetricsCollector(config)
    return _metrics_collector


def reset_metrics_collector() -> None:
    """Reset the global metrics collector (for testing)."""
    global _metrics_collector
    _metrics_collector = None
