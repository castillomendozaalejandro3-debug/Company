"""
Instagram Agent for Helios AI Engine

Integración con Instagram Graph API (Meta for Developers) para gestión de DMs y comentarios.
Implementa autenticación OAuth2, manejo de rate limits y respuestas automatizadas contextuales.
"""

import asyncio
import logging
import re
import time
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from enum import Enum

import requests
from pydantic import BaseModel, Field, field_validator, ConfigDict

from ai_engine.agents.base_agent import BaseAgent
from ai_engine.core.schemas import StrictBaseModel, sanitize_string

logger = logging.getLogger(__name__)


class InstagramMediaType(str, Enum):
    """Tipos de medios soportados por Instagram."""
    IMAGE = "IMAGE"
    VIDEO = "VIDEO"
    CAROUSEL_ALBUM = "CAROUSEL_ALBUM"
    STORIES = "STORIES"
    REELS = "REELS"


class CommentType(str, Enum):
    """Tipos de comentarios."""
    COMMENT = "comment"
    REPLY = "reply"
    MENTION = "mention"


class MessageIntent(str, Enum):
    """Tipos de intenciones para mensajes/interacciones."""
    GREETING = "greeting"
    INQUIRY = "inquiry"
    COMPLAINT = "complaint"
    COMPLIMENT = "compliment"
    SPAM = "spam"
    COLLABORATION = "collaboration"
    SUPPORT = "support"
    UNKNOWN = "unknown"


class InstagramMessage(StrictBaseModel):
    """Modelo estricto para mensajes de Instagram."""
    id: str = Field(..., min_length=1, max_length=64, description="ID del mensaje")
    from_user_id: str = Field(..., min_length=1, max_length=64, description="ID del usuario remitente")
    from_username: Optional[str] = Field(default=None, max_length=64, description="Username del remitente")
    text: str = Field(..., min_length=1, max_length=1000, description="Texto del mensaje")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Timestamp del mensaje")
    media_id: Optional[str] = Field(default=None, max_length=64, description="ID del medio asociado")
    message_type: str = Field(default="text", pattern=r"^(text|media|share)$", description="Tipo de mensaje")
    
    @field_validator('text')
    @classmethod
    def sanitize_text(cls, v: str) -> str:
        """Sanitizar el texto del mensaje."""
        return sanitize_string(v)


class InstagramComment(StrictBaseModel):
    """Modelo estricto para comentarios de Instagram."""
    id: str = Field(..., min_length=1, max_length=64, description="ID del comentario")
    user_id: str = Field(..., min_length=1, max_length=64, description="ID del usuario")
    username: Optional[str] = Field(default=None, max_length=64, description="Username del comentarista")
    text: str = Field(..., min_length=1, max_length=2000, description="Texto del comentario")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Timestamp del comentario")
    media_id: str = Field(..., min_length=1, max_length=64, description="ID del medio comentado")
    like_count: int = Field(default=0, ge=0, description="Cantidad de likes")
    reply_count: int = Field(default=0, ge=0, description="Cantidad de respuestas")
    
    @field_validator('text')
    @classmethod
    def sanitize_text(cls, v: str) -> str:
        """Sanitizar el texto del comentario."""
        return sanitize_string(v)


class InstagramAgentConfig(StrictBaseModel):
    """Configuración segura para el agente de Instagram."""
    app_id: str = Field(..., min_length=5, max_length=64, description="App ID de Meta")
    app_secret: str = Field(..., min_length=10, max_length=128, description="App Secret de Meta")
    access_token: str = Field(..., min_length=10, max_length=512, description="Access Token OAuth2")
    instagram_business_account_id: str = Field(..., min_length=1, max_length=64, description="ID de cuenta business")
    webhook_verify_token: Optional[str] = Field(default=None, max_length=128, description="Token para verificar webhooks")
    
    @field_validator('app_id', 'app_secret', 'access_token')
    @classmethod
    def validate_credentials(cls, v: str) -> str:
        """Validar que las credenciales no sean default."""
        sanitized = sanitize_string(v)
        if len(sanitized) < 10 or sanitized in ('your_app_id', 'your_app_secret', 'CHANGEME'):
            raise ValueError("Credenciales inválidas. Deben provenir de variables de entorno cifradas.")
        return sanitized


class RateLimitInfo(BaseModel):
    """Información de rate limit de la API."""
    model_config = ConfigDict(extra='forbid')
    
    calls_remaining: int
    calls_total: int
    reset_time: datetime
    is_limited: bool = False


