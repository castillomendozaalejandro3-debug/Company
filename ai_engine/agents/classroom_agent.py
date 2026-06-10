"""
Google Classroom Agent for Helios AI Engine

Integración con Google Classroom API para sincronización de tareas, plazos y calificaciones.
Implementa autenticación OAuth2 con credenciales cifradas y extracción de requerimientos académicos.
"""

import asyncio
import logging
import os
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from enum import Enum

from google.oauth2.credentials import Credentials
from google.oauth2 import service_account
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from pydantic import BaseModel, Field, field_validator, ConfigDict

from ai_engine.agents.base_agent import BaseAgent
from ai_engine.core.schemas import StrictBaseModel, sanitize_string
from ai_engine.core.security.env_encryptor import load_encrypted_env, apply_env_to_os

logger = logging.getLogger(__name__)


class CourseWorkType(str, Enum):
    """Tipos de trabajo del curso."""
    ASSIGNMENT = "ASSIGNMENT"
    QUESTION = "QUESTION"
    MATERIAL = "MATERIAL"
    MULTIPLE_CHOICE_QUESTION = "MULTIPLE_CHOICE_QUESTION"


class StudentState(str, Enum):
    """Estados de entrega de estudiante."""
    WORK_STATE_UNSPECIFIED = "WORK_STATE_UNSPECIFIED"
    NEW = "NEW"
    CREATED = "CREATED"
    TURNED_IN = "TURNED_IN"
    RETURNED = "RETURNED"
    RECLAIMED_BY_STUDENT = "RECLAIMED_BY_STUDENT"


class GradeState(str, Enum):
    """Estados de calificación."""
    GRADE_STATE_UNSPECIFIED = "GRADE_STATE_UNSPECIFIED"
    ASSIGNED = "ASSIGNED"
    RETURNED = "RETURNED"


class ClassroomCourse(StrictBaseModel):
    """Modelo estricto para un curso de Classroom."""
    id: str = Field(..., min_length=1, max_length=64, description="ID del curso")
    name: str = Field(..., min_length=1, max_length=256, description="Nombre del curso")
    section: Optional[str] = Field(default=None, max_length=256, description="Sección del curso")
    description: Optional[str] = Field(default=None, max_length=2000, description="Descripción del curso")
    owner_id: str = Field(..., min_length=1, max_length=64, description="ID del propietario")
    course_state: str = Field(default="ACTIVE", pattern=r"^(ACTIVE|ARCHIVED|PROVISIONED|SUSPENDED)$", description="Estado del curso")
    
    @field_validator('name', 'section', 'description')
    @classmethod
    def sanitize_strings(cls, v: Optional[str]) -> Optional[str]:
        """Sanitizar campos de texto."""
        if v is None:
            return v
        return sanitize_string(v)


class ClassroomAssignment(StrictBaseModel):
    """Modelo estricto para una tarea/actividad."""
    id: str = Field(..., min_length=1, max_length=64, description="ID de la tarea")
    course_id: str = Field(..., min_length=1, max_length=64, description="ID del curso")
    title: str = Field(..., min_length=1, max_length=3000, description="Título de la tarea")
    description: Optional[str] = Field(default=None, max_length=30000, description="Descripción de la tarea")
    state: str = Field(default="DRAFT", pattern=r"^(DRAFT|PUBLISHED|DELETED)$", description="Estado de publicación")
    due_date: Optional[datetime] = Field(default=None, description="Fecha de vencimiento")
    max_points: Optional[float] = Field(default=None, ge=0, description="Puntaje máximo")
    work_type: str = Field(default="ASSIGNMENT", pattern=r"^(ASSIGNMENT|QUESTION|MATERIAL|MULTIPLE_CHOICE_QUESTION)$", description="Tipo de trabajo")
    assignment_share_date: Optional[datetime] = Field(default=None, description="Fecha de publicación")
    
    @field_validator('title', 'description')
    @classmethod
    def sanitize_strings(cls, v: Optional[str]) -> Optional[str]:
        """Sanitizar campos de texto."""
        if v is None:
            return v
        return sanitize_string(v)


