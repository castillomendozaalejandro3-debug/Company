"""
Task Manager Agent for Helios AI Engine

Integración con gestores de tareas corporativos (Trello, Asana, Monday.com) vía API REST.
Sincroniza tareas, plazos y prioridades. Genera reportes de productividad.
"""

import asyncio
import logging
import os
import hashlib
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from enum import Enum

import aiohttp
from pydantic import BaseModel, Field, field_validator, ConfigDict

from ai_engine.agents.base_agent import BaseAgent
from ai_engine.core.schemas import StrictBaseModel, sanitize_string

logger = logging.getLogger(__name__)


class TaskManagerPlatform(str, Enum):
    """Plataformas de gestión de tareas soportadas."""
    TRELLO = "trello"
    ASANA = "asana"
    MONDAY = "monday"


class TaskPriority(str, Enum):
    """Prioridades de tareas."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class TaskStatus(str, Enum):
    """Estados de tareas."""
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    REVIEW = "review"
    DONE = "done"
    BLOCKED = "blocked"


class CorporateTask(StrictBaseModel):
    """Modelo estricto para tarea corporativa."""
    id: str = Field(..., min_length=1, max_length=64, description="ID único de la tarea")
    title: str = Field(..., min_length=1, max_length=500, description="Título de la tarea")
    description: Optional[str] = Field(default=None, max_length=10000, description="Descripción detallada")
    status: str = Field(default="todo", pattern=r"^(todo|in_progress|review|done|blocked)$", description="Estado actual")
    priority: str = Field(default="medium", pattern=r"^(low|medium|high|urgent)$", description="Prioridad")
    due_date: Optional[datetime] = Field(default=None, description="Fecha de vencimiento")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Fecha de creación")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Fecha de actualización")
    assignee_ids: List[str] = Field(default_factory=list, description="IDs de asignados")
    project_id: Optional[str] = Field(default=None, max_length=64, description="ID del proyecto/board")
    platform: str = Field(default="unknown", max_length=32, description="Plataforma de origen")
    tags: List[str] = Field(default_factory=list, description="Etiquetas/tags")
    custom_fields: Dict[str, Any] = Field(default_factory=dict, description="Campos personalizados")
    
    @field_validator('title', 'description')
    @classmethod
    def sanitize_strings(cls, v: Optional[str]) -> Optional[str]:
        """Sanitizar campos de texto."""
        if v is None:
            return v
        return sanitize_string(v)


class ProductivityReport(StrictBaseModel):
    """Modelo para reporte de productividad."""
    model_config = ConfigDict(extra='forbid')
    
    period_start: datetime
    period_end: datetime
    total_tasks: int
    completed_tasks: int
    in_progress_tasks: int
    blocked_tasks: int
    overdue_tasks: int
    completion_rate: float = Field(ge=0, le=100, description="Porcentaje de completitud")
    average_completion_days: Optional[float] = Field(default=None, ge=0, description="Días promedio de completitud")
    tasks_by_priority: Dict[str, int] = Field(default_factory=dict, description="Tareas por prioridad")
    tasks_by_assignee: Dict[str, int] = Field(default_factory=dict, description="Tareas por asignado")
    velocity: Optional[float] = Field(default=None, ge=0, description="Velocidad (tareas/semana)")


class TaskManagerConfig(StrictBaseModel):
    """Configuración segura para el gestor de tareas."""
    platform: str = Field(..., pattern=r"^(trello|asana|monday)$", description="Plataforma a usar")
    api_key: str = Field(..., min_length=10, max_length=256, description="API Key o token")
    api_secret: Optional[str] = Field(default=None, max_length=256, description="API Secret (si aplica)")
    workspace_id: Optional[str] = Field(default=None, max_length=64, description="ID del workspace/espacio")
    board_id: Optional[str] = Field(default=None, max_length=64, description="ID del board/proyecto principal")
    base_url: Optional[str] = Field(default=None, max_length=256, description="URL base de la API")
    
    @field_validator('api_key', 'api_secret')
    @classmethod
    def validate_credentials(cls, v: Optional[str]) -> Optional[str]:
        """Validar que las credenciales no sean default."""
        if v is None:
            return None
        sanitized = sanitize_string(v)
        if len(sanitized) < 10 or sanitized in ('your_api_key', 'CHANGEME'):
            raise ValueError("Credenciales inválidas. Deben provenir de variables de entorno cifradas.")
        return sanitized
    
    @field_validator('base_url')
    @classmethod
    def validate_base_url(cls, v: Optional[str]) -> Optional[str]:
        """Validar URL base."""
        if v is None:
            return None
        if not v.startswith('https://'):
            raise ValueError("La URL base debe usar HTTPS")
        return v


class TaskManagerAgent(BaseAgent):
    """
    Agente de integración con gestores de tareas corporativos.
    
    Soporta:
    - Trello API
    - Asana API
    - Monday.com API
    
    Características:
    - Sincronización bidireccional de tareas
    - Gestión de plazos y prioridades
    - Reportes de productividad
    - Rate limiting y manejo de errores
    - Logging y auditoría completa
    """
    
    # URLs base de las APIs
    PLATFORM_URLS = {
        TaskManagerPlatform.TRELLO: "https://api.trello.com/1",
        TaskManagerPlatform.ASANA: "https://app.asana.com/api/1.0",
        TaskManagerPlatform.MONDAY: "https://api.monday.com/v2",
    }
    
    # Rate limits por plataforma (requests por segundo)
    RATE_LIMITS = {
        TaskManagerPlatform.TRELLO: 100,
        TaskManagerPlatform.ASANA: 50,
        TaskManagerPlatform.MONDAY: 50,
    }

    def __init__(self, config: TaskManagerConfig, agent_id: str = "task_manager_agent_001"):
        """
        Inicializar el agente de gestión de tareas.
        
        Args:
            config: Configuración con credenciales de API
            agent_id: Identificador único del agente
        """
        super().__init__(agent_name="Corporate Task Manager Agent", agent_id=agent_id)
        
        self._config = config
        self._session: Optional[aiohttp.ClientSession] = None
        self._rate_limit_delay = 1.0 / self.RATE_LIMITS.get(
            TaskManagerPlatform(config.platform), 
            50
        )
        self._last_request_time: float = 0
        
        # Mapeo de estados entre plataformas
        self._status_mapping = {
            'trello': {'todo': 'open', 'in_progress': 'active', 'done': 'closed'},
            'asana': {'todo': 'pending', 'in_progress': 'active', 'done': 'completed'},
            'monday': {'todo': 'not_started', 'in_progress': 'working_on_it', 'done': 'done'},
        }
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Obtener o crear sesión HTTP asíncrona."""
        if self._session is None or self._session.closed:
            headers = await self._build_headers()
            self._session = aiohttp.ClientSession(headers=headers)
        return self._session
    
    async def _build_headers(self) -> Dict[str, str]:
        """Construir headers de autenticación según plataforma."""
        platform = TaskManagerPlatform(self._config.platform)
        
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Helios-AI-Engine/1.0"
        }
        
        if platform == TaskManagerPlatform.TRELLO:
            headers["Accept"] = "application/json"
        elif platform == TaskManagerPlatform.ASANA:
            headers["Authorization"] = f"Bearer {self._config.api_key}"
        elif platform == TaskManagerPlatform.MONDAY:
            headers["Authorization"] = self._config.api_key
        
        return headers
    
    async def _check_rate_limit(self) -> None:
        """Respetar rate limits de la API."""
        elapsed = asyncio.get_event_loop().time() - self._last_request_time
        if elapsed < self._rate_limit_delay:
            await asyncio.sleep(self._rate_limit_delay - elapsed)
        self._last_request_time = asyncio.get_event_loop().time()
    
    async def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Realizar una request HTTP a la API.
        
        Args:
            method: Método HTTP (GET, POST, PUT, DELETE)
            endpoint: Endpoint relativo
            data: Datos del body (para POST/PUT)
            params: Parámetros query
            
        Returns:
            Respuesta de la API
        """
        await self._check_rate_limit()
        
        session = await self._get_session()
        base_url = self._config.base_url or self.PLATFORM_URLS[TaskManagerPlatform(self._config.platform)]
        url = f"{base_url}/{endpoint.lstrip('/')}"
        
        # Agregar parámetros específicos de plataforma
        if params is None:
            params = {}
        
        if self._config.platform == TaskManagerPlatform.TRELLO.value:
            params['key'] = self._config.api_key
            if self._config.api_secret:
                params['token'] = self._config.api_secret
        
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                async with session.request(
                    method=method,
                    url=url,
                    json=data,
                    params=params if params else None,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    response.raise_for_status()
                    
                    if response.status == 204:
                        return {"success": True}
                    
                    return await response.json()
                    
            except aiohttp.ClientResponseError as e:
                if e.status == 429:  # Rate limit
                    retry_count += 1
                    wait_time = (2 ** retry_count)
                    logger.warning(f"Rate limit. Reintentando en {wait_time}s")
                    await asyncio.sleep(wait_time)
                elif e.status >= 500:  # Server error
                    retry_count += 1
                    wait_time = (2 ** retry_count)
                    logger.warning(f"Error del servidor. Reintentando en {wait_time}s")
                    await asyncio.sleep(wait_time)
                else:
                    raise
            except Exception as e:
                logger.error(f"Error en request: {e}")
                if retry_count < max_retries - 1:
                    retry_count += 1
                    await asyncio.sleep(2 ** retry_count)
                else:
                    raise
        
        raise Exception("Max retries exceeded")
    
    async def list_tasks(
        self,
        board_id: Optional[str] = None,
        status_filter: Optional[List[str]] = None
    ) -> List[CorporateTask]:
        """
        Listar tareas del gestor.
        
        Args:
            board_id: ID del board/proyecto (None para default)
            status_filter: Filtrar por estados
            
        Returns:
            Lista de tareas
        """
        platform = self._config.platform
        target_board = board_id or self._config.board_id
        
        if platform == TaskManagerPlatform.TRELLO.value:
            return await self._list_trello_tasks(target_board, status_filter)
        elif platform == TaskManagerPlatform.ASANA.value:
            return await self._list_asana_tasks(target_board, status_filter)
        elif platform == TaskManagerPlatform.MONDAY.value:
            return await self._list_monday_tasks(target_board, status_filter)
        else:
            raise ValueError(f"Plataforma no soportada: {platform}")
    
    async def _list_trello_tasks(
        self,
        board_id: Optional[str],
        status_filter: Optional[List[str]]
    ) -> List[CorporateTask]:
        """Listar tareas de Trello."""
        endpoint = f"/boards/{board_id}/cards"
        params = {
            'fields': 'id,name,desc,due,dateLastActivity,idMembers,idLabels',
            'members': 'true',
            'labels': 'true'
        }
        
        result = await self._make_request('GET', endpoint, params=params)
        
        tasks = []
        for card in result:
            # Mapear estado
            status = "todo"
            if card.get('due') and datetime.fromisoformat(card['due'].replace('Z', '+00:00')) < datetime.utcnow():
                status = "blocked"
            
            task = CorporateTask(
                id=card.get('id', ''),
                title=card.get('name', ''),
                description=card.get('desc'),
                status=status,
                priority="medium",  # Trello usa labels para prioridad
                due_date=datetime.fromisoformat(card['due'].replace('Z', '+00:00')) if card.get('due') else None,
                created_at=datetime.fromisoformat(card['dateLastActivity'].replace('Z', '+00:00')) if card.get('dateLastActivity') else datetime.utcnow(),
                updated_at=datetime.fromisoformat(card['dateLastActivity'].replace('Z', '+00:00')) if card.get('dateLastActivity') else datetime.utcnow(),
                assignee_ids=card.get('idMembers', []),
                project_id=board_id,
                platform="trello",
                tags=[label.get('name', '') for label in card.get('labels', []) if label.get('name')]
            )
            tasks.append(task)
        
        logger.info(f"Se listaron {len(tasks)} tareas de Trello")
        return tasks
    
    async def _list_asana_tasks(
        self,
        project_id: Optional[str],
        status_filter: Optional[List[str]]
    ) -> List[CorporateTask]:
        """Listar tareas de Asana."""
        endpoint = "/tasks"
        params = {
            'opt_fields': 'id,name,notes,completed,completed_at,due_on,assignees,projects,created_at,modified_at,priority',
            'limit': 100
        }
        
        if project_id:
            params['project'] = project_id
        
        result = await self._make_request('GET', endpoint, params=params)
        
        tasks = []
        for task_data in result.get('data', []):
            # Mapear estado
            status = "done" if task_data.get('completed') else "todo"
            
            # Mapear prioridad
            priority_map = {1: "low", 2: "medium", 3: "high"}
            priority = priority_map.get(task_data.get('priority'), "medium")
            
            task = CorporateTask(
                id=task_data.get('id', ''),
                title=task_data.get('name', ''),
                description=task_data.get('notes'),
                status=status,
                priority=priority,
                due_date=datetime.fromisoformat(task_data['due_on']) if task_data.get('due_on') else None,
                created_at=datetime.fromisoformat(task_data['created_at']) if task_data.get('created_at') else datetime.utcnow(),
                updated_at=datetime.fromisoformat(task_data['modified_at']) if task_data.get('modified_at') else datetime.utcnow(),
                assignee_ids=[a.get('gid', '') for a in task_data.get('assignees', [])],
                project_id=project_id,
                platform="asana"
            )
            tasks.append(task)
        
        logger.info(f"Se listaron {len(tasks)} tareas de Asana")
        return tasks
    
    async def _list_monday_tasks(
        self,
        board_id: Optional[str],
        status_filter: Optional[List[str]]
    ) -> List[CorporateTask]:
        """Listar tareas de Monday.com usando GraphQL."""
        query = """
        query {
            boards(ids: [%s]) {
                items {
                    id
                    name
                    column_values {
                        text
                        value
                    }
                    created_at
                    updated_at
                }
            }
        }
        """ % board_id
        
        data = {"query": query}
        result = await self._make_request('POST', '', data=data)
        
        tasks = []
        boards = result.get('data', {}).get('boards', [])
        
        for board in boards:
            for item in board.get('items', []):
                # Extraer valores de columnas
                columns = {cv.get('text', '').lower(): cv for cv in item.get('column_values', [])}
                
                task = CorporateTask(
                    id=item.get('id', ''),
                    title=item.get('name', ''),
                    created_at=datetime.fromisoformat(item['created_at']) if item.get('created_at') else datetime.utcnow(),
                    updated_at=datetime.fromisoformat(item['updated_at']) if item.get('updated_at') else datetime.utcnow(),
                    project_id=board_id,
                    platform="monday",
                    custom_fields={cv.get('text', ''): cv.get('value', '') for cv in item.get('column_values', [])}
                )
                tasks.append(task)
        
        logger.info(f"Se listaron {len(tasks)} tareas de Monday")
        return tasks
    
    async def create_task(
        self,
        title: str,
        description: Optional[str] = None,
        due_date: Optional[datetime] = None,
        priority: TaskPriority = TaskPriority.MEDIUM,
        assignee_ids: Optional[List[str]] = None
    ) -> CorporateTask:
        """
        Crear una nueva tarea.
        
        Args:
            title: Título de la tarea
            description: Descripción opcional
            due_date: Fecha de vencimiento opcional
            priority: Prioridad de la tarea
            assignee_ids: IDs de usuarios asignados
            
        Returns:
            Tarea creada
        """
        platform = self._config.platform
        board_id = self._config.board_id
        
        if not board_id:
            raise ValueError("board_id es requerido para crear tareas")
        
        if platform == TaskManagerPlatform.TRELLO.value:
            return await self._create_trello_task(title, description, due_date, priority, board_id, assignee_ids)
        elif platform == TaskManagerPlatform.ASANA.value:
            return await self._create_asana_task(title, description, due_date, priority, board_id, assignee_ids)
        elif platform == TaskManagerPlatform.MONDAY.value:
            return await self._create_monday_task(title, description, due_date, priority, board_id, assignee_ids)
        else:
            raise ValueError(f"Plataforma no soportada: {platform}")
    
    async def _create_trello_task(
        self,
        title: str,
        description: Optional[str],
        due_date: Optional[datetime],
        priority: TaskPriority,
        board_id: str,
        assignee_ids: Optional[List[str]]
    ) -> CorporateTask:
        """Crear tarea en Trello."""
        endpoint = "/cards"
        data = {
            'name': title,
            'desc': description or '',
            'idBoard': board_id,
            'due': due_date.isoformat() if due_date else None,
            'idMembers': assignee_ids or []
        }
        
        result = await self._make_request('POST', endpoint, data=data)
        
        task = CorporateTask(
            id=result.get('id', ''),
            title=result.get('name', ''),
            description=result.get('desc'),
            due_date=datetime.fromisoformat(result['due'].replace('Z', '+00:00')) if result.get('due') else None,
            assignee_ids=result.get('idMembers', []),
            project_id=board_id,
            platform="trello"
        )
        
        await self.log_action("create_task", {
            "task_id": task.id,
            "title": task.title,
            "platform": "trello"
        })
        
        return task
    
    async def _create_asana_task(
        self,
        title: str,
        description: Optional[str],
        due_date: Optional[datetime],
        priority: TaskPriority,
        project_id: str,
        assignee_ids: Optional[List[str]]
    ) -> CorporateTask:
        """Crear tarea en Asana."""
        endpoint = "/tasks"
        data = {
            'data': {
                'name': title,
                'notes': description or '',
                'projects': [project_id],
                'due_on': due_date.strftime('%Y-%m-%d') if due_date else None,
                'assignees': assignee_ids or [],
                'priority': {'low': 1, 'medium': 2, 'high': 3, 'urgent': 3}.get(priority.value, 2)
            }
        }
        
        result = await self._make_request('POST', endpoint, data=data)
        task_data = result.get('data', {})
        
        task = CorporateTask(
            id=task_data.get('gid', ''),
            title=task_data.get('name', ''),
            description=task_data.get('notes'),
            due_date=datetime.fromisoformat(task_data['due_on']) if task_data.get('due_on') else None,
            assignee_ids=[a.get('gid', '') for a in task_data.get('assignees', [])],
            project_id=project_id,
            platform="asana"
        )
        
        await self.log_action("create_task", {
            "task_id": task.id,
            "title": task.title,
            "platform": "asana"
        })
        
        return task
    
    async def _create_monday_task(
        self,
        title: str,
        description: Optional[str],
        due_date: Optional[datetime],
        priority: TaskPriority,
        board_id: str,
        assignee_ids: Optional[List[str]]
    ) -> CorporateTask:
        """Crear tarea en Monday.com."""
        query = """
        mutation {
            create_item(
                board_id: %s,
                name: "%s",
                column_values: "%s"
            ) {
                id
                name
            }
        }
        """ % (board_id, title, f'{{\\"status\\": \\"Working on it\\"}}')
        
        data = {"query": query}
        result = await self._make_request('POST', '', data=data)
        
        item_data = result.get('data', {}).get('create_item', {})
        
        task = CorporateTask(
            id=item_data.get('id', ''),
            title=item_data.get('name', ''),
            project_id=board_id,
            platform="monday"
        )
        
        await self.log_action("create_task", {
            "task_id": task.id,
            "title": task.title,
            "platform": "monday"
        })
        
        return task
    
    async def update_task_status(self, task_id: str, new_status: TaskStatus) -> Dict[str, Any]:
        """
        Actualizar el estado de una tarea.
        
        Args:
            task_id: ID de la tarea
            new_status: Nuevo estado
            
        Returns:
            Resultado de la actualización
        """
        platform = self._config.platform
        
        if platform == TaskManagerPlatform.TRELLO.value:
            # En Trello, mover entre listas
            return await self._update_trello_status(task_id, new_status)
        elif platform == TaskManagerPlatform.ASANA.value:
            return await self._update_asana_status(task_id, new_status)
        elif platform == TaskManagerPlatform.MONDAY.value:
            return await self._update_monday_status(task_id, new_status)
        else:
            raise ValueError(f"Plataforma no soportada: {platform}")
    
    async def _update_trello_status(self, task_id: str, new_status: TaskStatus) -> Dict[str, Any]:
        """Actualizar estado en Trello (mover lista)."""
        # Implementación simplificada - en producción se mapean listas específicas
        endpoint = f"/cards/{task_id}"
        data = {
            'closed': new_status == TaskStatus.DONE
        }
        
        result = await self._make_request('PUT', endpoint, data=data)
        
        await self.log_action("update_task_status", {
            "task_id": task_id,
            "new_status": new_status.value,
            "platform": "trello"
        })
        
        return {"success": True, "task_id": task_id, "status": new_status.value}
    
    async def _update_asana_status(self, task_id: str, new_status: TaskStatus) -> Dict[str, Any]:
        """Actualizar estado en Asana."""
        endpoint = f"/tasks/{task_id}"
        data = {
            'data': {
                'completed': new_status == TaskStatus.DONE
            }
        }
        
        result = await self._make_request('PUT', endpoint, data=data)
        
        await self.log_action("update_task_status", {
            "task_id": task_id,
            "new_status": new_status.value,
            "platform": "asana"
        })
        
        return {"success": True, "task_id": task_id, "status": new_status.value}
    
    async def _update_monday_status(self, task_id: str, new_status: TaskStatus) -> Dict[str, Any]:
        """Actualizar estado en Monday.com."""
        status_value = {
            TaskStatus.TODO: "Not Started",
            TaskStatus.IN_PROGRESS: "Working on it",
            TaskStatus.DONE: "Done",
            TaskStatus.BLOCKED: "Stuck",
            TaskStatus.REVIEW: "Review"
        }.get(new_status, "Working on it")
        
        query = """
        mutation {
            change_column_value(
                item_id: "%s",
                board_id: %s,
                column_id: "status",
                value: "%s"
            ) {
                id
            }
        }
        """ % (task_id, self._config.board_id or '0', status_value)
        
        data = {"query": query}
        result = await self._make_request('POST', '', data=data)
        
        await self.log_action("update_task_status", {
            "task_id": task_id,
            "new_status": new_status.value,
            "platform": "monday"
        })
        
        return {"success": True, "task_id": task_id, "status": new_status.value}
    
    async def generate_productivity_report(
        self,
        days: int = 30,
        board_id: Optional[str] = None
    ) -> ProductivityReport:
        """
        Generar reporte de productividad.
        
        Args:
            days: Cantidad de días hacia atrás para el análisis
            board_id: ID del board (None para todos)
            
        Returns:
            Reporte de productividad
        """
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
        
        # Obtener todas las tareas
        tasks = await self.list_tasks(board_id=board_id)
        
        # Filtrar por período
        recent_tasks = [
            t for t in tasks 
            if t.created_at >= start_date or (t.updated_at and t.updated_at >= start_date)
        ]
        
        # Calcular métricas
        completed = [t for t in recent_tasks if t.status == TaskStatus.DONE.value]
        in_progress = [t for t in recent_tasks if t.status == TaskStatus.IN_PROGRESS.value]
        blocked = [t for t in recent_tasks if t.status == TaskStatus.BLOCKED.value]
        
        # Tareas vencidas
        overdue = [
            t for t in recent_tasks 
            if t.due_date and t.due_date < datetime.utcnow() and t.status != TaskStatus.DONE.value
        ]
        
        # Tareas por prioridad
        by_priority = {}
        for t in recent_tasks:
            p = t.priority
            by_priority[p] = by_priority.get(p, 0) + 1
        
        # Tareas por asignado
        by_assignee = {}
        for t in recent_tasks:
            for assignee in t.assignee_ids:
                by_assignee[assignee] = by_assignee.get(assignee, 0) + 1
        
        # Calcular tasa de completitud
        total = len(recent_tasks)
        completion_rate = (len(completed) / total * 100) if total > 0 else 0
        
        # Calcular velocidad (tareas por semana)
        weeks = days / 7
        velocity = len(completed) / weeks if weeks > 0 else 0
        
        report = ProductivityReport(
            period_start=start_date,
            period_end=end_date,
            total_tasks=total,
            completed_tasks=len(completed),
            in_progress_tasks=len(in_progress),
            blocked_tasks=len(blocked),
            overdue_tasks=len(overdue),
            completion_rate=completion_rate,
            tasks_by_priority=by_priority,
            tasks_by_assignee=by_assignee,
            velocity=velocity
        )
        
        await self.log_action("generate_productivity_report", {
            "period_days": days,
            "total_tasks": total,
            "completion_rate": completion_rate
        })
        
        return report
    
    async def execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Ejecutar una tarea del agente.
        
        Args:
            task: Diccionario con parámetros de la tarea
            
        Returns:
            Resultado de la ejecución
        """
        operation = task.get("operation")
        
        operations = {
            "list_tasks": lambda: self.list_tasks(
                board_id=task.get("board_id"),
                status_filter=task.get("status_filter")
            ),
            "create_task": lambda: self.create_task(
                title=task.get("title"),
                description=task.get("description"),
                due_date=task.get("due_date"),
                priority=TaskPriority(task.get("priority", "medium")),
                assignee_ids=task.get("assignee_ids")
            ),
            "update_status": lambda: self.update_task_status(
                task_id=task.get("task_id"),
                new_status=TaskStatus(task.get("new_status"))
            ),
            "productivity_report": lambda: self.generate_productivity_report(
                days=task.get("days", 30),
                board_id=task.get("board_id")
            ),
        }
        
        if operation not in operations:
            raise ValueError(f"Operación desconocida: {operation}")
        
        try:
            result = await operations[operation]()
            return {
                "success": True,
                "operation": operation,
                "result": result
            }
        except Exception as e:
            logger.error(f"Error ejecutando tarea {operation}: {e}")
            return {
                "success": False,
                "operation": operation,
                "error": str(e)
            }
    
    async def check_authorization(self, target: str) -> bool:
        """
        Verificar autorización para acceder a un recurso.
        
        Args:
            target: Recurso a verificar
            
        Returns:
            True si está autorizado
        """
        # Verificar que hay credenciales configuradas
        if not self._config.api_key:
            return False
        
        # Para boards, verificar acceso
        if target.startswith("board:"):
            board_id = target.replace("board:", "")
            try:
                # Intentar listar tareas del board
                await self.list_tasks(board_id=board_id)
                return True
            except Exception:
                return False
        
        return True
    
    async def log_action(self, action: str, context: Dict[str, Any]) -> None:
        """
        Registrar una acción para auditoría.
        
        Args:
            action: Nombre de la acción
            context: Contexto adicional
        """
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "agent_id": self.agent_id,
            "action": action,
            "context": context
        }
        
        logger.info(f"[AUDIT] {log_entry}")
    
    async def close(self) -> None:
        """Cerrar la sesión HTTP."""
        if self._session and not self._session.closed:
            await self._session.close()
            logger.info("Sesión HTTP cerrada")
    
    @property
    def platform(self) -> str:
        """Obtener plataforma configurada."""
        return self._config.platform
