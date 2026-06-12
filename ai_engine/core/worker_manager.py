"""
Worker Manager - Gestor de ciclo de vida de Workers.
Crea, monitorea y destruye workers según la demanda del sistema.
"""
import asyncio
import logging
import uuid
import os
from typing import Dict, List, Optional, Type
from enum import Enum

try:
    from .actor_system import ActorSystem, WorkerActor
    from .structured_logger import get_logger
except ImportError:
    from actor_system import ActorSystem, WorkerActor
    from structured_logger import get_logger

logger = get_logger(__name__)

class WorkerType(Enum):
    """Tipos de workers disponibles."""
    OFFICE = "office"
    EMAIL = "email"
    GUI = "gui"
    WEB = "web"
    API = "api"
    PENTEST = "pentest"
    VISUAL = "visual"

class WorkerStatus(Enum):
    """Estados del worker."""
    INITIALIZING = "initializing"
    IDLE = "idle"
    BUSY = "busy"
    SUSPENDED = "suspended"
    ERROR = "error"

class WorkerConfig:
    """Configuración de un worker."""
    def __init__(
        self,
        worker_type: WorkerType,
        max_memory_mb: int = 256,
        cpu_quota: float = 0.5,
        timeout_seconds: int = 300,
        auto_restart: bool = True
    ):
        self.worker_type = worker_type
        self.max_memory_mb = max_memory_mb
        self.cpu_quota = cpu_quota
        self.timeout_seconds = timeout_seconds
        self.auto_restart = auto_restart

class Worker:
    """Representación de un Worker en ejecución."""
    
    def __init__(self, worker_id: str, config: WorkerConfig, actor: WorkerActor):
        self.worker_id = worker_id
        self.config = config
        self.actor = actor
        self.status = WorkerStatus.INITIALIZING
        self.created_at = asyncio.get_event_loop().time()
        self.last_activity = self.created_at
        self.tasks_completed = 0
        
    async def initialize(self):
        """Inicializa el worker."""
        logger.info(f"Initializing worker {self.worker_id} ({self.config.worker_type.value})")
        # Simular inicialización
        await asyncio.sleep(0.1)
        self.status = WorkerStatus.IDLE
        logger.info(f"Worker {self.worker_id} ready.")
        
    async def execute(self, task: dict) -> dict:
        """Ejecuta una tarea en el worker."""
        if self.status != WorkerStatus.IDLE:
            raise RuntimeError(f"Worker {self.worker_id} is not idle (status: {self.status})")
            
        self.status = WorkerStatus.BUSY
        self.last_activity = asyncio.get_event_loop().time()
        
        try:
            # Enviar tarea al actor
            result = await self.actor.execute_task(task)
            self.tasks_completed += 1
            return result
        finally:
            self.status = WorkerStatus.IDLE
            self.last_activity = asyncio.get_event_loop().time()

