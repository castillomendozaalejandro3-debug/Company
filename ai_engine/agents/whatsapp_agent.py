"""
WhatsApp Agent for Helios AI Engine

Integración con WhatsApp Business API usando Twilio para mensajería empresarial.
Implementa métodos asíncronos para envío, lectura y respuesta automática de mensajes.
Incluye validación estricta de números telefónicos y prevención de exfiltración de datos (DPI).
"""

import asyncio
import logging
import re
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum

from twilio.rest import Client as TwilioClient
from twilio.base.exceptions import TwilioRestException
from pydantic import BaseModel, Field, field_validator, ConfigDict

from ai_engine.agents.base_agent import BaseAgent
from ai_engine.core.security.path_validator import validate_path, sanitize_path
from ai_engine.core.schemas import StrictBaseModel, sanitize_string

logger = logging.getLogger(__name__)


class PhoneNumberCountryCode(str, Enum):
    """Códigos de país válidos para números telefónicos."""
    AR = "+54"      # Argentina
    US = "+1"       # Estados Unidos
    MX = "+52"      # México
    ES = "+34"      # España
    CO = "+57"      # Colombia
    CL = "+56"      # Chile
    PE = "+51"      # Perú
    BR = "+55"      # Brasil
    UK = "+44"      # Reino Unido
    DE = "+49"      # Alemania
    FR = "+33"      # Francia
    IT = "+39"      # Italia
    JP = "+81"      # Japón
    CN = "+86"      # China
    IN = "+91"      # India
    AU = "+61"      # Australia
    CA = "+1"       # Canadá


class MessageIntent(str, Enum):
    """Tipos de intenciones extraídas de mensajes."""
    GREETING = "greeting"
    FAREWELL = "farewell"
    QUESTION = "question"
    COMMAND = "command"
    INFORMATION_REQUEST = "information_request"
    COMPLAINT = "complaint"
    SUPPORT = "support"
    SALES = "sales"
    UNKNOWN = "unknown"


class WhatsAppMessage(StrictBaseModel):
    """Modelo estricto para mensajes de WhatsApp."""
    from_number: str = Field(..., min_length=8, max_length=20, description="Número del remitente")
    to_number: str = Field(..., min_length=8, max_length=20, description="Número del destinatario")
    body: str = Field(..., min_length=1, max_length=4096, description="Cuerpo del mensaje")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Timestamp del mensaje")
    message_sid: Optional[str] = Field(default=None, max_length=64, description="SID del mensaje")
    direction: str = Field(default="inbound", pattern=r"^(inbound|outbound)$", description="Dirección del mensaje")
    
    @field_validator('from_number', 'to_number')
    @classmethod
    def validate_phone_number(cls, v: str) -> str:
        """Validar formato de número telefónico."""
        sanitized = sanitize_string(v)
        if not cls._is_valid_phone(sanitized):
            raise ValueError(f"Número telefónico inválido: {sanitized}")
        return sanitized
    
    @field_validator('body')
    @classmethod
    def sanitize_body(cls, v: str) -> str:
        """Sanitizar el cuerpo del mensaje."""
        return sanitize_string(v)
    
    @staticmethod
    def _is_valid_phone(phone: str) -> bool:
        """
        Validar formato de número telefónico internacional.
        Debe comenzar con + seguido de código de país y número.
        """
        pattern = r'^\+[1-9]\d{6,14}$'
        return bool(re.match(pattern, phone))


class DPIValidationResult(BaseModel):
    """Resultado de validación DPI (Data Loss Prevention)."""
    model_config = ConfigDict(extra='forbid')
    
    is_safe: bool
    detected_patterns: List[str] = Field(default_factory=list)
    risk_level: str = Field(default="low", pattern=r"^(low|medium|high|critical)$")
    blocked: bool = False
    reason: Optional[str] = None


