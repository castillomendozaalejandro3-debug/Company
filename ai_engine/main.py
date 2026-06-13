"""
Helios AI Engine - Main Entry Point with Kernel Daemon Integration

Flujo: FastAPI -> KernelDaemon -> Validación -> Worker -> Respuesta
"""

import os
import logging
import asyncio
import uuid
import time
from typing import Optional, Dict, Any
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

logger = logging.getLogger(__name__)

# Importar componentes del kernel
try:
    from ai_engine.core.idle_monitor import (
        IdleTimeMonitor,
        WorkerDomain,
        init_idle_monitor,
        get_idle_monitor
    )
    from ai_engine.core.ipc_mtls import (
        IPCKernelDaemon,
        MTLSIPCChannel,
        IPCMessage,
        get_default_socket_path
    )
    KERNEL_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Módulos del Kernel no disponibles: {e}")
    KERNEL_AVAILABLE = False

# Importar seguridad
try:
    from pathlib import Path
    from ai_engine.core.security import validate_path, load_encrypted_env, EnvEncryptionError
    from ai_engine.core.schemas import ExecuteRequest, ExecuteResponse, HealthResponse, PathRequest
    SECURITY_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Módulos de seguridad no disponibles: {e}")
    SECURITY_AVAILABLE = False
    
    class ExecuteRequest(BaseModel):
        request: str
        user_id: Optional[str] = "anonymous"
        context: Optional[Dict[str, Any]] = None
    
    class ExecuteResponse(BaseModel):
        success: bool
        message: str
        data: Optional[Any] = None
        error: Optional[str] = None
    
    class HealthResponse(BaseModel):
        status: str
        python_server: bool
        rust_core: bool
        orchestrator: bool
        details: Dict[str, Any]
    
    class PathRequest(BaseModel):
        workspace_path: str
        target_path: str