class WorkerManager:
    """Gestor central de Workers."""
    
    def __init__(self, kernel_daemon=None):
        self.kernel_daemon = kernel_daemon
        self.workers: Dict[str, Worker] = {}
        self.actor_system: Optional[ActorSystem] = None
        self.running = False
        self._monitor_task: Optional[asyncio.Task] = None
        
        # Configuraciones por defecto por tipo
        self.default_configs: Dict[WorkerType, WorkerConfig] = {
            WorkerType.OFFICE: WorkerConfig(WorkerType.OFFICE, max_memory_mb=512),
            WorkerType.EMAIL: WorkerConfig(WorkerType.EMAIL, max_memory_mb=256),
            WorkerType.GUI: WorkerConfig(WorkerType.GUI, max_memory_mb=512, cpu_quota=0.8),
            WorkerType.WEB: WorkerConfig(WorkerType.WEB, max_memory_mb=384),
            WorkerType.API: WorkerConfig(WorkerType.API, max_memory_mb=256),
            WorkerType.PENTEST: WorkerConfig(WorkerType.PENTEST, max_memory_mb=1024, cpu_quota=1.0),
            WorkerType.VISUAL: WorkerConfig(WorkerType.VISUAL, max_memory_mb=768, cpu_quota=0.9),
        }

    async def initialize(self):
        """Inicializa el gestor de workers."""
        logger.info("Initializing WorkerManager...")
        self.running = True
        
        if self.kernel_daemon and hasattr(self.kernel_daemon, 'actor_system'):
            self.actor_system = self.kernel_daemon.actor_system
            
        # Iniciar monitor de salud
        self._monitor_task = asyncio.create_task(self._health_monitor())
        logger.info("WorkerManager initialized.")

    async def shutdown(self):
        """Detiene todos los workers."""
        logger.info("Shutting down WorkerManager...")
        self.running = False
        
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        
        # Detener todos los workers
        tasks = [self.destroy_worker(wid) for wid in list(self.workers.keys())]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
            
        self.workers.clear()
        logger.info("WorkerManager shutdown complete.")

    async def spawn_worker(
        self, 
        worker_type: WorkerType, 
        config: Optional[WorkerConfig] = None
    ) -> str:
        """Crea un nuevo worker."""
        if config is None:
            config = self.default_configs.get(worker_type, WorkerConfig(worker_type))
            
        worker_id = f"{worker_type.value}-{uuid.uuid4().hex[:8]}"
        
        if not self.actor_system:
            raise RuntimeError("Actor system not initialized")
            
        # Crear actor para el worker
        actor_id = await self.actor_system.spawn(
            WorkerActor,
            actor_id=f"worker-{worker_id}",
            worker_type=worker_type.value
        )
        
        actor = self.actor_system.actors[actor_id]
        worker = Worker(worker_id, config, actor)
        
        self.workers[worker_id] = worker
        await worker.initialize()
        
        logger.info(f"Spawned worker {worker_id} of type {worker_type.value}")
        return worker_id

    async def destroy_worker(self, worker_id: str):
        """Destruye un worker."""
        if worker_id not in self.workers:
            logger.warning(f"Worker {worker_id} not found.")
            return
            
        worker = self.workers[worker_id]
        logger.info(f"Destroying worker {worker_id}...")
        
        # Detener actor
        await worker.actor.stop()
        
        # Eliminar del registro
        del self.workers[worker_id]
        if self.actor_system:
            await self.actor_system.unregister_actor(worker.actor.actor_id)
            
        logger.info(f"Worker {worker_id} destroyed.")

    async def get_worker(self, worker_id: str) -> Optional[Worker]:
        """Obtiene un worker por ID."""
        return self.workers.get(worker_id)

    async def get_idle_worker(self, worker_type: Optional[WorkerType] = None) -> Optional[Worker]:
        """Obtiene un worker idle disponible."""
        for worker in self.workers.values():
            if worker.status == WorkerStatus.IDLE:
                if worker_type is None or worker.config.worker_type == worker_type:
                    return worker
        return None

    async def _health_monitor(self):
        """Monitor de salud de workers en segundo plano."""
        logger.info("Worker health monitor started.")
        
        while self.running:
            try:
                await asyncio.sleep(5)  # Verificar cada 5 segundos
                
                for worker_id, worker in list(self.workers.items()):
                    # Verificar timeout
                    elapsed = asyncio.get_event_loop().time() - worker.last_activity
                    if elapsed > worker.config.timeout_seconds and worker.status == WorkerStatus.BUSY:
                        logger.error(f"Worker {worker_id} timed out after {elapsed}s")
                        # Manejar timeout (reiniciar o destruir)
                        if worker.config.auto_restart:
                            await self.restart_worker(worker_id)
                            
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health monitor error: {e}")

    async def restart_worker(self, worker_id: str):
        """Reinicia un worker."""
        if worker_id not in self.workers:
            return
            
        worker = self.workers[worker_id]
        worker_type = worker.config.worker_type
        
        logger.info(f"Restarting worker {worker_id}...")
        await self.destroy_worker(worker_id)
        
        # Crear nuevo worker del mismo tipo
        new_id = await self.spawn_worker(worker_type, worker.config)
        logger.info(f"Worker {worker_id} restarted as {new_id}")
        return new_id

    @property
    def active_workers(self) -> List[Worker]:
        """Lista de workers activos."""
        return [w for w in self.workers.values() if w.status != WorkerStatus.ERROR]

    def get_stats(self) -> dict:
        """Obtiene estadísticas de workers."""
        stats = {
            "total": len(self.workers),
            "by_status": {},
            "by_type": {}
        }
        
        for status in WorkerStatus:
            stats["by_status"][status.value] = sum(
                1 for w in self.workers.values() if w.status == status
            )
            
        for wtype in WorkerType:
            stats["by_type"][wtype.value] = sum(
                1 for w in self.workers.values() if w.config.worker_type == wtype
            )
            
        return stats