class ClassroomStudentSubmission(StrictBaseModel):
    """Modelo estricto para entrega de estudiante."""
    id: str = Field(..., min_length=1, max_length=64, description="ID de la entrega")
    course_work_id: str = Field(..., min_length=1, max_length=64, description="ID de la tarea")
    course_id: str = Field(..., min_length=1, max_length=64, description="ID del curso")
    user_id: str = Field(..., min_length=1, max_length=64, description="ID del estudiante")
    state: str = Field(default="NEW", pattern=r"^(WORK_STATE_UNSPECIFIED|NEW|CREATED|TURNED_IN|RETURNED|RECLAIMED_BY_STUDENT)$", description="Estado de entrega")
    grade: Optional[float] = Field(default=None, ge=0, description="Calificación obtenida")
    max_points: Optional[float] = Field(default=None, ge=0, description="Puntaje máximo")
    assigned_grade: Optional[float] = Field(default=None, ge=0, description="Calificación asignada")
    submission_time: Optional[datetime] = Field(default=None, description="Fecha de entrega")
    creation_time: datetime = Field(default_factory=datetime.utcnow, description="Fecha de creación")
    
    @property
    def percentage(self) -> Optional[float]:
        """Calcular porcentaje de calificación."""
        if self.assigned_grade and self.max_points and self.max_points > 0:
            return (self.assigned_grade / self.max_points) * 100
        return None


class ClassroomAgentConfig(StrictBaseModel):
    """Configuración segura para el agente de Google Classroom."""
    credentials_json: Optional[str] = Field(default=None, max_length=10000, description="Credenciales OAuth2 en JSON (cifrado)")
    service_account_file: Optional[str] = Field(default=None, max_length=500, description="Path a archivo de service account")
    token_file: Optional[str] = Field(default=None, max_length=500, description="Path a archivo de token almacenado")
    scopes: List[str] = Field(
        default=["https://www.googleapis.com/auth/classroom.courses.readonly",
                 "https://www.googleapis.com/auth/classroom.coursework.students.readonly",
                 "https://www.googleapis.com/auth/classroom.rosters.readonly"],
        description="Scopes de OAuth2 necesarios"
    )
    
    @field_validator('credentials_json')
    @classmethod
    def validate_credentials(cls, v: Optional[str]) -> Optional[str]:
        """Validar que las credenciales no sean default."""
        if v is None:
            return None
        sanitized = sanitize_string(v)
        if len(sanitized) < 50 or 'CHANGEME' in sanitized:
            raise ValueError("Credenciales inválidas. Deben provenir de variables de entorno cifradas.")
        return sanitized


