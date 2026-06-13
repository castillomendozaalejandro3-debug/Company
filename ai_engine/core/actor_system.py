"""
Actor System - Sistema de Actores estilo Erlang/OTP para Helios.
Gestiona la concurrencia, el aislamiento de fallos y el mensaje entre workers.
"""
import asyncio
import logging
import uuid
from typing import Dict, Any, Optional, Callable, List
from dataclasses import dataclass
from enum import Enum

try:
    from .structured_logger import get_logger
except ImportError:
    from structured_logger import get_logger

logger = get_logger(__name__)

class ActorStatus(Enum):
    """Estados posibles de un actor."""
    RUNNING = "running"
    SUSPENDED = "suspended"
    STOPPED = "stopped"
    FAILED = "failed"

@dataclass
class Message:
    """Mensaje enviado entre actores."""
    message_id: str
    sender_id: str
    recipient_id: str
    command: str
    payload: Any
    timestamp: float
    priority: int = 0

class Actor:
    """Clase base para todos los actores del sistema."""
    
    def __init__(self, actor_id: str, actor_system):
        self.actor_id = actor_id
        self.actor_system = actor_system
        self.status = ActorStatus.RUNNING
        self.mailbox: asyncio.Queue = asyncio.Queue()
        self.children: List[str] = []
        self.supervisor: Optional[str] = None
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        """Inicia el bucle de procesamiento del actor."""
        logger.info(f"Actor {self.actor_id} starting...")
        self._task = asyncio.create_task(self._run())
        
    async def _run(self):
        """Bucle principal de procesamiento de mensajes."""
        while self.status == ActorStatus.RUNNING:
            try:
                # Esperar mensaje con timeout para verificar estado
                try:
                    message = await asyncio.wait_for(self.mailbox.get(), timeout=1.0)
                    await self.handle_message(message)
                except asyncio.TimeoutError:
                    continue
            except Exception as e:
                logger.error(f"Actor {self.actor_id} error: {e}")
                await self.handle_failure(e)
                
    async def handle_message(self, message: Message):
        """Procesa un mensaje recibido. Sobrescribir en subclases."""
        logger.warning(f"Actor {self.actor_id} received unhandled message: {message.command}")
        
    async def handle_failure(self, error: Exception):
        """Maneja fallos del actor. Implementa estrategia de supervisión."""
        logger.error(f"Actor {self.actor_id} failed: {error}")
        self.status = ActorStatus.FAILED
        
        # Notificar al supervisor
        if self.supervisor:
            await self.actor_system.tell(
                self.supervisor,
                Message(
                    message_id=str(uuid.uuid4()),
                    sender_id=self.actor_id,
                    recipient_id=self.supervisor,
                    command="CHILD_FAILED",
                    payload={"error": str(error), "child_id": self.actor_id},
                    timestamp=asyncio.get_event_loop().time()
                )
            )

    async def stop(self):
        """Detiene el actor gracefulmente."""
        logger.info(f"Stopping actor {self.actor_id}")
        self.status = ActorStatus.STOPPED
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def tell(self, message: Message):
        """Envía un mensaje asíncrono (fire-and-forget)."""
        await self.mailbox.put(message)

class WorkerActor(Actor):
    """Actor especializado para Workers."""
    
    def __init__(self, actor_id: str, actor_system, worker_type: str):
        super().__init__(actor_id, actor_system)
        self.worker_type = worker_type
        self.capabilities: List[str] = []
        
    async def handle_message(self, message: Message):
        """Procesa comandos específicos del worker."""
        logger.debug(f"WorkerActor {self.actor_id} processing: {message.command}")
        
        if message.command == "EXECUTE":
            # Ejecutar tarea asignada
            result = await self.execute_task(message.payload)
            # Responder al remitente
            response = Message(
                message_id=str(uuid.uuid4()),
                sender_id=self.actor_id,
                recipient_id=message.sender_id,
                command="RESULT",
                payload=result,
                timestamp=asyncio.get_event_loop().time()
            )
            await self.actor_system.tell(message.sender_id, response)
            
        elif message.command == "SUSPEND":
            self.status = ActorStatus.SUSPENDED
            logger.info(f"WorkerActor {self.actor_id} suspended")
            
        elif message.command == "RESUME":
            self.status = ActorStatus.RUNNING
            logger.info(f"WorkerActor {self.actor_id} resumed")

    async def execute_task(self, task_data: Dict) -> Any:
        """Ejecuta una tarea específica. Sobrescribir según tipo de worker."""
        logger.info(f"Executing task on {self.worker_type}: {task_data}")
        # Simulación de ejecución - sobrescribir en implementación real
        await asyncio.sleep(0.1)
        return {"status": "completed", "worker_type": self.worker_type}

