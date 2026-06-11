"""
Helios AI Engine - Alert Manager
Enterprise-grade alerting system with deduplication and multi-channel support.

Author: Helios Architecture Team
Version: 2.0.0
"""

import asyncio
import hashlib
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any, Callable, Awaitable
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict
import threading
import json

from ai_engine.core.structured_logger import get_logger

logger = get_logger(__name__)


class AlertSeverity(str, Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    SECURITY = "security"


class AlertStatus(str, Enum):
    """Alert status states."""
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    SUPPRESSED = "suppressed"


class AlertChannel(str, Enum):
    """Supported alert notification channels."""
    TELEGRAM = "telegram"
    EMAIL = "email"
    WEBHOOK = "webhook"
    SLACK = "slack"
    PAGERDUTY = "pagerduty"


@dataclass
class AlertThreshold:
    """Configuration for alert thresholds."""
    
    metric_name: str
    threshold_value: float
    comparison: str  # "gt", "lt", "gte", "lte", "eq"
    severity: AlertSeverity
    cooldown_seconds: int = 300  # 5 minutes default
    description: str = ""


@dataclass
class Alert:
    """Alert data structure."""
    
    id: str
    name: str
    severity: AlertSeverity
    status: AlertStatus = AlertStatus.ACTIVE
    message: str = ""
    metric_name: Optional[str] = None
    metric_value: Optional[float] = None
    threshold_value: Optional[float] = None
    source: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    acknowledged_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    acknowledged_by: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    fingerprint: str = ""
    occurrence_count: int = 1
    first_occurrence: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_occurrence: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def __post_init__(self):
        if not self.fingerprint:
            self.fingerprint = self._generate_fingerprint()
    
    def _generate_fingerprint(self) -> str:
        """Generate unique fingerprint for deduplication."""
        content = f"{self.name}:{self.severity}:{self.source}:{self.metric_name}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert alert to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "severity": self.severity.value,
            "status": self.status.value,
            "message": self.message,
            "metric_name": self.metric_name,
            "metric_value": self.metric_value,
            "threshold_value": self.threshold_value,
            "source": self.source,
            "timestamp": self.timestamp.isoformat(),
            "acknowledged_at": self.acknowledged_at.isoformat() if self.acknowledged_at else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "acknowledged_by": self.acknowledged_by,
            "details": self.details,
            "tags": self.tags,
            "fingerprint": self.fingerprint,
            "occurrence_count": self.occurrence_count,
            "first_occurrence": self.first_occurrence.isoformat(),
            "last_occurrence": self.last_occurrence.isoformat(),
        }


@dataclass
class AlertConfig:
    """Alert manager configuration."""
    
    # Cooldown settings
    default_cooldown_seconds: int = 300
    security_alert_cooldown_seconds: int = 60
    
    # Deduplication settings
    enable_deduplication: bool = True
    deduplication_window_seconds: int = 600
    
    # Rate limiting
    max_alerts_per_minute: int = 10
    max_alerts_per_hour: int = 100
    
    # Channel settings
    enabled_channels: List[AlertChannel] = field(default_factory=list)
    
    # Telegram settings
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    
    # Email settings
    smtp_host: Optional[str] = None
    smtp_port: int = 587
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    email_recipients: List[str] = field(default_factory=list)
    
    # Webhook settings
    webhook_url: Optional[str] = None
    webhook_headers: Dict[str, str] = field(default_factory=dict)
    
    # Thresholds
    thresholds: List[AlertThreshold] = field(default_factory=list)