class InstagramAgent(BaseAgent):
    """
    Agente de integración con Instagram Graph API.
    
    Características:
    - Lectura de DMs y comentarios
    - Respuestas automatizadas con contexto conversacional
    - Manejo de rate limits y reintentos exponenciales
    - Autenticación OAuth2 con refresh token
    - Detección de spam y moderación básica
    - Logging y auditoría completa
    """
    
    # Endpoint base de Instagram Graph API
    GRAPH_API_BASE = "https://graph.facebook.com/v18.0"
    
    # Rate limits por defecto (ajustables según tier de API)
    DEFAULT_RATE_LIMIT_CALLS = 200
    DEFAULT_RATE_LIMIT_WINDOW = 3600  # 1 hora
    
    # Patrones de spam
    SPAM_PATTERNS = [
        r'\b(free|gratis|ganador|winner|click here|haga clic)\b.*\b(url|link|http)\b',
        r'\b(seguime|follow me|follow back)\b.*\b(te sigo|i follow you)\b',
        r'(.)\1{4,}',  # Caracteres repetidos
        r'\b\d{10,}\b',  # Números largos
    ]
    
    # Patrones de intenciones
    INTENT_PATTERNS = {
        MessageIntent.GREETING: [r'\b(hola|hi|hello|hey|buenos|buenas)\b'],
        MessageIntent.INQUIRY: [r'\b(precio|info|información|details|cómo|cuándo|dónde|what|how)\b'],
        MessageIntent.COMPLAINT: [r'\b(problema|error|malo|bad|terrible|no funciona|issue)\b'],
        MessageIntent.COMPLIMENT: [r'\b(excelente|genial|awesome|great|love|encanta|hermoso)\b'],
        MessageIntent.COLLABORATION: [r'\b(colab|collaboration|partnership|marca|brand|promo)\b'],
        MessageIntent.SUPPORT: [r'\b(ayuda|help|soporte|support|asistencia)\b'],
    }

    def __init__(self, config: InstagramAgentConfig, agent_id: str = "instagram_agent_001"):
        """
        Inicializar el agente de Instagram.
        
        Args:
            config: Configuración con credenciales OAuth2
            agent_id: Identificador único del agente
        """
        super().__init__(agent_name="Instagram Integration Agent", agent_id=agent_id)
        
        self._config = config
        self._session = requests.Session()
        self._rate_limit_info: Optional[RateLimitInfo] = None
        self._last_request_time: float = 0
        self._min_request_interval = 0.5  # 500ms entre requests
        
        # Inicializar rate limit tracker
        self._reset_rate_limit()
    
    def _reset_rate_limit(self) -> None:
        """Resetear información de rate limit."""
        self._rate_limit_info = RateLimitInfo(
            calls_remaining=self.DEFAULT_RATE_LIMIT_CALLS,
            calls_total=self.DEFAULT_RATE_LIMIT_CALLS,
            reset_time=datetime.utcnow() + timedelta(seconds=self.DEFAULT_RATE_LIMIT_WINDOW)
        )
    
    def _extract_intent(self, text: str) -> MessageIntent:
        """
        Extraer la intención de un texto.
        
        Args:
            text: Texto a analizar
            
        Returns:
            Intención detectada
        """
        text_lower = text.lower()
        
        for intent, patterns in self.INTENT_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, text_lower, re.IGNORECASE):
                    logger.debug(f"Intención detectada: {intent.value}")
                    return intent
        
        return MessageIntent.UNKNOWN
    
    def _is_spam(self, text: str) -> bool:
        """
        Detectar si un texto es potencial spam.
        
        Args:
            text: Texto a analizar
            
        Returns:
            True si parece spam, False en caso contrario
        """
        for pattern in self.SPAM_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False
    
    def _generate_contextual_response(self, intent: MessageIntent, original_text: str) -> str:
        """
        Generar respuesta contextual basada en la intención.
        
        Args:
            intent: Intención detectada
            original_text: Texto original
            
        Returns:
            Respuesta generada
        """
        responses = {
            MessageIntent.GREETING: "¡Hola! 👋 Gracias por contactarnos. ¿En qué podemos ayudarte?",
            MessageIntent.INQUIRY: "Gracias por tu interés. Te compartimos toda la información que necesitas. 📋",
            MessageIntent.COMPLAINT: "Lamentamos escuchar esto. Por favor envíanos un DM con más detalles para resolverlo. 😔",
            MessageIntent.COMPLIMENT: "¡Muchas gracias por tus palabras! Nos motiva a seguir mejorando. ❤️",
            MessageIntent.COLLABORATION: "¡Nos encantaría colaborar! Envíanos un email a partnerships@empresa.com 🤝",
            MessageIntent.SUPPORT: "Estamos aquí para ayudarte. Cuéntanos más sobre tu consulta. 💬",
            MessageIntent.UNKNOWN: "Gracias por tu mensaje. ¿Podrías darnos más detalles? 🙏",
        }
        
        return responses.get(intent, responses[MessageIntent.UNKNOWN])
    
    async def _wait_for_rate_limit(self) -> None:
        """Esperar si es necesario para respetar rate limits."""
        if self._rate_limit_info and self._rate_limit_info.is_limited:
            wait_time = (self._rate_limit_info.reset_time - datetime.utcnow()).total_seconds()
            if wait_time > 0:
                logger.warning(f"Rate limit alcanzado. Esperando {wait_time:.2f}s")
                await asyncio.sleep(min(wait_time, 60))  # Máximo 60s
                self._reset_rate_limit()
        
        # Respetar intervalo mínimo entre requests
        elapsed = time.time() - self._last_request_time
        if elapsed < self._min_request_interval:
            await asyncio.sleep(self._min_request_interval - elapsed)
        
        self._last_request_time = time.time()
    
    def _make_api_request(
        self, 
        method: str, 
        endpoint: str, 
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Realizar una request a la API de Instagram con manejo de errores.
        
        Args:
            method: Método HTTP (GET, POST, etc.)
            endpoint: Endpoint relativo
            params: Parámetros query
            data: Datos del body (para POST)
            
        Returns:
            Respuesta de la API como dict
            
        Raises:
            requests.RequestException: Si la request falla
        """
        url = f"{self.GRAPH_API_BASE}/{endpoint}"
        
        # Agregar access token a los parámetros
        if params is None:
            params = {}
        params['access_token'] = self._config.access_token
        
        try:
            response = self._session.request(
                method=method,
                url=url,
                params=params,
                json=data,
                timeout=30
            )
            
            # Actualizar rate limit info desde headers
            if 'x-app-usage' in response.headers:
                usage = response.headers['x-app-usage']
                # Parsear usage header si está disponible
                logger.debug(f"API Usage: {usage}")
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                self._rate_limit_info.is_limited = True
                logger.error("Rate limit excedido")
            elif e.response.status_code == 401:
                logger.error("Token expirado o inválido")
            raise
    
    async def read_messages(self, limit: int = 50) -> List[InstagramMessage]:
        """
        Leer mensajes directos (DMs) de Instagram.
        
        Args:
            limit: Cantidad máxima de mensajes a recuperar
            
        Returns:
            Lista de mensajes recuperados
        """
        await self._wait_for_rate_limit()
        
        try:
            endpoint = f"{self._config.instagram_business_account_id}/conversations"
            params = {
                'fields': 'messages{id,from,to,text,timestamp,attachments},from',
                'limit': limit
            }
            
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._make_api_request('GET', endpoint, params=params)
            )
            
            messages = []
            conversations = result.get('data', [])
            
            for conv in conversations:
                conv_messages = conv.get('messages', {}).get('data', [])
                for msg_data in conv_messages:
                    try:
                        from_user = msg_data.get('from', {})
                        message = InstagramMessage(
                            id=msg_data.get('id', ''),
                            from_user_id=from_user.get('id', ''),
                            from_username=from_user.get('username'),
                            text=msg_data.get('text', ''),
                            timestamp=datetime.fromisoformat(msg_data.get('timestamp', '').replace('Z', '+00:00')) if msg_data.get('timestamp') else datetime.utcnow(),
                            message_type='media' if msg_data.get('attachments') else 'text'
                        )
                        messages.append(message)
                    except Exception as e:
                        logger.warning(f"Error procesando mensaje: {e}")
                        continue
            
            logger.info(f"Se leyeron {len(messages)} mensajes de Instagram")
            return messages
            
        except Exception as e:
            logger.error(f"Error leyendo mensajes: {e}")
            raise
    
    async def read_comments(
        self, 
        media_id: Optional[str] = None,
        limit: int = 100
    ) -> List[InstagramComment]:
        """
        Leer comentarios de publicaciones de Instagram.
        
        Args:
            media_id: ID específico de medio (None para todos)
            limit: Cantidad máxima de comentarios
            
        Returns:
            Lista de comentarios recuperados
        """
        await self._wait_for_rate_limit()
        
        try:
            if media_id:
                endpoint = f"{media_id}/comments"
            else:
                endpoint = f"{self._config.instagram_business_account_id}/media"
                params = {
                    'fields': 'comments{id,from,text,timestamp,like_count,hidden},from',
                    'limit': limit
                }
                
                media_result = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: self._make_api_request('GET', endpoint, params=params)
                )
                
                comments = []
                for media in media_result.get('data', []):
                    media_comments = media.get('comments', {}).get('data', [])
                    for comment_data in media_comments:
                        try:
                            from_user = comment_data.get('from', {})
                            comment = InstagramComment(
                                id=comment_data.get('id', ''),
                                user_id=from_user.get('id', ''),
                                username=from_user.get('username'),
                                text=comment_data.get('text', ''),
                                timestamp=datetime.fromisoformat(comment_data.get('timestamp', '').replace('Z', '+00:00')) if comment_data.get('timestamp') else datetime.utcnow(),
                                media_id=media.get('id', ''),
                                like_count=comment_data.get('like_count', 0),
                                reply_count=comment_data.get('comment_count', 0)
                            )
                            comments.append(comment)
                        except Exception as e:
                            logger.warning(f"Error procesando comentario: {e}")
                            continue
                
                return comments
            
            # Caso específico de un medio
            params = {
                'fields': 'id,from,text,timestamp,like_count,comment_count,hidden',
                'limit': limit
            }
            
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._make_api_request('GET', endpoint, params=params)
            )
            
            comments = []
            for comment_data in result.get('data', []):
                try:
                    from_user = comment_data.get('from', {})
                    comment = InstagramComment(
                        id=comment_data.get('id', ''),
                        user_id=from_user.get('id', ''),
                        username=from_user.get('username'),
                        text=comment_data.get('text', ''),
                        timestamp=datetime.fromisoformat(comment_data.get('timestamp', '').replace('Z', '+00:00')) if comment_data.get('timestamp') else datetime.utcnow(),
                        media_id=media_id,
                        like_count=comment_data.get('like_count', 0),
                        reply_count=comment_data.get('comment_count', 0)
                    )
                    comments.append(comment)
                except Exception as e:
                    logger.warning(f"Error procesando comentario: {e}")
                    continue
            
            logger.info(f"Se leyeron {len(comments)} comentarios")
            return comments
            
        except Exception as e:
            logger.error(f"Error leyendo comentarios: {e}")
            raise
    
    async def send_message(self, recipient_id: str, message: str) -> Dict[str, Any]:
        """
        Enviar un mensaje directo a un usuario de Instagram.
        
        Args:
            recipient_id: ID del usuario destinatario
            message: Texto del mensaje
            
        Returns:
            Resultado del envío
        """
        await self._wait_for_rate_limit()
        
        # Validar que no sea spam
        if self._is_spam(message):
            raise ValueError("El mensaje contiene patrones de spam")
        
        try:
            endpoint = f"{self._config.instagram_business_account_id}/messages"
            data = {
                'recipient': {'id': recipient_id},
                'message': {'text': message}
            }
            
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._make_api_request('POST', endpoint, data=data)
            )
            
            await self.log_action("send_message", {
                "recipient_id": recipient_id,
                "message_id": result.get('message_id'),
                "status": "sent"
            })
            
            logger.info(f"Mensaje enviado a {recipient_id}")
            
            return {
                "success": True,
                "message_id": result.get('message_id'),
                "recipient_id": recipient_id,
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error enviando mensaje: {e}")
            await self.log_action("send_message_failed", {
                "recipient_id": recipient_id,
                "error": str(e)
            })
            raise
    
    async def reply_to_comment(
        self, 
        comment_id: str, 
        reply_text: str
    ) -> Dict[str, Any]:
        """
        Responder a un comentario.
        
        Args:
            comment_id: ID del comentario original
            reply_text: Texto de la respuesta
            
        Returns:
            Resultado de la respuesta
        """
        await self._wait_for_rate_limit()
        
        if self._is_spam(reply_text):
            raise ValueError("La respuesta contiene patrones de spam")
        
        try:
            endpoint = f"{comment_id}/comments"
            data = {
                'message': reply_text
            }
            
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._make_api_request('POST', endpoint, data=data)
            )
            
            await self.log_action("reply_to_comment", {
                "comment_id": comment_id,
                "reply_id": result.get('id'),
                "status": "sent"
            })
            
            logger.info(f"Respuesta enviada al comentario {comment_id}")
            
            return {
                "success": True,
                "comment_id": result.get('id'),
                "parent_comment_id": comment_id,
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error respondiendo comentario: {e}")
            raise
    
    async def auto_respond_to_comments(
        self,
        media_id: Optional[str] = None,
        custom_rules: Optional[Dict[str, str]] = None,
        skip_spam: bool = True
    ) -> Dict[str, Any]:
        """
        Responder automáticamente a comentarios nuevos.
        
        Args:
            media_id: ID de medio específico (None para todos)
            custom_rules: Reglas personalizadas {patrón: respuesta}
            skip_spam: Saltar comentarios detectados como spam
            
        Returns:
            Resultados de las respuestas enviadas
        """
        comments = await self.read_comments(media_id=media_id, limit=50)
        
        results = {
            "processed": 0,
            "responded": 0,
            "skipped_spam": 0,
            "errors": []
        }
        
        for comment in comments:
            try:
                # Saltar spam si está habilitado
                if skip_spam and self._is_spam(comment.text):
                    logger.info(f"Comentario spam saltado: {comment.id}")
                    results["skipped_spam"] += 1
                    continue
                
                # Extraer intención
                intent = self._extract_intent(comment.text)
                
                # Verificar reglas personalizadas
                response_text = None
                if custom_rules:
                    for pattern, response in custom_rules.items():
                        if re.search(pattern, comment.text, re.IGNORECASE):
                            response_text = response
                            break
                
                # Usar respuesta contextual si no hay regla personalizada
                if not response_text:
                    response_text = self._generate_contextual_response(intent, comment.text)
                
                # Enviar respuesta
                await self.reply_to_comment(comment.id, response_text)
                results["responded"] += 1
                
            except Exception as e:
                error_msg = f"Error procesando comentario {comment.id}: {str(e)}"
                logger.error(error_msg)
                results["errors"].append({
                    "comment_id": comment.id,
                    "error": error_msg
                })
            
            results["processed"] += 1
        
        await self.log_action("auto_respond_comments", results)
        return results
    
    async def hide_comment(self, comment_id: str) -> Dict[str, Any]:
        """
        Ocultar un comentario (moderación).
        
        Args:
            comment_id: ID del comentario a ocultar
            
        Returns:
            Resultado de la operación
        """
        await self._wait_for_rate_limit()
        
        try:
            endpoint = f"{comment_id}/hide"
            data = {'hidden': True}
            
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._make_api_request('POST', endpoint, data=data)
            )
            
            await self.log_action("hide_comment", {
                "comment_id": comment_id,
                "status": "hidden"
            })
            
            logger.info(f"Comentario ocultado: {comment_id}")
            
            return {
                "success": True,
                "comment_id": comment_id,
                "action": "hidden",
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error ocultando comentario: {e}")
            raise
    
    async def execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Ejecutar una tarea del agente de Instagram.
        
        Args:
            task: Diccionario con parámetros de la tarea
            
        Returns:
            Resultado de la ejecución
        """
        operation = task.get("operation")
        
        operations = {
            "read_messages": lambda: self.read_messages(limit=task.get("limit", 50)),
            "read_comments": lambda: self.read_comments(
                media_id=task.get("media_id"),
                limit=task.get("limit", 100)
            ),
            "send_message": lambda: self.send_message(
                recipient_id=task.get("recipient_id"),
                message=task.get("message")
            ),
            "reply_to_comment": lambda: self.reply_to_comment(
                comment_id=task.get("comment_id"),
                reply_text=task.get("reply_text")
            ),
            "auto_respond": lambda: self.auto_respond_to_comments(
                media_id=task.get("media_id"),
                custom_rules=task.get("custom_rules"),
                skip_spam=task.get("skip_spam", True)
            ),
            "hide_comment": lambda: self.hide_comment(comment_id=task.get("comment_id")),
            "detect_intent": lambda: self._extract_intent(task.get("text", "")).value,
            "is_spam": lambda: self._is_spam(task.get("text", "")),
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
        Verificar si un usuario está autorizado para interactuar.
        
        Args:
            target: User ID o username a verificar
            
        Returns:
            True si está autorizado, False en caso contrario
        """
        # Implementar lógica de autorización específica
        # Por defecto, permitir todos menos usuarios bloqueados
        blocked_users = []  # Cargar desde configuración
        return target not in blocked_users
    
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
    
    def refresh_access_token(self, new_token: str) -> None:
        """
        Actualizar el access token (para refresh OAuth2).
        
        Args:
            new_token: Nuevo access token
        """
        self._config.access_token = new_token
        logger.info("Access token actualizado")
    
    @property
    def rate_limit_status(self) -> Optional[RateLimitInfo]:
        """Obtener estado actual del rate limit."""
        return self._rate_limit_info