class ClassroomAgent(BaseAgent):
    """
    Agente de integración con Google Classroom API.
    
    Características:
    - Sincronización de cursos, tareas y calificaciones
    - Extracción de requerimientos académicos
    - Actualización de agenda local
    - Autenticación OAuth2 con credenciales cifradas
    - Manejo de rate limits y errores de API
    - Logging y auditoría completa
    """
    
    # Scopes disponibles
    AVAILABLE_SCOPES = {
        'courses_readonly': 'https://www.googleapis.com/auth/classroom.courses.readonly',
        'coursework_readonly': 'https://www.googleapis.com/auth/classroom.coursework.students.readonly',
        'rosters_readonly': 'https://www.googleapis.com/auth/classroom.rosters.readonly',
        'guardian_readonly': 'https://www.googleapis.com/auth/classroom.guardianlinks.students.readonly',
    }
    
    # Rate limits de Classroom API
    RATE_LIMIT_QUOTA = 1000  # Requests por 100 segundos
    RATE_LIMIT_WINDOW = 100  # Ventana en segundos

    def __init__(self, config: ClassroomAgentConfig, agent_id: str = "classroom_agent_001"):
        """
        Inicializar el agente de Google Classroom.
        
        Args:
            config: Configuración con credenciales OAuth2 cifradas
            agent_id: Identificador único del agente
        """
        super().__init__(agent_name="Google Classroom Integration Agent", agent_id=agent_id)
        
        self._config = config
        self._credentials: Optional[Credentials] = None
        self._service = None
        self._request_timestamps: List[datetime] = []
        
        # Inicializar autenticación
        self._initialize_auth()
    
    def _initialize_auth(self) -> None:
        """Inicializar autenticación con Google Classroom API."""
        try:
            if self._config.service_account_file:
                # Usar service account
                self._credentials = service_account.Credentials.from_service_account_file(
                    self._config.service_account_file,
                    scopes=self._config.scopes
                )
            elif self._config.credentials_json:
                # Usar credenciales JSON
                import json
                creds_info = json.loads(self._config.credentials_json)
                self._credentials = Credentials.from_authorized_user_info(creds_info, self._config.scopes)
            else:
                logger.warning("No se proporcionaron credenciales. La autenticación fallará.")
            
            if self._credentials:
                self._service = build('classroom', 'v1', credentials=self._credentials)
                logger.info("Servicio de Classroom inicializado correctamente")
                
        except Exception as e:
            logger.error(f"Error al inicializar autenticación: {e}")
            raise
    
    async def _check_rate_limit(self) -> None:
        """Verificar y respetar rate limits de la API."""
        now = datetime.utcnow()
        cutoff = now - timedelta(seconds=self.RATE_LIMIT_WINDOW)
        
        # Limpiar timestamps antiguos
        self._request_timestamps = [ts for ts in self._request_timestamps if ts > cutoff]
        
        if len(self._request_timestamps) >= self.RATE_LIMIT_QUOTA:
            wait_time = self.RATE_LIMIT_WINDOW
            logger.warning(f"Rate limit alcanzado. Esperando {wait_time}s")
            await asyncio.sleep(wait_time)
            self._request_timestamps = []
        
        self._request_timestamps.append(now)
    
    async def _make_api_request(self, request_func, *args, **kwargs):
        """
        Ejecutar una request a la API con manejo de rate limits y reintentos.
        
        Args:
            request_func: Función a ejecutar
            *args, **kwargs: Argumentos para la función
            
        Returns:
            Resultado de la request
        """
        await self._check_rate_limit()
        
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None,
                    lambda: request_func(*args, **kwargs)
                )
                return result
            except HttpError as e:
                if e.resp.status == 429:  # Rate limit
                    retry_count += 1
                    wait_time = (2 ** retry_count)  # Backoff exponencial
                    logger.warning(f"Rate limit. Reintentando en {wait_time}s (intento {retry_count}/{max_retries})")
                    await asyncio.sleep(wait_time)
                else:
                    raise
            except Exception as e:
                logger.error(f"Error en request: {e}")
                raise
        
        raise Exception("Max retries exceeded")
    
    async def list_courses(self, teacher_id: Optional[str] = None) -> List[ClassroomCourse]:
        """
        Listar cursos de Google Classroom.
        
        Args:
            teacher_id: ID del profesor para filtrar (None para todos los accesibles)
            
        Returns:
            Lista de cursos
        """
        try:
            request = self._service.courses().list(teacherId=teacher_id) if teacher_id else self._service.courses().list()
            
            courses_data = await self._make_api_request(request.execute)
            courses_list = courses_data.get('courses', [])
            
            courses = []
            for course_data in courses_list:
                try:
                    course = ClassroomCourse(
                        id=course_data.get('id', ''),
                        name=course_data.get('name', ''),
                        section=course_data.get('section'),
                        description=course_data.get('description'),
                        owner_id=course_data.get('ownerId', ''),
                        course_state=course_data.get('courseState', 'ACTIVE')
                    )
                    courses.append(course)
                except Exception as e:
                    logger.warning(f"Error procesando curso: {e}")
                    continue
            
            logger.info(f"Se listaron {len(courses)} cursos")
            return courses
            
        except HttpError as e:
            logger.error(f"Error listando cursos: {e}")
            raise
    
    async def get_course(self, course_id: str) -> Optional[ClassroomCourse]:
        """
        Obtener detalles de un curso específico.
        
        Args:
            course_id: ID del curso
            
        Returns:
            Curso o None si no existe
        """
        try:
            request = self._service.courses().get(id=course_id)
            course_data = await self._make_api_request(request.execute)
            
            return ClassroomCourse(
                id=course_data.get('id', ''),
                name=course_data.get('name', ''),
                section=course_data.get('section'),
                description=course_data.get('description'),
                owner_id=course_data.get('ownerId', ''),
                course_state=course_data.get('courseState', 'ACTIVE')
            )
            
        except HttpError as e:
            if e.resp.status == 404:
                return None
            logger.error(f"Error obteniendo curso: {e}")
            raise
    
    async def list_coursework(
        self, 
        course_id: str,
        work_types: Optional[List[str]] = None
    ) -> List[ClassroomAssignment]:
        """
        Listar tareas/trabajos de un curso.
        
        Args:
            course_id: ID del curso
            work_types: Filtrar por tipos de trabajo (None para todos)
            
        Returns:
            Lista de tareas
        """
        try:
            request = self._service.courses().courseWork().list(
                courseId=course_id,
                workStates=['PUBLISHED']
            )
            
            coursework_data = await self._make_api_request(request.execute)
            coursework_list = coursework_data.get('courseWork', [])
            
            assignments = []
            for cw_data in coursework_list:
                # Filtrar por tipo si se especificó
                if work_types and cw_data.get('workType') not in work_types:
                    continue
                
                try:
                    # Parsear fecha de vencimiento
                    due_date = None
                    if cw_data.get('dueDate'):
                        due = cw_data['dueDate']
                        due_time = cw_data.get('dueTime', {})
                        due_date = datetime(
                            year=due.get('year', 2000),
                            month=due.get('month', 1),
                            day=due.get('day', 1),
                            hour=due_time.get('hours', 0),
                            minute=due_time.get('minutes', 0)
                        )
                    
                    # Parsear fecha de publicación
                    share_date = None
                    if cw_data.get('assignmentShareDate'):
                        share_date = datetime.fromisoformat(
                            cw_data['assignmentShareDate'].replace('Z', '+00:00')
                        )
                    
                    assignment = ClassroomAssignment(
                        id=cw_data.get('id', ''),
                        course_id=course_id,
                        title=cw_data.get('title', ''),
                        description=cw_data.get('description'),
                        state=cw_data.get('state', 'DRAFT'),
                        due_date=due_date,
                        max_points=cw_data.get('maxPoints'),
                        work_type=cw_data.get('workType', 'ASSIGNMENT'),
                        assignment_share_date=share_date
                    )
                    assignments.append(assignment)
                except Exception as e:
                    logger.warning(f"Error procesando tarea: {e}")
                    continue
            
            logger.info(f"Se listaron {len(assignments)} tareas del curso {course_id}")
            return assignments
            
        except HttpError as e:
            logger.error(f"Error listando tareas: {e}")
            raise
    
    async def get_student_submissions(
        self,
        course_id: str,
        course_work_id: str,
        student_id: Optional[str] = None
    ) -> List[ClassroomStudentSubmission]:
        """
        Obtener entregas de estudiantes para una tarea.
        
        Args:
            course_id: ID del curso
            course_work_id: ID de la tarea
            student_id: ID de estudiante específico (None para todos)
            
        Returns:
            Lista de entregas
        """
        try:
            request = self._service.courses().courseWork().studentSubmissions().list(
                courseId=course_id,
                courseWorkId=course_work_id,
                userId=student_id if student_id else '-'
            )
            
            submissions_data = await self._make_api_request(request.execute)
            submissions_list = submissions_data.get('studentSubmissions', [])
            
            submissions = []
            for sub_data in submissions_list:
                try:
                    # Parsear fechas
                    submission_time = None
                    if sub_data.get('submissionHistory'):
                        history = sub_data['submissionHistory']
                        if history:
                            last_entry = history[-1]
                            if 'turnIn' in last_entry:
                                submission_time = datetime.fromisoformat(
                                    last_entry['turnIn']['timestamp'].replace('Z', '+00:00')
                                )
                    
                    submission = ClassroomStudentSubmission(
                        id=sub_data.get('id', ''),
                        course_work_id=course_work_id,
                        course_id=course_id,
                        user_id=sub_data.get('userId', ''),
                        state=sub_data.get('state', 'NEW'),
                        grade=sub_data.get('grade'),
                        max_points=sub_data.get('maxPoints'),
                        assigned_grade=sub_data.get('assignedGrade'),
                        submission_time=submission_time
                    )
                    submissions.append(submission)
                except Exception as e:
                    logger.warning(f"Error procesando entrega: {e}")
                    continue
            
            logger.info(f"Se listaron {len(submissions)} entregas")
            return submissions
            
        except HttpError as e:
            logger.error(f"Error obteniendo entregas: {e}")
            raise
    
    async def extract_academic_requirements(self, course_ids: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Extraer requerimientos académicos de cursos y tareas.
        
        Args:
            course_ids: Lista de IDs de cursos (None para todos)
            
        Returns:
            Diccionario con requerimientos extraídos
        """
        requirements = {
            "courses": [],
            "assignments": [],
            "deadlines": [],
            "grading_criteria": []
        }
        
        # Obtener cursos
        if course_ids:
            courses = []
            for cid in course_ids:
                course = await self.get_course(cid)
                if course:
                    courses.append(course)
        else:
            courses = await self.list_courses()
        
        for course in courses:
            requirements["courses"].append({
                "id": course.id,
                "name": course.name,
                "section": course.section
            })
            
            # Obtener tareas del curso
            assignments = await self.list_coursework(course.id)
            
            for assignment in assignments:
                req = {
                    "course_id": course.id,
                    "course_name": course.name,
                    "assignment_id": assignment.id,
                    "title": assignment.title,
                    "description": assignment.description,
                    "max_points": assignment.max_points,
                    "work_type": assignment.work_type
                }
                requirements["assignments"].append(req)
                
                # Extraer deadlines
                if assignment.due_date:
                    requirements["deadlines"].append({
                        "assignment_id": assignment.id,
                        "title": assignment.title,
                        "due_date": assignment.due_date.isoformat(),
                        "days_remaining": (assignment.due_date - datetime.utcnow()).days
                    })
        
        logger.info(f"Requerimientos académicos extraídos: {len(requirements['assignments'])} tareas")
        return requirements
    
    async def sync_to_local_agenda(self, output_path: str) -> Dict[str, Any]:
        """
        Sincronizar tareas y plazos a una agenda local (archivo JSON).
        
        Args:
            output_path: Path donde guardar la agenda sincronizada
            
        Returns:
            Resumen de la sincronización
        """
        import json
        from ai_engine.core.security.path_validator import validate_path
        
        # Validar path seguro
        workspace = os.environ.get('HELIOS_WORKSPACE', '/workspace')
        validated_path = validate_path(workspace, output_path)
        
        # Extraer requerimientos
        requirements = await self.extract_academic_requirements()
        
        # Crear estructura de agenda
        agenda = {
            "sync_timestamp": datetime.utcnow().isoformat(),
            "total_courses": len(requirements["courses"]),
            "total_assignments": len(requirements["assignments"]),
            "upcoming_deadlines": sorted(
                requirements["deadlines"],
                key=lambda x: x.get("due_date", "")
            ),
            "courses": requirements["courses"],
            "assignments_by_course": {}
        }
        
        # Organizar por curso
        for assignment in requirements["assignments"]:
            cid = assignment["course_id"]
            if cid not in agenda["assignments_by_course"]:
                agenda["assignments_by_course"][cid] = []
            agenda["assignments_by_course"][cid].append(assignment)
        
        # Guardar archivo
        with open(validated_path, 'w', encoding='utf-8') as f:
            json.dump(agenda, f, indent=2, ensure_ascii=False)
        
        await self.log_action("sync_to_local_agenda", {
            "output_path": str(validated_path),
            "courses_synced": len(requirements["courses"]),
            "assignments_synced": len(requirements["assignments"])
        })
        
        logger.info(f"Agenda sincronizada en {validated_path}")
        
        return {
            "success": True,
            "output_path": str(validated_path),
            "courses_synced": len(requirements["courses"]),
            "assignments_synced": len(requirements["assignments"]),
            "deadline_count": len(requirements["deadlines"])
        }
    
    async def execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Ejecutar una tarea del agente de Classroom.
        
        Args:
            task: Diccionario con parámetros de la tarea
            
        Returns:
            Resultado de la ejecución
        """
        operation = task.get("operation")
        
        operations = {
            "list_courses": lambda: self.list_courses(teacher_id=task.get("teacher_id")),
            "get_course": lambda: self.get_course(course_id=task.get("course_id")),
            "list_coursework": lambda: self.list_coursework(
                course_id=task.get("course_id"),
                work_types=task.get("work_types")
            ),
            "get_submissions": lambda: self.get_student_submissions(
                course_id=task.get("course_id"),
                course_work_id=task.get("course_work_id"),
                student_id=task.get("student_id")
            ),
            "extract_requirements": lambda: self.extract_academic_requirements(
                course_ids=task.get("course_ids")
            ),
            "sync_agenda": lambda: self.sync_to_local_agenda(output_path=task.get("output_path", "agenda.json")),
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
        Verificar si el agente está autorizado para acceder a un recurso.
        
        Args:
            target: Recurso a verificar (curso, usuario, etc.)
            
        Returns:
            True si está autorizado, False en caso contrario
        """
        # Verificar que las credenciales sean válidas
        if not self._credentials:
            return False
        
        # Verificar que el servicio esté inicializado
        if not self._service:
            return False
        
        # Para cursos, verificar acceso
        if target.startswith("course:"):
            course_id = target.replace("course:", "")
            try:
                course = self._service.courses().get(id=course_id).execute()
                return course is not None
            except HttpError:
                return False
        
        # Por defecto, asumir autorizado si hay credenciales válidas
        return True
    
    async def log_action(self, action: str, context: Dict[str, Any]) -> None:
        """
        Registrar una acción para auditoría.
        
        Args:
            action: Nombre de la acción
            context: Contexto adicional de la acción
        """
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "agent_id": self.agent_id,
            "action": action,
            "context": context
        }
        
        logger.info(f"[AUDIT] {log_entry}")
    
    def refresh_credentials(self, new_credentials: str) -> None:
        """
        Actualizar credenciales OAuth2.
        
        Args:
            new_credentials: Nuevas credenciales en formato JSON
        """
        import json
        self._config.credentials_json = new_credentials
        creds_info = json.loads(new_credentials)
        self._credentials = Credentials.from_authorized_user_info(creds_info, self._config.scopes)
        self._service = build('classroom', 'v1', credentials=self._credentials)
        logger.info("Credenciales actualizadas")
    
    @property
    def is_authenticated(self) -> bool:
        """Verificar si hay credenciales válidas."""
        return self._credentials is not None and self._service is not None
