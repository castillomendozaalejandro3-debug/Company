"""
DPI Validator - Validador de Deep Packet Inspection Semántica.
Analiza tráfico de red, URLs, emails y payloads contra reglas semánticas.
"""
import asyncio
import logging
import re
import json
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

try:
    from .structured_logger import get_logger
except ImportError:
    from structured_logger import get_logger

logger = get_logger(__name__)

class ThreatLevel(Enum):
    """Niveles de amenaza detectados."""
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class PayloadType(Enum):
    """Tipos de payload analizados."""
    URL = "url"
    EMAIL = "email"
    IP_ADDRESS = "ip_address"
    DOMAIN = "domain"
    FILE_CONTENT = "file_content"
    JSON_PAYLOAD = "json_payload"

@dataclass
class DPIResult:
    """Resultado del análisis DPI."""
    payload: str
    payload_type: PayloadType
    threat_level: ThreatLevel
    is_allowed: bool
    matched_rules: List[str]
    details: Dict[str, Any]
    timestamp: float

class DPIValidator:
    """Validador DPI Semántico para Helios."""
    
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or "config/allowed_domains.json"
        self.allowed_domains: List[str] = []
        self.blocked_patterns: List[re.Pattern] = []
        self.email_patterns: List[re.Pattern] = []
        self.url_patterns: List[re.Pattern] = []
        self.payload_rules: Dict[str, Any] = {}
        self.keyword_blocks: List[str] = []
        
        # Cargar configuración
        self._load_config()

    def _load_config(self):
        """Carga la configuración de dominios y reglas permitidos."""
        try:
            config_file = Path(self.config_path)
            if config_file.exists():
                with open(config_file, 'r') as f:
                    config = json.load(f)
                    
                self.allowed_domains = config.get("allowed_domains", [])
                
                # Compilar patrones regex bloqueados
                blocked = config.get("blocked_patterns", [])
                self.blocked_patterns = [re.compile(p, re.IGNORECASE) for p in blocked]
                
                # Patrones de email
                email_patterns = config.get("email_patterns", [])
                self.email_patterns = [re.compile(p, re.IGNORECASE) for p in email_patterns]
                
                # Patrones de URL
                url_patterns = config.get("url_patterns", [])
                self.url_patterns = [re.compile(p, re.IGNORECASE) for p in url_patterns]
                
                # Reglas de payload
                self.payload_rules = config.get("payload_rules", {})
                
                # Keywords bloqueadas
                self.keyword_blocks = config.get("blocked_keywords", [])
                
                logger.info(f"DPI config loaded: {len(self.allowed_domains)} domains, {len(self.blocked_patterns)} blocked patterns")
            else:
                logger.warning(f"DPI config file not found: {self.config_path}. Using defaults.")
                self._load_defaults()
                
        except Exception as e:
            logger.error(f"Failed to load DPI config: {e}")
            self._load_defaults()

    def _load_defaults(self):
        """Carga reglas por defecto si no hay configuración."""
        self.allowed_domains = [
            "localhost",
            "127.0.0.1",
            "*.example.com",
            "*.microsoft.com",
            "*.google.com",
            "*.github.com"
        ]
        
        self.blocked_patterns = [
            re.compile(r"malware", re.IGNORECASE),
            re.compile(r"exploit", re.IGNORECASE),
            re.compile(r"hack", re.IGNORECASE),
            re.compile(r"injection", re.IGNORECASE),
            re.compile(r"<script[^>]*>", re.IGNORECASE)  # XSS básico
        ]
        
        self.email_patterns = [
            re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
        ]
        
        self.url_patterns = [
            re.compile(r"^https?://[^\s/$.?#].[^\s]*$")
        ]

    async def validate_url(self, url: str) -> DPIResult:
        """Valida una URL contra las reglas DPI."""
        import time
        
        result = DPIResult(
            payload=url,
            payload_type=PayloadType.URL,
            threat_level=ThreatLevel.NONE,
            is_allowed=True,
            matched_rules=[],
            details={},
            timestamp=time.time()
        )
        
        # Extraer dominio
        domain = self._extract_domain(url)
        
        # Verificar dominio permitido
        if not self._is_domain_allowed(domain):
            result.is_allowed = False
            result.threat_level = ThreatLevel.HIGH
            result.matched_rules.append("domain_not_allowed")
            result.details["blocked_domain"] = domain
            
        # Verificar patrones bloqueados en URL completa
        for i, pattern in enumerate(self.blocked_patterns):
            if pattern.search(url):
                result.is_allowed = False
                result.threat_level = ThreatLevel.CRITICAL
                result.matched_rules.append(f"blocked_pattern_{i}")
                result.details["matched_pattern"] = pattern.pattern
                
        # Validar formato URL
        url_valid = any(p.match(url) for p in self.url_patterns)
        if not url_valid:
            result.is_allowed = False
            result.threat_level = ThreatLevel.MEDIUM
            result.matched_rules.append("invalid_url_format")
            
        return result

    async def validate_email(self, email: str) -> DPIResult:
        """Valida una dirección de email."""
        import time
        
        result = DPIResult(
            payload=email,
            payload_type=PayloadType.EMAIL,
            threat_level=ThreatLevel.NONE,
            is_allowed=True,
            matched_rules=[],
            details={},
            timestamp=time.time()
        )
        
        # Validar formato email
        email_valid = any(p.match(email) for p in self.email_patterns)
        if not email_valid:
            result.is_allowed = False
            result.threat_level = ThreatLevel.MEDIUM
            result.matched_rules.append("invalid_email_format")
            return result
            
        # Extraer dominio del email
        domain = email.split("@")[1] if "@" in email else ""
        
        # Verificar dominio
        if not self._is_domain_allowed(domain):
            result.is_allowed = False
            result.threat_level = ThreatLevel.HIGH
            result.matched_rules.append("email_domain_not_allowed")
            result.details["blocked_domain"] = domain
            
        return result

    async def validate_payload(self, payload: str, payload_type: PayloadType = PayloadType.JSON_PAYLOAD) -> DPIResult:
        """Valida un payload arbitrario."""
        import time
        
        result = DPIResult(
            payload=payload,
            payload_type=payload_type,
            threat_level=ThreatLevel.NONE,
            is_allowed=True,
            matched_rules=[],
            details={},
            timestamp=time.time()
        )
        
        # Verificar keywords bloqueadas
        for keyword in self.keyword_blocks:
            if keyword.lower() in payload.lower():
                result.is_allowed = False
                result.threat_level = ThreatLevel.HIGH
                result.matched_rules.append(f"blocked_keyword:{keyword}")
                
        # Verificar patrones de inyección
        injection_patterns = [
            r"(?i)(union\s+select)",
            r"(?i)(drop\s+table)",
            r"(?i)(exec\s*\()",
            r"(?i)(eval\s*\()",
            r"(?i)(__import__)",
        ]
        
        for pattern_str in injection_patterns:
            pattern = re.compile(pattern_str)
            if pattern.search(payload):
                result.is_allowed = False
                result.threat_level = ThreatLevel.CRITICAL
                result.matched_rules.append("injection_attempt")
                result.details["injection_type"] = pattern_str
                
        # Validar JSON si corresponde
        if payload_type == PayloadType.JSON_PAYLOAD:
            try:
                json.loads(payload)
            except json.JSONDecodeError as e:
                result.is_allowed = False
                result.threat_level = ThreatLevel.LOW
                result.matched_rules.append("invalid_json")
                result.details["json_error"] = str(e)
                
        return result

    async def validate_ip(self, ip_address: str) -> DPIResult:
        """Valida una dirección IP."""
        import time
        import ipaddress
        
        result = DPIResult(
            payload=ip_address,
            payload_type=PayloadType.IP_ADDRESS,
            threat_level=ThreatLevel.NONE,
            is_allowed=True,
            matched_rules=[],
            details={},
            timestamp=time.time()
        )
        
        try:
            ip = ipaddress.ip_address(ip_address)
            
            # Bloquear IPs privadas en contextos externos (configurable)
            if ip.is_private:
                result.details["private_ip"] = True
                
            # Bloquear localhost solo si está configurado
            if ip.is_loopback and "127.0.0.1" not in self.allowed_domains:
                result.is_allowed = False
                result.threat_level = ThreatLevel.MEDIUM
                result.matched_rules.append("loopback_blocked")
                
        except ValueError:
            result.is_allowed = False
            result.threat_level = ThreatLevel.MEDIUM
            result.matched_rules.append("invalid_ip_format")
            
        return result

    def _extract_domain(self, url: str) -> str:
        """Extrae el dominio de una URL."""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            return parsed.netloc or parsed.path.split("/")[0]
        except Exception:
            return url

    def _is_domain_allowed(self, domain: str) -> bool:
        """Verifica si un dominio está en la lista permitida."""
        if not domain:
            return False
            
        # Verificación exacta
        if domain in self.allowed_domains:
            return True
            
        # Verificación con wildcard
        for allowed in self.allowed_domains:
            if allowed.startswith("*."):
                base_domain = allowed[2:]
                if domain.endswith(base_domain) or domain == base_domain:
                    return True
                    
        return False

    async def deep_inspect(self, data: Dict[str, Any]) -> Dict[str, DPIResult]:
        """
        Realiza inspección profunda en un diccionario de datos.
        
        Args:
            data: Diccionario con posibles URLs, emails, payloads.
            
        Returns:
            Dict con resultados de validación por campo.
        """
        results = {}
        
        for key, value in data.items():
            if isinstance(value, str):
                # Determinar tipo y validar
                if value.startswith(("http://", "https://")):
                    results[key] = await self.validate_url(value)
                elif "@" in value and "." in value:
                    results[key] = await self.validate_email(value)
                elif self._looks_like_ip(value):
                    results[key] = await self.validate_ip(value)
                else:
                    results[key] = await self.validate_payload(value)
                    
        return results

    def _looks_like_ip(self, value: str) -> bool:
        """Verifica si un string parece una IP."""
        import re
        ip_pattern = r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$"
        return bool(re.match(ip_pattern, value))

    def add_allowed_domain(self, domain: str):
        """Agrega un dominio a la lista permitida."""
        if domain not in self.allowed_domains:
            self.allowed_domains.append(domain)
            logger.info(f"Added allowed domain: {domain}")

    def add_blocked_pattern(self, pattern: str):
        """Agrega un patrón bloqueado."""
        try:
            compiled = re.compile(pattern, re.IGNORECASE)
            self.blocked_patterns.append(compiled)
            logger.info(f"Added blocked pattern: {pattern}")
        except re.error as e:
            logger.error(f"Invalid regex pattern: {e}")

    def get_statistics(self) -> Dict[str, Any]:
        """Obtiene estadísticas del validator."""
        return {
            "allowed_domains_count": len(self.allowed_domains),
            "blocked_patterns_count": len(self.blocked_patterns),
            "email_patterns_count": len(self.email_patterns),
            "url_patterns_count": len(self.url_patterns),
            "blocked_keywords_count": len(self.keyword_blocks)
        }
