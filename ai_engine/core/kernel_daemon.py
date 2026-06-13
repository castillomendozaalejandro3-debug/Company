"""
KernelDaemon - El núcleo inmutable del sistema Helios.
Gestiona el ciclo de vida de los workers, la comunicación gRPC con el núcleo Rust
y la coordinación del sistema de actores.
"""
import asyncio
import logging
import signal
import sys
import os
from typing import Dict, List, Optional
import grpc
from concurrent import futures

# Imports locales corregidos
try:
    from .worker_manager import WorkerManager
    from .actor_system import ActorSystem
    from .health_checker import HealthChecker
    from .structured_logger import get_logger
    from ..proto_generated import helios_pb2, helios_pb2_grpc
except ImportError:
    # Fallback para ejecución directa
    from worker_manager import WorkerManager
    from actor_system import ActorSystem
    from health_checker import HealthChecker
    from structured_logger import get_logger
    # proto_generated se maneja en runtime

logger = get_logger(__name__)

class KernelDaemonServicer(helios_pb2_grpc.HeliosServiceServicer):
    """Implementación del servicio gRPC del Kernel."""
    
    def __init__(self, kernel_daemon):
        self.kernel_daemon = kernel_daemon

    async def GetMetrics(self, request, context):
        """Obtiene métricas del sistema."""
        try:
            metrics = await self.kernel_daemon.health_checker.get_full_report()
            return helios_pb2.MetricsResponse(
                status="healthy" if metrics["status"] == "ok" else "degraded",
                cpu_usage=metrics["components"].get("rust_core", {}).get("cpu", 0.0),
                memory_usage=metrics["components"].get("system", {}).get("ram_used", 0),
                disk_usage=metrics["components"].get("system", {}).get("disk_used", 0),
                active_workers=len(self.kernel_daemon.worker_manager.active_workers),
                timestamp=asyncio.get_event_loop().time()
            )
        except Exception as e:
            logger.error(f"Error getting metrics: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return helios_pb2.MetricsResponse(status="error")

    async def ExecuteCommand(self, request, context):
        """Ejecuta un comando a través del sistema de actores."""
        try:
            command = request.command
            payload = request.payload
            
            # Validar comando en el DPI Validator si existe
            # Enviar al Actor System para distribución
            result = await self.kernel_daemon.actor_system.dispatch_command(
                command, 
                payload,
                request.target_worker_id if hasattr(request, 'target_worker_id') else None
            )
            
            return helios_pb2.CommandResponse(
                success=True,
                result=str(result),
                message="Command executed successfully"
            )
        except Exception as e:
            logger.error(f"Error executing command: {e}")
            return helios_pb2.CommandResponse(
                success=False,
                message=str(e)
            )

class KernelDaemon:
    """Clase principal del Daemon del Kernel."""
    
    def __init__(self, host: str = "0.0.0.0", port: int = 50051):
        self.host = host
        self.port = port
        self.server = None
        self.running = False
        
        # Componentes principales
        self.worker_manager = WorkerManager(self)
        self.actor_system = ActorSystem(self)
        self.health_checker = HealthChecker(self)
        
        # Configuración de señales
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Maneja señales de interrupción."""
        logger.info(f"Signal {signum} received. Shutting down gracefully...")
        self.running = False

    async def start(self):
        """Inicia el Kernel Daemon."""
        logger.info(f"Starting KernelDaemon on {self.host}:{self.port}")
        
        # Iniciar servidor gRPC
        self.server = grpc.aio.server(
            futures.ThreadPoolExecutor(max_workers=10),
            options=[
                ('grpc.max_metadata_size', 4 * 1024 * 1024),
                ('grpc.max_send_message_length', 4 * 1024 * 1024),
                ('grpc.max_receive_message_length', 4 * 1024 * 1024),
            ]
        )
        
        helios_pb2_grpc.add_HeliosServiceServicer_to_server(
            KernelDaemonServicer(self), 
            self.server
        )
        
        self.server.add_insecure_port(f"{self.host}:{self.port}")
        await self.server.start()
        
        self.running = True
        logger.info(f"KernelDaemon started successfully on port {self.port}")
        
        # Iniciar componentes
        await self.worker_manager.initialize()
        await self.actor_system.start()
        
        try:
            await self.server.wait_for_termination()
        except KeyboardInterrupt:
            pass
        finally:
            await self.stop()

    async def stop(self):
        """Detiene el Kernel Daemon de forma segura."""
        logger.info("Stopping KernelDaemon...")
        self.running = False
        
        # Detener componentes en orden inverso
        await self.actor_system.stop()
        await self.worker_manager.shutdown()
        
        if self.server:
            await self.server.stop(grace=5)
            
        logger.info("KernelDaemon stopped.")

async def main():
    """Punto de entrada principal."""
    daemon = KernelDaemon()
    await daemon.start()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logger.critical(f"Fatal error in KernelDaemon: {e}")
        sys.exit(1)