class WhatsAppAgentConfig(StrictBaseModel):
    """Configuración segura para el agente de WhatsApp."""
    account_sid: str = Field(..., min_length=10, max_length=64, description="Account SID de Twilio")
    auth_token: str = Field(..., min_length=10, max_length=64, description="Auth Token de Twilio")
    from_number: str = Field(..., description="Número de WhatsApp Business desde el cual enviar")
    webhook_url: Optional[str] = Field(default=None, max_length=500, description="URL para webhooks")
    
    @field_validator('account_sid', 'auth_token')
    @classmethod
    def validate_credentials(cls, v: str) -> str:
        """Validar que las credenciales no estén vacías o sean default."""
        sanitized = sanitize_string(v)
        if len(sanitized) < 10 or sanitized in ('your_account_sid', 'your_auth_token', 'CHANGEME'):
            raise ValueError("Credenciales inválidas. Deben provenir de variables de entorno cifradas.")
        return sanitized
    
    @field_validator('from_number')
    @classmethod
    def validate_from_number(cls, v: str) -> str:
        """Validar número de origen."""
        if not WhatsAppMessage._is_valid_phone(v):
            raise ValueError(f"Número de origen inválido: {v}")
        return v


class WhatsAppAgent(BaseAgent):
    """
    Agente de integración con WhatsApp Business API.
    
    Características:
    - Envío y recepción asíncrona de mensajes
    - Extracción de intenciones usando patrones y NLP básico
    - Respuestas automáticas contextuales
    - Validación DPI para prevenir exfiltración de datos sensibles
    - Rate limiting integrado
    - Logging y auditoría completa
    """
    
    # Patrones de datos sensibles para DPI
    SENSITIVE_PATTERNS = {
        'credit_card': r'\b(?:\d{4}[- ]?){3}\d{4}\b',
        'ssn': r'\b\d{3}-\d{2}-\d{4}\b',
        'email': r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        'phone': r'\b\+?[1-9]\d{6,14}\b',
        'api_key': r'\b(?:api[_-]?key|apikey|token|secret)[_\s]*[=:]\s*[A-Za-z0-9\-_]{16,}\b',
        'password': r'\b(?:password|passwd|pwd)[_\s]*[=:]\s*\S+\b',
        'aws_key': r'\bAKIA[0-9A-Z]{16}\b',
        'private_key': r'-----BEGIN (?:RSA |EC )?PRIVATE KEY-----',
    }
    
    # Patrones de intenciones
    INTENT_PATTERNS = {
        MessageIntent.GREETING: [r'\b(hola|buenos|buenas|hi|hello|hey)\b'],
        MessageIntent.FAREWELL: [r'\b(chau|adios|bye|hasta luego|nos vemos)\b'],
        MessageIntent.QUESTION: [r'\b(qué|cuándo|cómo|por qué|dónde|cuánto|which|what|when|how|why|where)\b', r'.*\?$'],
        MessageIntent.COMMAND: [r'\b(necesito|quiero|requiero|make|do|execute|run)\b'],
        MessageIntent.INFORMATION_REQUEST: [r'\b(información|info|datos|details|status|estado)\b'],
        MessageIntent.COMPLAINT: [r'\b(problema|error|falla|issue|complaint|no funciona)\b'],
        MessageIntent.SUPPORT: [r'\b(ayuda|soporte|help|support|asistencia)\b'],
        MessageIntent.SALES: [r'\b(precio|costo|comprar|buy|price|venta|offer)\b'],
    }
    
    RATE_LIMIT_MESSAGES_PER_MINUTE = 60
    RATE_LIMIT_SECONDS = 60

    def __init__(self, config: WhatsAppAgentConfig, agent_id: str = "whatsapp_agent_001"):
        """
        Inicializar el agente de WhatsApp.
        
        Args:
            config: Configuración con credenciales cifradas
            agent_id: Identificador único del agente
        """
        super().__init__(agent_name="WhatsApp Integration Agent", agent_id=agent_id)
        
        self._config = config
        self._client: Optional[TwilioClient] = None
        self._message_history: List[WhatsAppMessage] = []
        self._rate_limit_tracker: List[datetime] = []
        self._dpi_enabled = True
        
        # Inicializar cliente Twilio
        self._initialize_client()
    
    def _initialize_client(self) -> None:
        """Inicializar el cliente de Twilio con las credenciales."""
        try:
            self._client = TwilioClient(
                self._config.account_sid,
                self._config.auth_token
            )
            logger.info("Cliente Twilio inicializado correctamente")
        except Exception as e:
            logger.error(f"Error al inicializar cliente Twilio: {e}")
            raise
    
    async def _check_rate_limit(self) -> bool:
        """
        Verificar si se ha excedido el rate limit.
        
        Returns:
            True si se puede enviar, False si se debe esperar
        """
        now = datetime.utcnow()
        cutoff = now.timestamp() - self.RATE_LIMIT_SECONDS
        
        # Limpiar mensajes antiguos del tracker
        self._rate_limit_tracker = [
            ts for ts in self._rate_limit_tracker 
            if ts.timestamp() > cutoff
        ]
        
        if len(self._rate_limit_tracker) >= self.RATE_LIMIT_MESSAGES_PER_MINUTE:
            logger.warning("Rate limit alcanzado. Esperando...")
            return False
        
        return True
    
    def _validate_dpi(self, content: str) -> DPIValidationResult:
        """
        Validar contenido contra patrones de exfiltración de datos (DPI).
        
        Args:
            content: Contenido del mensaje a validar
            
        Returns:
            Resultado de la validación DPI
        """
        if not self._dpi_enabled:
            return DPIValidationResult(is_safe=True, risk_level="low")
        
        detected = []
        risk_scores = {
            'credit_card': 0.9,
            'ssn': 0.95,
            'api_key': 0.85,
            'aws_key': 0.9,
            'private_key': 0.95,
            'password': 0.8,
            'email': 0.3,
            'phone': 0.3,
        }
        
        max_risk = 0.0
        for pattern_name, pattern in self.SENSITIVE_PATTERNS.items():
            if re.search(pattern, content, re.IGNORECASE):
                detected.append(pattern_name)
                max_risk = max(max_risk, risk_scores.get(pattern_name, 0.5))
        
        if max_risk >= 0.8:
            risk_level = "critical"
        elif max_risk >= 0.6:
            risk_level = "high"
        elif max_risk >= 0.4:
            risk_level = "medium"
        else:
            risk_level = "low"
        
        blocked = max_risk >= 0.7
        
        return DPIValidationResult(
            is_safe=not blocked,
            detected_patterns=detected,
            risk_level=risk_level,
            blocked=blocked,
            reason=f"Patrones sensibles detectados: {', '.join(detected)}" if detected else None
        )
    
    def _extract_intent(self, message_text: str) -> MessageIntent:
        """
        Extraer la intención de un mensaje entrante.
        
        Args:
            message_text: Texto del mensaje
            
        Returns:
            Intención detectada
        """
        text_lower = message_text.lower()
        
        for intent, patterns in self.INTENT_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, text_lower, re.IGNORECASE):
                    logger.debug(f"Intención detectada: {intent.value}")
                    return intent
        
        return MessageIntent.UNKNOWN
    
    def _generate_contextual_response(self, intent: MessageIntent, original_message: str) -> str:
        """
        Generar respuesta contextual basada en la intención detectada.
        
        Args:
            intent: Intención detectada
            original_message: Mensaje original
            
        Returns:
            Respuesta generada
        """
        responses = {
            MessageIntent.GREETING: "¡Hola! 👋 ¿En qué puedo ayudarte hoy?",
            MessageIntent.FAREWELL: "¡Hasta pronto! Que tengas un excelente día. 😊",
            MessageIntent.QUESTION: "Entiendo tu consulta. Déjame buscar la información más precisa para ti.",
            MessageIntent.COMMAND: "He recibido tu solicitud. La estoy procesando ahora mismo.",
            MessageIntent.INFORMATION_REQUEST: "Con gusto te proporciono esa información. Un momento por favor.",
            MessageIntent.COMPLAINT: "Lamento escuchar que tienes un problema. Voy a escalarte con nuestro equipo de soporte inmediatamente.",
            MessageIntent.SUPPORT: "Gracias por contactarnos. Un especialista te atenderá en breve.",
            MessageIntent.SALES: "¡Excelente interés! Te comparto información sobre nuestros productos y servicios.",
            MessageIntent.UNKNOWN: "Gracias por tu mensaje. ¿Podrías darme más detalles sobre lo que necesitas?",
        }
        
        base_response = responses.get(intent, responses[MessageIntent.UNKNOWN])
        
        # Agregar contexto específico si es una pregunta
        if intent == MessageIntent.QUESTION and "?" in original_message:
            base_response += " Mientras tanto, ¿hay algo más en lo que pueda asistirte?"
        
        return base_response
    
    async def send_message(
        self, 
        to_number: str, 
        message: str,
        media_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Enviar un mensaje de WhatsApp de forma asíncrona.
        
        Args:
            to_number: Número de destino (formato internacional con +)
            message: Cuerpo del mensaje
            media_url: URL opcional de imagen/video adjunto
            
        Returns:
            Dict con resultado del envío incluyendo SID del mensaje
            
        Raises:
            ValueError: Si el número es inválido
            PermissionError: Si DPI bloquea el mensaje
            TwilioRestException: Si la API de Twilio falla
        """
        # Validar número de destino
        if not WhatsAppMessage._is_valid_phone(PhoneNumber(to_number)):
            raise ValueError(f"Número de destino inválido: {to_number}")
        
        # Validar DPI
        dpi_result = self._validate_dpi(message)
        if dpi_result.blocked:
            logger.warning(f"DPI bloqueó mensaje: {dpi_result.reason}")
            raise PermissionError(f"Mensaje bloqueado por DPI: {dpi_result.reason}")
        
        # Check rate limit
        if not await self._check_rate_limit():
            # Esperar hasta que haya capacidad
            wait_time = self.RATE_LIMIT_SECONDS / self.RATE_LIMIT_MESSAGES_PER_MINUTE
            await asyncio.sleep(wait_time)
        
        try:
            # Construir cuerpo del mensaje
            message_body = {"body": message}
            if media_url:
                message_body["media_url"] = media_url
            
            # Enviar mensaje asíncronamente
            loop = asyncio.get_event_loop()
            sent_message = await loop.run_in_executor(
                None,
                lambda: self._client.messages.create(
                    to=to_number,
                    from_=self._config.from_number,
                    **message_body
                )
            )
            
            # Registrar en historial
            msg_record = WhatsAppMessage(
                from_number=self._config.from_number,
                to_number=to_number,
                body=message,
                message_sid=sent_message.sid,
                direction="outbound"
            )
            self._message_history.append(msg_record)
            self._rate_limit_tracker.append(datetime.utcnow())
            
            # Log acción
            await self.log_action("send_message", {
                "to": to_number,
                "message_sid": sent_message.sid,
                "status": "sent",
                "dpi_risk": dpi_result.risk_level
            })
            
            logger.info(f"Mensaje enviado a {to_number}, SID: {sent_message.sid}")
            
            return {
                "success": True,
                "message_sid": sent_message.sid,
                "status": sent_message.status,
                "to": to_number,
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except TwilioRestException as e:
            logger.error(f"Error de Twilio API: {e}")
            await self.log_action("send_message_failed", {
                "to": to_number,
                "error": str(e),
                "error_code": e.code
            })
            raise
    
    async def read_messages(
        self, 
        limit: int = 50,
        direction: str = "inbound"
    ) -> List[WhatsAppMessage]:
        """
        Leer mensajes recientes de WhatsApp de forma asíncrona.
        
        Args:
            limit: Cantidad máxima de mensajes a recuperar
            direction: Filtrar por dirección (inbound/outbound/both)
            
        Returns:
            Lista de mensajes recuperados
        """
        try:
            loop = asyncio.get_event_loop()
            
            # Construir filtros
            filters = {"limit": limit}
            if direction != "both":
                filters["direction"] = direction
            
            # Obtener mensajes asíncronamente
            messages = await loop.run_in_executor(
                None,
                lambda: list(self._client.messages.list(**filters))
            )
            
            result = []
            for msg in messages:
                try:
                    msg_record = WhatsAppMessage(
                        from_number=msg.from_,
                        to_number=msg.to,
                        body=msg.body or "",
                        timestamp=msg.date_created or datetime.utcnow(),
                        message_sid=msg.sid,
                        direction="inbound" if msg.direction == "inbound" else "outbound"
                    )
                    result.append(msg_record)
                except Exception as e:
                    logger.warning(f"Error procesando mensaje {msg.sid}: {e}")
                    continue
            
            logger.info(f"Se leyeron {len(result)} mensajes")
            return result
            
        except TwilioRestException as e:
            logger.error(f"Error leyendo mensajes: {e}")
            raise
    
    async def auto_respond(
        self,
        message_sid: Optional[str] = None,
        custom_rules: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Procesar mensajes entrantes y generar respuestas automáticas contextuales.
        
        Args:
            message_sid: SID específico de mensaje a responder (None para todos los nuevos)
            custom_rules: Reglas personalizadas de respuesta {patrón: respuesta}
            
        Returns:
            Dict con resultados de las respuestas enviadas
        """
        # Obtener mensajes sin responder
        inbound_messages = await self.read_messages(limit=10, direction="inbound")
        
        results = {
            "processed": 0,
            "responded": 0,
            "skipped": 0,
            "errors": []
        }
        
        for msg in inbound_messages:
            # Saltar si ya tiene SID específico y no coincide
            if message_sid and msg.message_sid != message_sid:
                continue
            
            try:
                # Validar DPI del mensaje entrante
                dpi_check = self._validate_dpi(msg.body)
                if dpi_check.blocked:
                    logger.warning(f"Mensaje entrante bloqueado por DPI de {msg.from_number}")
                    results["skipped"] += 1
                    continue
                
                # Extraer intención
                intent = self._extract_intent(msg.body)
                
                # Verificar reglas personalizadas primero
                response_text = None
                if custom_rules:
                    for pattern, response in custom_rules.items():
                        if re.search(pattern, msg.body, re.IGNORECASE):
                            response_text = response
                            break
                
                # Si no hay regla personalizada, usar respuesta contextual
                if not response_text:
                    response_text = self._generate_contextual_response(intent, msg.body)
                
                # Enviar respuesta
                send_result = await self.send_message(
                    to_number=msg.from_number,
                    message=response_text
                )
                
                results["responded"] += 1
                logger.info(f"Respuesta automática enviada a {msg.from_number} (intención: {intent.value})")
                
            except Exception as e:
                error_msg = f"Error procesando mensaje {msg.message_sid}: {str(e)}"
                logger.error(error_msg)
                results["errors"].append({
                    "message_sid": msg.message_sid,
                    "error": error_msg
                })
            
            results["processed"] += 1
        
        await self.log_action("auto_respond", results)
        return results
    
    async def execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Ejecutar una tarea del agente de WhatsApp.
        
        Args:
            task: Diccionario con parámetros de la tarea
            
        Returns:
            Resultado de la ejecución
        """
        operation = task.get("operation")
        
        operations = {
            "send_message": lambda: self.send_message(
                to_number=task.get("to_number"),
                message=task.get("message"),
                media_url=task.get("media_url")
            ),
            "read_messages": lambda: self.read_messages(
                limit=task.get("limit", 50),
                direction=task.get("direction", "inbound")
            ),
            "auto_respond": lambda: self.auto_respond(
                message_sid=task.get("message_sid"),
                custom_rules=task.get("custom_rules")
            ),
            "validate_dpi": lambda: self._validate_dpi(task.get("content", "")),
            "extract_intent": lambda: self._extract_intent(task.get("message", "")).value,
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
        Verificar si un número de teléfono está autorizado.
        
        Args:
            target: Número de teléfono o patrón a verificar
            
        Returns:
            True si está autorizado, False en caso contrario
        """
        # Implementar lógica de autorización específica
        # Por defecto, validar formato y permitir números verificados
        if not WhatsAppMessage._is_valid_phone(target):
            return False
        
        # Aquí se podría integrar con una lista blanca de números autorizados
        authorized_prefixes = ["+54", "+1", "+52", "+34", "+57", "+56", "+51", "+55"]
        return any(target.startswith(prefix) for prefix in authorized_prefixes)
    
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
        
        # En producción, esto iría a un sistema de logging centralizado
        logger.info(f"[AUDIT] {log_entry}")
    
    def enable_dpi(self) -> None:
        """Habilitar validación DPI."""
        self._dpi_enabled = True
        logger.info("DPI habilitado")
    
    def disable_dpi(self) -> None:
        """Deshabilitar validación DPI (solo para debugging)."""
        self._dpi_enabled = False
        logger.warning("DPI deshabilitado - ¡Solo para debugging!")
    
    @property
    def message_count(self) -> int:
        """Cantidad de mensajes en el historial."""
        return len(self._message_history)
    
    @property
    def config(self) -> WhatsAppAgentConfig:
        """Obtener configuración (solo lectura)."""
        return self._config