class AlertManager:
    """
    Enterprise alert manager with deduplication and multi-channel support.
    
    Features:
    - Alert deduplication to prevent spam
    - Configurable cooldown periods
    - Multi-channel notifications (Telegram, Email, Webhook)
    - Severity-based routing
    - Alert acknowledgment and resolution
    - Rate limiting
    - Thread-safe operation
    """
    
    _instance: Optional["AlertManager"] = None
    _lock = threading.Lock()
    
    def __new__(cls, config: Optional[AlertConfig] = None) -> "AlertManager":
        """Singleton pattern for alert manager."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, config: Optional[AlertConfig] = None):
        """Initialize alert manager."""
        if self._initialized:
            return
        
        self.config = config or AlertConfig()
        
        # Alert storage
        self._alerts: Dict[str, Alert] = {}
        self._alert_history: List[Alert] = []
        
        # Deduplication tracking
        self._fingerprint_last_sent: Dict[str, float] = {}
        self._fingerprint_occurrences: Dict[str, int] = defaultdict(int)
        
        # Rate limiting
        self._alerts_last_minute: List[float] = []
        self._alerts_last_hour: List[float] = []
        
        # Notification handlers
        self._notification_handlers: Dict[AlertChannel, Callable[[Alert], Awaitable[bool]]] = {}
        
        # Register default handlers
        self._register_default_handlers()
        
        # Background tasks
        self._cleanup_task: Optional[asyncio.Task] = None
        
        self._initialized = True
        
        logger.info("AlertManager initialized", extra={
            "enabled_channels": [c.value for c in self.config.enabled_channels],
            "deduplication_enabled": self.config.enable_deduplication
        })
    
    def _register_default_handlers(self) -> None:
        """Register default notification handlers."""
        self._notification_handlers[AlertChannel.TELEGRAM] = self._send_telegram
        self._notification_handlers[AlertChannel.EMAIL] = self._send_email
        self._notification_handlers[AlertChannel.WEBHOOK] = self._send_webhook
        self._notification_handlers[AlertChannel.SLACK] = self._send_slack
        self._notification_handlers[AlertChannel.PAGERDUTY] = self._send_pagerduty
    
    # =========================================================================
    # Alert Creation and Management
    # =========================================================================
    
    async def create_alert(
        self,
        name: str,
        severity: AlertSeverity,
        message: str,
        source: str = "helios",
        metric_name: Optional[str] = None,
        metric_value: Optional[float] = None,
        threshold_value: Optional[float] = None,
        details: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None
    ) -> Optional[Alert]:
        """
        Create and potentially send an alert.
        
        Args:
            name: Alert name
            severity: Alert severity level
            message: Alert message
            source: Alert source identifier
            metric_name: Optional associated metric name
            metric_value: Optional current metric value
            threshold_value: Optional threshold that was exceeded
            details: Additional alert details
            tags: Tags for categorization
        
        Returns:
            Alert object if sent, None if suppressed/deduplicated
        """
        # Check rate limits
        if not self._check_rate_limit():
            logger.warning("Alert rate limit exceeded, suppressing alert", extra={
                "alert_name": name,
                "severity": severity.value
            })
            return None
        
        # Create alert object
        alert = Alert(
            id=self._generate_alert_id(),
            name=name,
            severity=severity,
            message=message,
            source=source,
            metric_name=metric_name,
            metric_value=metric_value,
            threshold_value=threshold_value,
            details=details or {},
            tags=tags or []
        )
        
        # Check deduplication
        if self.config.enable_deduplication:
            if not self._should_send_alert(alert):
                # Update existing alert occurrence
                self._update_occurrence(alert.fingerprint)
                logger.debug("Alert deduplicated", extra={
                    "alert_name": name,
                    "fingerprint": alert.fingerprint
                })
                return None
        
        # Determine cooldown based on severity
        cooldown = self._get_cooldown_for_severity(severity)
        
        # Check cooldown
        if not self._check_cooldown(alert.fingerprint, cooldown):
            logger.debug("Alert in cooldown period", extra={
                "alert_name": name,
                "cooldown_seconds": cooldown
            })
            return None
        
        # Store alert
        self._alerts[alert.id] = alert
        self._alert_history.append(alert)
        
        # Update tracking
        self._fingerprint_last_sent[alert.fingerprint] = time.time()
        self._fingerprint_occurrences[alert.fingerprint] = 1
        
        # Send notifications
        await self._send_notifications(alert)
        
        logger.warning(f"Alert created: {name}", extra={
            "alert_id": alert.id,
            "severity": severity.value,
            "source": source
        })
        
        return alert
    
    def acknowledge_alert(
        self,
        alert_id: str,
        acknowledged_by: str
    ) -> bool:
        """
        Acknowledge an active alert.
        
        Args:
            alert_id: Alert ID to acknowledge
            acknowledged_by: User/system acknowledging the alert
        
        Returns:
            True if successfully acknowledged
        """
        if alert_id not in self._alerts:
            logger.warning(f"Alert {alert_id} not found for acknowledgment")
            return False
        
        alert = self._alerts[alert_id]
        if alert.status != AlertStatus.ACTIVE:
            logger.warning(f"Alert {alert_id} is not active", extra={
                "current_status": alert.status.value
            })
            return False
        
        alert.status = AlertStatus.ACKNOWLEDGED
        alert.acknowledged_at = datetime.now(timezone.utc)
        alert.acknowledged_by = acknowledged_by
        
        logger.info(f"Alert acknowledged: {alert.name}", extra={
            "alert_id": alert_id,
            "acknowledged_by": acknowledged_by
        })
        
        return True
    
    def resolve_alert(
        self,
        alert_id: str,
        resolution_message: Optional[str] = None
    ) -> bool:
        """
        Resolve an alert.
        
        Args:
            alert_id: Alert ID to resolve
            resolution_message: Optional resolution notes
        
        Returns:
            True if successfully resolved
        """
        if alert_id not in self._alerts:
            logger.warning(f"Alert {alert_id} not found for resolution")
            return False
        
        alert = self._alerts[alert_id]
        alert.status = AlertStatus.RESOLVED
        alert.resolved_at = datetime.now(timezone.utc)
        
        if resolution_message:
            alert.details["resolution_message"] = resolution_message
        
        logger.info(f"Alert resolved: {alert.name}", extra={
            "alert_id": alert_id
        })
        
        return True
    
    def get_active_alerts(
        self,
        severity: Optional[AlertSeverity] = None,
        source: Optional[str] = None
    ) -> List[Alert]:
        """
        Get all active alerts, optionally filtered.
        
        Args:
            severity: Filter by severity level
            source: Filter by source
        
        Returns:
            List of active alerts
        """
        alerts = [
            a for a in self._alerts.values()
            if a.status == AlertStatus.ACTIVE
        ]
        
        if severity:
            alerts = [a for a in alerts if a.severity == severity]
        
        if source:
            alerts = [a for a in alerts if a.source == source]
        
        return sorted(alerts, key=lambda x: x.timestamp, reverse=True)
    
    def get_alert_statistics(self) -> Dict[str, Any]:
        """Get alert statistics."""
        now = time.time()
        
        # Count by severity
        severity_counts = defaultdict(int)
        status_counts = defaultdict(int)
        
        for alert in self._alerts.values():
            severity_counts[alert.severity.value] += 1
            status_counts[alert.status.value] += 1
        
        return {
            "total_alerts": len(self._alerts),
            "active_alerts": status_counts.get(AlertStatus.ACTIVE.value, 0),
            "acknowledged_alerts": status_counts.get(AlertStatus.ACKNOWLEDGED.value, 0),
            "resolved_alerts": status_counts.get(AlertStatus.RESOLVED.value, 0),
            "by_severity": dict(severity_counts),
            "alerts_last_minute": len([
                t for t in self._alerts_last_minute
                if now - t < 60
            ]),
            "alerts_last_hour": len([
                t for t in self._alerts_last_hour
                if now - t < 3600
            ]),
            "unique_fingerprints_tracked": len(self._fingerprint_last_sent)
        }
    
    # =========================================================================
    # Threshold-Based Alerting
    # =========================================================================
    
    async def check_threshold(
        self,
        metric_name: str,
        metric_value: float
    ) -> List[Alert]:
        """
        Check metric against configured thresholds and create alerts if exceeded.
        
        Args:
            metric_name: Name of the metric
            metric_value: Current metric value
        
        Returns:
            List of alerts created (if any)
        """
        alerts_created = []
        
        for threshold in self.config.thresholds:
            if threshold.metric_name != metric_name:
                continue
            
            # Check if threshold is exceeded
            exceeded = self._compare_value(
                metric_value,
                threshold.threshold_value,
                threshold.comparison
            )
            
            if exceeded:
                alert = await self.create_alert(
                    name=f"Threshold Exceeded: {metric_name}",
                    severity=threshold.severity,
                    message=f"{metric_name} value {metric_value} {self._comparison_to_text(threshold.comparison)} {threshold.threshold_value}. {threshold.description}",
                    source="threshold_monitor",
                    metric_name=metric_name,
                    metric_value=metric_value,
                    threshold_value=threshold.threshold_value,
                    tags=["threshold", "automated"]
                )
                
                if alert:
                    alerts_created.append(alert)
        
        return alerts_created
    
    def _compare_value(
        self,
        value: float,
        threshold: float,
        comparison: str
    ) -> bool:
        """Compare value against threshold."""
        ops = {
            "gt": lambda v, t: v > t,
            "lt": lambda v, t: v < t,
            "gte": lambda v, t: v >= t,
            "lte": lambda v, t: v <= t,
            "eq": lambda v, t: v == t,
        }
        return ops.get(comparison, lambda v, t: False)(value, threshold)
    
    def _comparison_to_text(self, comparison: str) -> str:
        """Convert comparison operator to text."""
        texts = {
            "gt": "exceeds",
            "lt": "is below",
            "gte": "meets or exceeds",
            "lte": "is at or below",
            "eq": "equals"
        }
        return texts.get(comparison, "compared to")
    
    # =========================================================================
    # Notification Methods
    # =========================================================================
    
    async def _send_notifications(self, alert: Alert) -> None:
        """Send alert through all enabled channels."""
        tasks = []
        
        for channel in self.config.enabled_channels:
            if channel in self._notification_handlers:
                handler = self._notification_handlers[channel]
                tasks.append(handler(alert))
        
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for channel, result in zip(self.config.enabled_channels, results):
                if isinstance(result, Exception):
                    logger.error(f"Failed to send alert via {channel.value}", extra={
                        "alert_id": alert.id,
                        "error": str(result)
                    })
                elif result:
                    logger.debug(f"Alert sent via {channel.value}", extra={
                        "alert_id": alert.id
                    })
    
    async def _send_telegram(self, alert: Alert) -> bool:
        """Send alert via Telegram."""
        if not self.config.telegram_bot_token or not self.config.telegram_chat_id:
            logger.debug("Telegram not configured, skipping")
            return False
        
        try:
            import aiohttp
            
            url = f"https://api.telegram.org/bot{self.config.telegram_bot_token}/sendMessage"
            
            # Format message with emoji based on severity
            emoji = {
                AlertSeverity.INFO: "ℹ️",
                AlertSeverity.WARNING: "⚠️",
                AlertSeverity.CRITICAL: "🚨",
                AlertSeverity.SECURITY: "🔒"
            }.get(alert.severity, "📢")
            
            message = f"""
{emoji} *{alert.name}*

