import os
import logging
from typing import Optional, Dict, Any
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Importar componentes del motor
try:
    from agents.master_orchestrator import MasterOrchestrator
    from helios_core_client import HeliosCoreClient
    CORE_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Algunos módulos no disponibles: {e}")
    CORE_AVAILABLE = False

app = FastAPI(
    title="Helios AI Engine API",
    description="API para el sistema multi-agente de Helios",
    version="1.0.0"
)

# Configurar CORS
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

# Modelos Pydantic
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

# Inicializar componentes
orchestrator: Optional[MasterOrchestrator] = None
core_client: Optional[HeliosCoreClient] = None

@app.on_event("startup")
async def startup_event():
    global orchestrator, core_client
    if CORE_AVAILABLE:
        try:
            core_client = HeliosCoreClient()
            orchestrator = MasterOrchestrator(core_client=core_client)
            logger.info("Motor de Helios inicializado correctamente")
        except Exception as e:
            logger.error(f"Error al inicializar el motor: {e}")
            orchestrator = None
            core_client = None

@app.get("/api/v1/health", response_model=HealthResponse)
async def health_check():
    """Verifica el estado de todos los componentes del sistema"""
    health_status = {
        "status": "healthy",
        "python_server": True,
        "rust_core": False,
        "orchestrator": False,
        "details": {}
    }
    
    # Verificar Rust Core
    if core_client:
        try:
            ping_result = await core_client.ping()
            health_status["rust_core"] = ping_result.get("success", False)
            health_status["details"]["rust_core_message"] = ping_result.get("message", "")
        except Exception as e:
            health_status["details"]["rust_core_error"] = str(e)
            logger.warning(f"Rust Core no disponible: {e}")
    
    # Verificar Orchestrator
    health_status["orchestrator"] = orchestrator is not None
    
    # Determinar estado general
    if not health_status["rust_core"] or not health_status["orchestrator"]:
        health_status["status"] = "degraded"
    
    return HealthResponse(**health_status)

@app.post("/api/v1/execute", response_model=ExecuteResponse)
async def execute_command(request_data: ExecuteRequest):
    """Ejecuta una solicitud del usuario a través del orquestador maestro"""
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Motor de Helios no inicializado")
    
    try:
        logger.info(f"Procesando solicitud: {request_data.request[:100]}...")
        
        context = request_data.context or {}
        context["user_id"] = request_data.user_id
        
        result = await orchestrator.process_user_request(
            user_request=request_data.request,
            context=context
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

@app.get("/api/v1/logs")
async def get_logs(lines: int = 50):
    """Obtiene las últimas líneas de los logs del sistema"""
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
                with open(log_file, 'r') as f:
                    file_logs = f.readlines()[-lines:]
                    for line in file_logs:
                        all_logs.append({
                            "source": os.path.basename(log_file),
                            "line": line.strip()
                        })
        except Exception as e:
            logger.warning(f"No se pudo leer {log_file}: {e}")
    
    # Ordenar por timestamp (asumiendo que está al inicio de cada línea)
    all_logs.sort(key=lambda x: x["line"], reverse=True)
    
    return {"logs": all_logs[:lines]}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