class KernelDaemon:
    """
    Daemon del Kernel que gestiona el ciclo de vida de Workers.
    
    Recibe requests de FastAPI, valida, lanza Workers y retorna respuestas.
    """
    
    def __init__(self):
        self.ipc_daemon: Optional[IPCKernelDaemon] = None
        self.idle_monitor: Optional[IdleTimeMonitor] = None
        self._workers: Dict[str, Dict[str, Any]] = {}
        self._running = False
        self._socket_path = get_default_socket_path()
    
    async def start(self) -> None:
        """Inicializa el Kernel Daemon."""
        if not KERNEL_AVAILABLE:
            logger.warning("Kernel no disponible, corriendo en modo degradado")
            return
        
        try:
            self.idle_monitor = init_idle_monitor(
                idle_threshold=5.0,
                interrupt_on_human=True
            )
            self.idle_monitor.start()
            logger.info("Idle Monitor iniciado")
            
            self.ipc_daemon = IPCKernelDaemon(socket_path=self._socket_path)
            await self.ipc_daemon.start()
            logger.info(f"IPC Daemon iniciado en {self._socket_path}")
            
            self._running = True
        except Exception as e:
            logger.error(f"Error iniciando Kernel Daemon: {e}")
            raise
    
    async def stop(self) -> None:
        """Detiene el Kernel Daemon."""
        self._running = False
        
        if self.idle_monitor:
            self.idle_monitor.stop()
        
        if self.ipc_daemon:
            await self.ipc_daemon.stop()
        
        logger.info("Kernel Daemon detenido")
    
    async def process_request(
        self,
        user_request: str,
        user_id: str = "anonymous",
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Procesa una solicitud del usuario a través del Kernel.
        
        Flujo:
        1. Validar request
        2. Determinar Worker apropiado
        3. Lanzar Worker vía IPC
        4. Esperar respuesta
        5. Retornar resultado
        """
        request_id = str(uuid.uuid4())
        start_time = time.time()
        
        logger.info(f"[{request_id}] Procesando request: {user_request[:50]}...")
        
        try:
            validated_data = await self._validate_request(
                user_request, user_id, context
            )
            
            worker_type = self._determine_worker_type(validated_data)
            
            worker_id = await self._launch_worker(
                request_id=request_id,
                worker_type=worker_type,
                payload=validated_data
            )
            
            result = await self._wait_for_worker_response(
                worker_id=worker_id,
                timeout=60.0
            )
            
            elapsed = time.time() - start_time
            logger.info(f"[{request_id}] Completado en {elapsed:.2f}s")
            
            return {
                "success": True,
                "message": result.get("message", "Request processed"),
                "data": result.get("data"),
                "request_id": request_id,
                "worker_id": worker_id,
                "elapsed_seconds": elapsed
            }
            
        except asyncio.TimeoutError:
            logger.error(f"[{request_id}] Timeout esperando Worker")
            return {
                "success": False,
                "message": "Timeout processing request",
                "error": "Worker did not respond within timeout",
                "request_id": request_id
            }
        except Exception as e:
            logger.error(f"[{request_id}] Error: {e}", exc_info=True)
            return {
                "success": False,
                "message": "Internal error processing request",
                "error": str(e),
                "request_id": request_id
            }
    
    async def _validate_request(
        self,
        user_request: str,
        user_id: str,
        context: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Valida y sanitiza el request del usuario."""
        if not user_request or len(user_request.strip()) == 0:
            raise ValueError("Empty request")
        
        if len(user_request) > 10000:
            raise ValueError("Request too long (max 10000 chars)")
        
        return {
            "request": user_request.strip(),
            "user_id": user_id,
            "context": context or {},
            "timestamp": time.time()
        }
    
    def _determine_worker_type(self, validated_data: Dict[str, Any]) -> str:
        """Determina qué tipo de Worker debe procesar el request."""
        request = validated_data["request"].lower()
        
        if any(kw in request for kw in ["security", "protect", "threat", "attack"]):
            return "security_shield"
        elif any(kw in request for kw in ["file", "folder", "path", "directory"]):
            return "pc_controller"
        elif any(kw in request for kw in ["screenshot", "image", "visual", "see"]):
            return "visual_agent"
        elif any(kw in request for kw in ["test", "pentest", "vulnerability"]):
            return "pentest_agent"
        elif any(kw in request for kw in ["whatsapp", "message", "chat"]):
            return "whatsapp_agent"
        else:
            return "master_orchestrator"
    
    async def _launch_worker(
        self,
        request_id: str,
        worker_type: str,
        payload: Dict[str, Any]
    ) -> str:
        """Lanza un Worker para procesar el request."""
        worker_id = f"{worker_type}_{request_id}"
        
        if not KERNEL_AVAILABLE or not self.ipc_daemon:
            logger.warning(f"Simulando Worker {worker_id} (IPC no disponible)")
            self._workers[worker_id] = {
                "type": worker_type,
                "status": "simulated",
                "start_time": time.time()
            }
            return worker_id
        
        try:
            message = IPCMessage(
                message_id=request_id,
                message_type="worker_request",
                source="kernel",
                destination=worker_type,
                payload=payload,
                timestamp=time.time()
            )
            
            if self.ipc_daemon.channel and self.ipc_daemon.channel._socket:
                pass
            
            self._workers[worker_id] = {
                "type": worker_type,
                "status": "launched",
                "start_time": time.time(),
                "message": message
            }
            
            logger.info(f"Worker {worker_id} lanzado (tipo: {worker_type})")
            
            if self.idle_monitor and worker_type in ["pc_controller", "visual_agent"]:
                self.idle_monitor.register_worker(
                    worker_id=worker_id,
                    domain=WorkerDomain.DOMAIN_2_ASSISTANT,
                    interrupt_callback=lambda: self._freeze_worker(worker_id)
                )
            
            return worker_id
            
        except Exception as e:
            logger.error(f"Error lanzando Worker: {e}")
            raise
    
    def _freeze_worker(self, worker_id: str) -> None:
        """Congela la ejecución de un Worker por intervención humana."""
        if worker_id in self._workers:
            self._workers[worker_id]["status"] = "frozen"
            logger.warning(f"Worker {worker_id} CONGELADO por intervención humana")
    
    async def _wait_for_worker_response(
        self,
        worker_id: str,
        timeout: float = 15.0
    ) -> Dict[str, Any]:
        """Espera respuesta del Worker con timeout.
        
        En modo simulado (sin IPC), retorna respuesta inmediata (<1s).
        En modo normal, espera hasta timeout (default 15s).
        """
        start = time.time()
        
        # Verificación inmediata para modo simulado
        if worker_id in self._workers:
            worker_info = self._workers[worker_id]
            if worker_info.get("status") == "simulated":
                logger.info(f"Worker {worker_id} en modo simulado, respuesta inmediata")
                self._workers[worker_id]["status"] = "completed"
                self._workers[worker_id]["result"] = {
                    "message": f"Simulated {worker_info['type']} response",
                    "data": {"worker_type": worker_info["type"], "mode": "degraded"}
                }
                return self._workers[worker_id]["result"]
        
        while time.time() - start < timeout:
            if worker_id not in self._workers:
                return {"message": "Worker completed", "data": None}
            
            worker_info = self._workers[worker_id]
            
            if worker_info.get("status") == "frozen":
                await asyncio.sleep(0.5)
                continue
            
            if worker_info.get("status") == "completed":
                return worker_info.get("result", {"message": "Done"})
            
            if worker_info.get("status") == "simulated":
                logger.info(f"Worker {worker_id} en modo simulado, respuesta inmediata")
                await asyncio.sleep(0.1)
                self._workers[worker_id]["status"] = "completed"
                self._workers[worker_id]["result"] = {
                    "message": f"Simulated {worker_info['type']} response",
                    "data": {"worker_type": worker_info["type"], "mode": "degraded"}
                }
                return self._workers[worker_id]["result"]
            
            await asyncio.sleep(0.1)
        
        raise asyncio.TimeoutError(f"Worker {worker_id} timeout after {timeout}s")
    
    def get_status(self) -> Dict[str, Any]:
        """Obtiene estado del Kernel Daemon."""
        return {
            "running": self._running,
            "socket_path": self._socket_path,
            "active_workers": len(self._workers),
            "workers": {
                wid: {"type": w["type"], "status": w["status"]}
                for wid, w in self._workers.items()
            },
            "idle_monitor": self.idle_monitor.get_state() if self.idle_monitor else None,
            "ipc_available": KERNEL_AVAILABLE
        }


app = FastAPI(
    title="Helios AI Engine API",
    description="API para el sistema multi-agente de Helios con Kernel Daemon",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://0.0.0.0:3000"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

kernel_daemon: Optional[KernelDaemon] = None


def load_encrypted_environment():
    """Load encrypted environment variables from .env.enc if it exists."""
    env_key = os.environ.get("HELIOS_ENV_KEY")
    possible_paths = [
        Path.cwd() / ".env.enc",
        Path(__file__).parent.parent / ".env.enc",
        Path("/") / "app" / ".env.enc",
    ]
    
    for enc_path in possible_paths:
        if enc_path.exists():
            try:
                logger.info(f"Loading encrypted environment from {enc_path}")
                env_vars = load_encrypted_env(str(enc_path), key=env_key)
                for key, value in env_vars.items():
                    if key not in os.environ:
                        os.environ[key] = value
                logger.info(f"Successfully loaded {len(env_vars)} environment variables")
                return True
            except EnvEncryptionError as e:
                logger.error(f"Failed to decrypt environment: {e}")
                return False
            except FileNotFoundError:
                continue
    
    return False


@app.on_event("startup")
async def startup_event():
    global kernel_daemon
    
    load_encrypted_environment()
    
    if KERNEL_AVAILABLE:
        try:
            kernel_daemon = KernelDaemon()
            await kernel_daemon.start()
            logger.info("Kernel Daemon inicializado correctamente")
        except Exception as e:
            logger.error(f"Error al inicializar Kernel Daemon: {e}")
            kernel_daemon = None
    else:
        kernel_daemon = KernelDaemon()
        logger.info("Kernel Daemon en modo degradado")


@app.on_event("shutdown")
async def shutdown_event():
    global kernel_daemon
    if kernel_daemon:
        await kernel_daemon.stop()
        logger.info("Kernel Daemon apagado")


@app.get("/api/v1/health", response_model=HealthResponse)
async def health_check():
    health_status = {
        "status": "healthy",
        "python_server": True,
        "rust_core": False,
        "orchestrator": kernel_daemon is not None,
        "details": {}
    }
    
    if kernel_daemon:
        kernel_status = kernel_daemon.get_status()
        health_status["details"]["kernel"] = kernel_status
    
    if not health_status["orchestrator"]:
        health_status["status"] = "degraded"
    
    return HealthResponse(**health_status)


@app.post("/api/v1/execute", response_model=ExecuteResponse)
async def execute_command(request_data: ExecuteRequest):
    """
    Ejecuta una solicitud del usuario a través del Kernel Daemon.
    
    Flujo: FastAPI -> KernelDaemon -> Validación -> Worker -> Respuesta
    """
    if not kernel_daemon:
        raise HTTPException(status_code=503, detail="Kernel Daemon no inicializado")
    
    try:
        result = await kernel_daemon.process_request(
            user_request=request_data.request,
            user_id=request_data.user_id,
            context=request_data.context
        )
        
        return ExecuteResponse(
            success=result.get("success", False),
            message=result.get("message", ""),
            data=result.get("data"),
            error=result.get("error")
        )
    
    except Exception as e:
        logger.error(f"Error al ejecutar comando: {e}", exc_info=True)
        return ExecuteResponse(
            success=False,
            message="Error interno al procesar la solicitud",
            error=str(e)
        )


@app.get("/api/v1/kernel/status")
async def kernel_status():
    """Obtiene el estado detallado del Kernel Daemon."""
    if not kernel_daemon:
        raise HTTPException(status_code=503, detail="Kernel Daemon no inicializado")
    
    return kernel_daemon.get_status()


@app.get("/api/v1/logs")
async def get_logs(lines: int = 50):
    if lines < 1 or lines > 1000:
        raise HTTPException(status_code=400, detail="lines must be between 1 and 1000")
    
    log_files = [
        "logs/orchestrator.log",
        "logs/security_shield.log",
        "logs/pc_controller.log",
        "logs/visual_agent.log",
        "logs/pentest_agent.log"
    ]
    
    all_logs = []
    
    for log_file in log_files:
        try:
            if os.path.exists(log_file):
                if SECURITY_AVAILABLE:
                    workspace = Path.cwd()
                    validated_path = validate_path(workspace, log_file)
                
                with open(log_file, 'r') as f:
                    file_logs = f.readlines()[-lines:]
                    for line in file_logs:
                        all_logs.append({
                            "source": os.path.basename(log_file),
                            "line": line.strip()
                        })
        except PermissionError:
            raise HTTPException(status_code=403, detail="Access denied to log file")
        except Exception as e:
            logger.warning(f"No se pudo leer {log_file}: {e}")
    
    all_logs.sort(key=lambda x: x["line"], reverse=True)
    
    return {"logs": all_logs[:lines]}


@app.post("/api/v1/validate-path")
async def validate_path_endpoint(request: PathRequest):
    if not SECURITY_AVAILABLE:
        raise HTTPException(status_code=503, detail="Security module not available")
    
    try:
        workspace = Path(request.workspace_path)
        target = Path(request.target_path)
        
        validated = validate_path(workspace, target)
        
        return {
            "valid": True,
            "resolved_path": str(validated),
            "message": "Path is within workspace boundary"
        }
    except PermissionError as e:
        return {
            "valid": False,
            "error": str(e)
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Path validation error: {str(e)}")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