{alert.message}

*Severity:* {alert.severity.value.upper()}
*Source:* {alert.source}
*Time:* {alert.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}
"""
            
            if alert.metric_name:
                message += f"\n*Metric:* {alert.metric_name} = {alert.metric_value}"
            
            payload = {
                "chat_id": self.config.telegram_chat_id,
                "text": message,
                "parse_mode": "Markdown"
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=10) as response:
                    if response.status == 200:
                        return True
                    logger.error(f"Telegram API error: {response.status}")
                    return False
                    
        except Exception as e:
            logger.error(f"Failed to send Telegram alert: {e}", exc_info=True)
            return False
    
    async def _send_email(self, alert: Alert) -> bool:
        """Send alert via email."""
        if not self.config.smtp_host or not self.config.email_recipients:
            logger.debug("Email not configured, skipping")
            return False
        
        try:
            import aiosmtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
            
            msg = MIMEMultipart()
            msg['From'] = self.config.smtp_user
            msg['To'] = ', '.join(self.config.email_recipients)
            msg['Subject'] = f"[{alert.severity.value.upper()}] {alert.name}"
            
            body = f"""
Alert: {alert.name}
Severity: {alert.severity.value.upper()}
Source: {alert.source}
Time: {alert.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}

{alert.message}
"""
            
            if alert.metric_name:
                body += f"\nMetric: {alert.metric_name} = {alert.metric_value}"
            
            msg.attach(MIMEText(body, 'plain'))
            
            await aiosmtplib.send(
                msg,
                hostname=self.config.smtp_host,
                port=self.config.smtp_port,
                username=self.config.smtp_user,
                password=self.config.smtp_password,
                start_tls=True
            )
            
            return True
            
        except ImportError:
            logger.warning("aiosmtplib not installed, email alerts disabled")
            return False
        except Exception as e:
            logger.error(f"Failed to send email alert: {e}", exc_info=True)
            return False
    
    async def _send_webhook(self, alert: Alert) -> bool:
        """Send alert via webhook."""
        if not self.config.webhook_url:
            logger.debug("Webhook not configured, skipping")
            return False
        
        try:
            import aiohttp
            
            payload = alert.to_dict()
            
            headers = {"Content-Type": "application/json"}
            headers.update(self.config.webhook_headers)
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.config.webhook_url,
                    json=payload,
                    headers=headers,
                    timeout=10
                ) as response:
                    return 200 <= response.status < 300
                    
        except Exception as e:
            logger.error(f"Failed to send webhook alert: {e}", exc_info=True)
            return False
    
    async def _send_slack(self, alert: Alert) -> bool:
        """Send alert to Slack (via webhook)."""
        # Slack uses webhook format
        if not self.config.webhook_url:
            logger.debug("Slack webhook not configured, skipping")
            return False
        
        try:
            import aiohttp
            
            color = {
                AlertSeverity.INFO: "#36a64f",
                AlertSeverity.WARNING: "#ff9800",
                AlertSeverity.CRITICAL: "#ff0000",
                AlertSeverity.SECURITY: "#9c27b0"
            }.get(alert.severity, "#808080")
            
            payload = {
                "attachments": [{
                    "color": color,
                    "title": alert.name,
                    "text": alert.message,
                    "fields": [
                        {"title": "Severity", "value": alert.severity.value.upper(), "short": True},
                        {"title": "Source", "value": alert.source, "short": True},
                    ],
                    "ts": int(alert.timestamp.timestamp())
                }]
            }
            
            if alert.metric_name:
                payload["attachments"][0]["fields"].append({
                    "title": "Metric",
                    "value": f"{alert.metric_name} = {alert.metric_value}",
                    "short": False
                })
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.config.webhook_url,
                    json=payload,
                    timeout=10
                ) as response:
                    return 200 <= response.status < 300
                    
        except Exception as e:
            logger.error(f"Failed to send Slack alert: {e}", exc_info=True)
            return False
    
    async def _send_pagerduty(self, alert: Alert) -> bool:
        """Send alert to PagerDuty."""
        # Requires PagerDuty integration key
        pd_key = self.config.webhook_headers.get("X-PagerDuty-Integration-Key")
        if not pd_key:
            logger.debug("PagerDuty not configured, skipping")
            return False
        
        try:
            import aiohttp
            
            event_type = {
                AlertSeverity.INFO: "info",
                AlertSeverity.WARNING: "warning",
                AlertSeverity.CRITICAL: "critical",
                AlertSeverity.SECURITY: "critical"
            }.get(alert.severity, "info")
            
            payload = {
                "routing_key": pd_key,
                "event_action": "trigger",
                "payload": {
                    "summary": alert.name,
                    "severity": event_type,
                    "source": alert.source,
                    "component": "helios_ai_engine",
                    "custom_details": alert.to_dict()
                }
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://events.pagerduty.com/v2/enqueue",
                    json=payload,
                    timeout=10
                ) as response:
                    return 200 <= response.status < 300
                    
        except Exception as e:
            logger.error(f"Failed to send PagerDuty alert: {e}", exc_info=True)
            return False
    
    # =========================================================================
    # Utility Methods
    # =========================================================================
    
    def _generate_alert_id(self) -> str:
        """Generate unique alert ID."""
        import uuid
        return f"alert_{uuid.uuid4().hex[:12]}"
    
    def _should_send_alert(self, alert: Alert) -> bool:
        """Check if alert should be sent (deduplication check)."""
        now = time.time()
        fingerprint = alert.fingerprint
        
        if fingerprint not in self._fingerprint_last_sent:
            return True
        
        last_sent = self._fingerprint_last_sent[fingerprint]
        window = self.config.deduplication_window_seconds
        
        # If within deduplication window, don't send new alert
        return (now - last_sent) > window
    
    def _update_occurrence(self, fingerprint: str) -> None:
        """Update occurrence count for deduplicated alert."""
        self._fingerprint_occurrences[fingerprint] += 1
        
        # Update existing alert if present
        for alert in self._alerts.values():
            if alert.fingerprint == fingerprint and alert.status == AlertStatus.ACTIVE:
                alert.occurrence_count = self._fingerprint_occurrences[fingerprint]
                alert.last_occurrence = datetime.now(timezone.utc)
                break
    
    def _check_cooldown(self, fingerprint: str, cooldown_seconds: int) -> bool:
        """Check if alert fingerprint is in cooldown period."""
        if fingerprint not in self._fingerprint_last_sent:
            return True
        
        last_sent = self._fingerprint_last_sent[fingerprint]
        return (time.time() - last_sent) >= cooldown_seconds
    
    def _get_cooldown_for_severity(self, severity: AlertSeverity) -> int:
        """Get cooldown period based on severity."""
        if severity == AlertSeverity.SECURITY:
            return self.config.security_alert_cooldown_seconds
        return self.config.default_cooldown_seconds
    
    def _check_rate_limit(self) -> bool:
        """Check if alert rate limits are exceeded."""
        now = time.time()
        
        # Clean old entries
        self._alerts_last_minute = [t for t in self._alerts_last_minute if now - t < 60]
        self._alerts_last_hour = [t for t in self._alerts_last_hour if now - t < 3600]
        
        # Check limits
        if len(self._alerts_last_minute) >= self.config.max_alerts_per_minute:
            return False
        
        if len(self._alerts_last_hour) >= self.config.max_alerts_per_hour:
            return False
        
        # Record this alert
        self._alerts_last_minute.append(now)
        self._alerts_last_hour.append(now)
        
        return True
    
    async def start_cleanup_task(self, interval_seconds: int = 300) -> None:
        """Start background task to clean up old alerts."""
        async def cleanup_loop():
            while True:
                await asyncio.sleep(interval_seconds)
                self._cleanup_old_alerts()
        
        self._cleanup_task = asyncio.create_task(cleanup_loop())
        logger.info("Alert cleanup task started", extra={
            "interval_seconds": interval_seconds
        })
    
    def _cleanup_old_alerts(self, max_age_hours: int = 24) -> None:
        """Clean up old resolved alerts."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        
        to_remove = [
            alert_id for alert_id, alert in self._alerts.items()
            if alert.status == AlertStatus.RESOLVED and alert.resolved_at < cutoff
        ]
        
        for alert_id in to_remove:
            del self._alerts[alert_id]
        
        if to_remove:
            logger.info(f"Cleaned up {len(to_remove)} old resolved alerts")
    
    def stop(self) -> None:
        """Stop the alert manager and cleanup tasks."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
        
        logger.info("AlertManager stopped")


# Global instance
_alert_manager: Optional[AlertManager] = None


def get_alert_manager(config: Optional[AlertConfig] = None) -> AlertManager:
    """Get or create the global alert manager instance."""
    global _alert_manager
    if _alert_manager is None:
        _alert_manager = AlertManager(config)
    return _alert_manager


def reset_alert_manager() -> None:
    """Reset the global alert manager (for testing)."""
    global _alert_manager
    _alert_manager = None


# Predefined threshold configurations
DEFAULT_THRESHOLDS = [
    AlertThreshold(
        metric_name="llm_response_latency_seconds",
        threshold_value=5.0,
        comparison="gt",
        severity=AlertSeverity.WARNING,
        cooldown_seconds=120,
        description="LLM response latency exceeds 5 seconds"
    ),
    AlertThreshold(
        metric_name="agent_error_rate",
        threshold_value=0.10,
        comparison="gt",
        severity=AlertSeverity.CRITICAL,
        cooldown_seconds=300,
        description="Agent error rate exceeds 10%"
    ),
    AlertThreshold(
        metric_name="path_traversal_attempts",
        threshold_value=5.0,
        comparison="gt",
        severity=AlertSeverity.SECURITY,
        cooldown_seconds=60,
        description="More than 5 path traversal attempts per minute"
    ),
]
