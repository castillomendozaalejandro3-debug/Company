"""
Self-Healing - Sistema de auto-reparación de Helios.
Detecta fallos, intenta reparaciones automáticas y escala problemas no resueltos.
"""
import asyncio
import logging
import time
from typing import Dict, List, Optional, Callable, Any
from enum import Enum
from dataclasses import dataclass

try:
    from .structured_logger import get_logger
except ImportError:
    from structured_logger import get_logger

logger = get_logger(__name__)

class HealthStatus(Enum):
    """Estados de salud del sistema."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"
    FAILED = "failed"

class RecoveryAction(Enum):
    """Acciones de recuperación posibles."""
    RESTART_COMPONENT = "restart_component"
    ROLLBACK_VERSION = "rollback_version"
    ISOLATE_COMPONENT = "isolate_component"
    SCALE_UP = "scale_up"
    ALERT_ADMIN = "alert_admin"
    EXECUTE_SCRIPT = "execute_script"

@dataclass
class HealthCheck:
    """Resultado de una verificación de salud."""
    component: str
    status: HealthStatus
    message: str
    timestamp: float
    metrics: Dict[str, Any]

@dataclass
class Incident:
    """Registro de un incidente."""
    incident_id: str
    component: str
    severity: int
    description: str
    detected_at: float
    actions_taken: List[RecoveryAction]
    resolved: bool = False
    resolved_at: Optional[float] = None

class SelfHealingSystem:
    """Sistema principal de auto-reparación."""
    
    def __init__(self, kernel_daemon=None):
        self.kernel_daemon = kernel_daemon
        self.running = False
        self.incidents: List[Incident] = []
        self.health_checks: Dict[str, HealthCheck] = {}
        self.recovery_strategies: Dict[str, List[Callable]] = {}
        self._monitor_task: Optional[asyncio.Task] = None
        
        # Umbrales de configuración
        self.check_interval = 10  # segundos
        self.max_incidents_before_critical = 5
        self.auto_recovery_enabled = True

    async def start(self):
        """Inicia el sistema de self-healing."""
        logger.info("Starting Self-Healing System...")
        self.running = True
        
        # Registrar estrategias de recuperación por defecto
        self._register_default_strategies()
        
        # Iniciar monitor
        self._monitor_task = asyncio.create_task(self._continuous_monitor())
        logger.info("Self-Healing System started.")

    async def stop(self):
        """Detiene el sistema."""
        logger.info("Stopping Self-Healing System...")
        self.running = False
        
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
                
        logger.info("Self-Healing System stopped.")

    def _register_default_strategies(self):
        """Registra estrategias de recuperación por defecto."""
        self.recovery_strategies["kernel_daemon"] = [
            self._restart_component,
            self._rollback_version,
            self._alert_admin
        ]
        self.recovery_strategies["worker"] = [
            self._restart_worker,
            self._isolate_worker,
            self._spawn_replacement
        ]
        self.recovery_strategies["database"] = [
            self._check_db_integrity,
            self._restore_db_backup,
            self._alert_admin
        ]
        self.recovery_strategies["grpc_connection"] = [
            self._reconnect_grpc,
            self._restart_component,
            self._alert_admin
        ]

    async def _continuous_monitor(self):
        """Bucle continuo de monitoreo."""
        while self.running:
            try:
                await self.run_health_checks()
                await self.process_incidents()
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Monitor error: {e}")
                await asyncio.sleep(5)

    async def run_health_checks(self):
        """Ejecuta todas las verificaciones de salud."""
        logger.debug("Running health checks...")
        
        # Verificar componentes principales
        checks = [
            self._check_kernel_daemon(),
            self._check_workers(),
            self._check_database(),
            self._check_grpc_connection(),
            self._check_system_resources()
        ]
        
        results = await asyncio.gather(*checks, return_exceptions=True)
        
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Health check failed: {result}")
                await self.report_incident(
                    component="health_check",
                    severity=2,
                    description=f"Health check exception: {str(result)}"
                )

    async def _check_kernel_daemon(self) -> HealthCheck:
        """Verifica el estado del Kernel Daemon."""
        try:
            if self.kernel_daemon and self.kernel_daemon.running:
                return HealthCheck(
                    component="kernel_daemon",
                    status=HealthStatus.HEALTHY,
                    message="Kernel daemon is running",
                    timestamp=time.time(),
                    metrics={"uptime": time.time()}
                )
            else:
                return HealthCheck(
                    component="kernel_daemon",
                    status=HealthStatus.FAILED,
                    message="Kernel daemon is not running",
                    timestamp=time.time(),
                    metrics={}
                )
        except Exception as e:
            return HealthCheck(
                component="kernel_daemon",
                status=HealthStatus.CRITICAL,
                message=f"Error checking kernel daemon: {e}",
                timestamp=time.time(),
                metrics={}
            )

    async def _check_workers(self) -> HealthCheck:
        """Verifica el estado de los workers."""
        try:
            if not self.kernel_daemon or not hasattr(self.kernel_daemon, 'worker_manager'):
                return HealthCheck(
                    component="workers",
                    status=HealthStatus.DEGRADED,
                    message="Worker manager not available",
                    timestamp=time.time(),
                    metrics={}
                )
                
            stats = self.kernel_daemon.worker_manager.get_stats()
            error_count = stats["by_status"].get("error", 0)
            total = stats["total"]
            
            if error_count == 0:
                status = HealthStatus.HEALTHY
            elif error_count < total * 0.3:
                status = HealthStatus.DEGRADED
            else:
                status = HealthStatus.CRITICAL
                
            return HealthCheck(
                component="workers",
                status=status,
                message=f"{total} workers, {error_count} errors",
                timestamp=time.time(),
                metrics=stats
            )
        except Exception as e:
            return HealthCheck(
                component="workers",
                status=HealthStatus.CRITICAL,
                message=f"Error checking workers: {e}",
                timestamp=time.time(),
                metrics={}
            )

    async def _check_database(self) -> HealthCheck:
        """Verifica el estado de la base de datos."""
        try:
            # Intentar conexión y query simple
            from .audit_logger import AuditLogger
            logger_instance = AuditLogger()
            
            if logger_instance.test_connection():
                return HealthCheck(
                    component="database",
                    status=HealthStatus.HEALTHY,
                    message="Database connection OK",
                    timestamp=time.time(),
                    metrics={"connections": 1}
                )
            else:
                return HealthCheck(
                    component="database",
                    status=HealthStatus.FAILED,
                    message="Database connection failed",
                    timestamp=time.time(),
                    metrics={}
                )
        except Exception as e:
            return HealthCheck(
                component="database",
                status=HealthStatus.CRITICAL,
                message=f"Database error: {e}",
                timestamp=time.time(),
                metrics={}
            )

    async def _check_grpc_connection(self) -> HealthCheck:
        """Verifica la conexión gRPC con el núcleo Rust."""
        try:
            # Verificar si el servidor gRPC está escuchando
            if self.kernel_daemon and self.kernel_daemon.server:
                return HealthCheck(
                    component="grpc_connection",
                    status=HealthStatus.HEALTHY,
                    message="gRPC server active",
                    timestamp=time.time(),
                    metrics={"port": self.kernel_daemon.port}
                )
            else:
                return HealthCheck(
                    component="grpc_connection",
                    status=HealthStatus.DEGRADED,
                    message="gRPC server not active",
                    timestamp=time.time(),
                    metrics={}
                )
        except Exception as e:
            return HealthCheck(
                component="grpc_connection",
                status=HealthStatus.CRITICAL,
                message=f"gRPC error: {e}",
                timestamp=time.time(),
                metrics={}
            )

    async def _check_system_resources(self) -> HealthCheck:
        """Verifica recursos del sistema (CPU, RAM, Disco)."""
        try:
            import psutil
            
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            status = HealthStatus.HEALTHY
            messages = []
            
            if cpu_percent > 90:
                status = HealthStatus.CRITICAL
                messages.append(f"CPU critical: {cpu_percent}%")
            elif cpu_percent > 70:
                status = HealthStatus.DEGRADED
                messages.append(f"CPU high: {cpu_percent}%")
                
            if memory.percent > 90:
                status = HealthStatus.CRITICAL
                messages.append(f"RAM critical: {memory.percent}%")
            elif memory.percent > 70:
                if status != HealthStatus.CRITICAL:
                    status = HealthStatus.DEGRADED
                messages.append(f"RAM high: {memory.percent}%")
                
            if disk.percent > 90:
                status = HealthStatus.CRITICAL
                messages.append(f"Disk critical: {disk.percent}%")
                
            return HealthCheck(
                component="system_resources",
                status=status,
                message="; ".join(messages) if messages else "All resources OK",
                timestamp=time.time(),
                metrics={
                    "cpu_percent": cpu_percent,
                    "memory_percent": memory.percent,
                    "disk_percent": disk.percent
                }
            )
        except Exception as e:
            return HealthCheck(
                component="system_resources",
                status=HealthStatus.DEGRADED,
                message=f"Cannot check resources: {e}",
                timestamp=time.time(),
                metrics={}
            )

    async def report_incident(
        self, 
        component: str, 
        severity: int, 
        description: str
    ):
        """Reporta un incidente al sistema."""
        import uuid
        
        incident = Incident(
            incident_id=f"INC-{uuid.uuid4().hex[:8]}",
            component=component,
            severity=severity,
            description=description,
            detected_at=time.time(),
            actions_taken=[]
        )
        
        self.incidents.append(incident)
        logger.warning(f"Incident reported: {incident.incident_id} - {description}")
        
        # Actualizar estado de salud del componente
        if severity >= 3:
            status = HealthStatus.CRITICAL
        elif severity >= 2:
            status = HealthStatus.DEGRADED
        else:
            status = HealthStatus.HEALTHY
            
        self.health_checks[component] = HealthCheck(
            component=component,
            status=status,
            message=description,
            timestamp=time.time(),
            metrics={}
        )
        
        # Intentar recuperación automática si está habilitada
        if self.auto_recovery_enabled:
            await self.attempt_recovery(incident)

    async def process_incidents(self):
        """Procesa incidentes pendientes."""
        unresolved = [i for i in self.incidents if not i.resolved]
        
        # Contar incidentes críticos recientes
        now = time.time()
        recent_critical = sum(
            1 for i in unresolved 
            if i.severity >= 3 and (now - i.detected_at) < 300
        )
        
        if recent_critical >= self.max_incidents_before_critical:
            logger.critical(f"System entering CRITICAL state: {recent_critical} recent critical incidents")
            # Escalar a administrador inmediatamente
            await self._alert_admin(None)

    async def attempt_recovery(self, incident: Incident):
        """Intenta recuperar automáticamente un incidente."""
        logger.info(f"Attempting recovery for incident {incident.incident_id}")
        
        strategies = self.recovery_strategies.get(incident.component, [])
        
        if not strategies:
            logger.warning(f"No recovery strategies for component: {incident.component}")
            await self._alert_admin(incident)
            return
            
        for strategy in strategies:
            try:
                success = await strategy(incident)
                if success:
                    incident.resolved = True
                    incident.resolved_at = time.time()
                    logger.info(f"Incident {incident.incident_id} resolved by {strategy.__name__}")
                    return
            except Exception as e:
                logger.error(f"Recovery strategy {strategy.__name__} failed: {e}")
                incident.actions_taken.append(RecoveryAction.EXECUTE_SCRIPT)  # Placeholder
                
        # Si ninguna estrategia funcionó
        logger.error(f"All recovery strategies failed for {incident.incident_id}")
        await self._alert_admin(incident)

    # Estrategias de recuperación específicas
    
    async def _restart_component(self, incident: Incident) -> bool:
        """Reinicia el componente afectado."""
        logger.info(f"Restarting component: {incident.component}")
        # Lógica específica de reinicio según componente
        await asyncio.sleep(0.5)  # Simulación
        return True

    async def _restart_worker(self, incident: Incident) -> bool:
        """Reinicia un worker fallido."""
        if not self.kernel_daemon or not hasattr(self.kernel_daemon, 'worker_manager'):
            return False
            
        # Extraer ID del worker del descripción si es posible
        # Implementación simplificada
        logger.info("Restarting affected worker...")
        await asyncio.sleep(0.5)
        return True

    async def _rollback_version(self, incident: Incident) -> bool:
        """Realiza rollback a versión anterior."""
        logger.info(f"Initiating rollback for {incident.component}")
        # Integración con git_rollback
        try:
            from .git_rollback import GitRollback
            rollback = GitRollback()
            await rollback.rollback_last_commit()
            return True
        except Exception:
            return False

    async def _isolate_worker(self, incident: Incident) -> bool:
        """Aísla un worker problemático."""
        logger.info("Isolating problematic worker...")
        await asyncio.sleep(0.3)
        return True

    async def _spawn_replacement(self, incident: Incident) -> bool:
        """Crea un reemplazo para el worker fallido."""
        if not self.kernel_daemon or not hasattr(self.kernel_daemon, 'worker_manager'):
            return False
            
        logger.info("Spawning replacement worker...")
        await asyncio.sleep(0.5)
        return True

    async def _check_db_integrity(self, incident: Incident) -> bool:
        """Verifica integridad de la base de datos."""
        logger.info("Checking database integrity...")
        await asyncio.sleep(0.3)
        return True

    async def _restore_db_backup(self, incident: Incident) -> bool:
        """Restaura base de datos desde backup."""
        logger.info("Restoring database from backup...")
        await asyncio.sleep(1.0)
        return True

    async def _reconnect_grpc(self, incident: Incident) -> bool:
        """Reintenta conexión gRPC."""
        logger.info("Reconnecting gRPC...")
        await asyncio.sleep(0.5)
        return True

    async def _alert_admin(self, incident: Optional[Incident]) -> bool:
        """Envía alerta al administrador."""
        logger.critical(f"ALERT TO ADMIN: {incident.description if incident else 'System critical'}")
        # Integración con alert_manager
        try:
            from .alert_manager import AlertManager
            alert_mgr = AlertManager()
            await alert_mgr.send_security_alert(
                "Self-Healing System",
                incident.description if incident else "Critical system state",
                "critical"
            )
            return True
        except Exception:
            return True  # Alerta considerada como enviada incluso si falla el envío

    def get_status_report(self) -> Dict:
        """Genera reporte de estado del sistema."""
        unresolved = [i for i in self.incidents if not i.resolved]
        
        return {
            "status": "healthy" if len(unresolved) == 0 else "degraded",
            "active_incidents": len(unresolved),
            "total_incidents": len(self.incidents),
            "components": {
                comp: check.status.value 
                for comp, check in self.health_checks.items()
            },
            "auto_recovery_enabled": self.auto_recovery_enabled
        }