class SupervisorActor(Actor):
    """Actor supervisor que gestiona hijos y aplica estrategias de recuperación."""
    
    def __init__(self, actor_id: str, actor_system):
        super().__init__(actor_id, actor_system)
        self.restart_count: Dict[str, int] = {}
        self.max_restarts = 3
        
    async def handle_message(self, message: Message):
        """Maneja mensajes de supervisión."""
        if message.command == "CHILD_FAILED":
            child_id = message.payload.get("child_id")
            error = message.payload.get("error")
            
            logger.warning(f"Supervisor {self.actor_id} detected failure in {child_id}: {error}")
            
            # Estrategia de reinicio
            count = self.restart_count.get(child_id, 0)
            if count < self.max_restarts:
                self.restart_count[child_id] = count + 1
                logger.info(f"Restarting {child_id} (attempt {count + 1}/{self.max_restarts})")
                await self.actor_system.restart_actor(child_id)
            else:
                logger.error(f"Max restarts reached for {child_id}. Escalating...")
                # Escalar al supervisor padre o tomar acción correctiva
                if self.supervisor:
                    await self.actor_system.tell(
                        self.supervisor,
                        Message(
                            message_id=str(uuid.uuid4()),
                            sender_id=self.actor_id,
                            recipient_id=self.supervisor,
                            command="ESCALATION",
                            payload={"failed_child": child_id, "reason": "max_restarts"},
                            timestamp=asyncio.get_event_loop().time()
                        )
                    )

class ActorSystem:
    """Sistema de Actores central."""
    
    def __init__(self, kernel_daemon=None):
        self.kernel_daemon = kernel_daemon
        self.actors: Dict[str, Actor] = {}
        self.running = False
        self._lock = asyncio.Lock()

    async def start(self):
        """Inicia el sistema de actores."""
        logger.info("Starting Actor System...")
        self.running = True
        
        # Crear actor supervisor raíz
        root_supervisor = SupervisorActor("root-supervisor", self)
        await self.register_actor(root_supervisor)
        await root_supervisor.start()
        
        logger.info("Actor System started.")

    async def stop(self):
        """Detiene todos los actores."""
        logger.info("Stopping Actor System...")
        self.running = False
        
        # Detener todos los actores en paralelo
        tasks = [actor.stop() for actor in self.actors.values()]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
            
        self.actors.clear()
        logger.info("Actor System stopped.")

    async def register_actor(self, actor: Actor):
        """Registra un actor en el sistema."""
        async with self._lock:
            self.actors[actor.actor_id] = actor
            logger.debug(f"Actor {actor.actor_id} registered.")

    async def unregister_actor(self, actor_id: str):
        """Elimina un actor del sistema."""
        async with self._lock:
            if actor_id in self.actors:
                del self.actors[actor_id]
                logger.debug(f"Actor {actor_id} unregistered.")

    async def spawn(self, actor_class, actor_id: Optional[str] = None, **kwargs) -> str:
        """Crea y registra un nuevo actor."""
        if actor_id is None:
            actor_id = f"{actor_class.__name__}-{uuid.uuid4().hex[:8]}"
            
        actor = actor_class(actor_id, self, **kwargs)
        await self.register_actor(actor)
        await actor.start()
        
        logger.info(f"Spawned actor {actor_id} of type {actor_class.__name__}")
        return actor_id

    async def tell(self, recipient_id: str, message: Message):
        """Envía un mensaje a un actor."""
        if recipient_id not in self.actors:
            logger.error(f"Actor {recipient_id} not found.")
            return
            
        await self.actors[recipient_id].tell(message)

    async def ask(self, recipient_id: str, message: Message, timeout: float = 5.0) -> Any:
        """Envía un mensaje y espera respuesta (patrón request-response)."""
        # Implementación simplificada - en producción usar correlación ID
        await self.tell(recipient_id, message)
        await asyncio.sleep(0.1)  # Placeholder
        return {"status": "acknowledged"}

    async def dispatch_command(self, command: str, payload: Any, target_id: Optional[str] = None):
        """Despacha un comando desde el exterior al sistema de actores."""
        if not target_id:
            # Enviar al supervisor raíz para distribución
            target_id = "root-supervisor"
            
        message = Message(
            message_id=str(uuid.uuid4()),
            sender_id="kernel-daemon",
            recipient_id=target_id,
            command=command,
            payload=payload,
            timestamp=asyncio.get_event_loop().time()
        )
        
        await self.tell(target_id, message)
        return {"dispatched": True, "target": target_id}

    async def restart_actor(self, actor_id: str):
        """Reinicia un actor fallido."""
        if actor_id not in self.actors:
            return
            
        actor = self.actors[actor_id]
        await actor.stop()
        
        # Recrear el actor (lógica simplificada)
        actor.status = ActorStatus.RUNNING
        await actor.start()
        logger.info(f"Actor {actor_id} restarted.")
