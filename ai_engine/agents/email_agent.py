"""
Email Agent - Agente especializado en automatización de correo electrónico.
Gestiona envío, recepción, clasificación y respuesta de emails de forma autónoma.
"""
import asyncio
import logging
import os
from typing import Dict, List, Optional, Any
from pathlib import Path
from dataclasses import dataclass
from enum import Enum

try:
    from .base_agent import BaseAgent, AgentState, AgentCapability
except ImportError:
    from ai_engine.agents.base_agent import BaseAgent, AgentState, AgentCapability

logger = logging.getLogger(__name__)

class EmailProtocol(Enum):
    """Protocolos de email soportados."""
    SMTP = "smtp"
    IMAP = "imap"
    POP3 = "pop3"

@dataclass
class EmailMessage:
    """Representación de un mensaje de email."""
    subject: str
    body: str
    from_address: str
    to_addresses: List[str]
    cc_addresses: Optional[List[str]] = None
    attachments: Optional[List[str]] = None
    is_html: bool = False
    in_reply_to: Optional[str] = None

class EmailAgent(BaseAgent):
    """Agente para automatización de tareas de correo electrónico."""
    
    def __init__(self, agent_id: str = "email-agent"):
        super().__init__(agent_id=agent_id)
        self.name = "EmailAgent"
        self.description = "Automates email tasks (send, receive, classify, respond)"
        
        # Registrar capacidades
        self.capabilities = [
            AgentCapability.SEND_EMAIL,
            AgentCapability.RECEIVE_EMAIL,
            AgentCapability.CLASSIFY_EMAIL,
            AgentCapability.REPLY_EMAIL,
            AgentCapability.FORWARD_EMAIL,
            AgentCapability.DELETE_EMAIL,
            AgentCapability.SEARCH_EMAIL
        ]
        
        # Configuración de conexión (se carga de variables de entorno)
        self.smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.imap_host = os.getenv("IMAP_HOST", "imap.gmail.com")
        self.imap_port = int(os.getenv("IMAP_PORT", "993"))
        self.email_user = os.getenv("EMAIL_USER")
        self.email_password = os.getenv("EMAIL_PASSWORD")
        
        self.connected = False
        
    async def initialize(self):
        """Inicializa el agente Email."""
        logger.info(f"Initializing {self.name}...")
        
        # Verificar credenciales
        if not self.email_user or not self.email_password:
            logger.warning("Email credentials not configured. Set EMAIL_USER and EMAIL_PASSWORD env vars.")
        else:
            logger.info("Email credentials found.")
            
        self.state = AgentState.IDLE
        logger.info(f"{self.name} initialized successfully.")

    async def execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Ejecuta una tarea de email."""
        if self.state != AgentState.IDLE:
            return {"success": False, "error": "Agent is busy"}
            
        self.state = AgentState.BUSY
        action = task.get("action")
        
        try:
            if action == "send":
                result = await self._send_email(task)
            elif action == "receive":
                result = await self._receive_emails(task)
            elif action == "search":
                result = await self._search_emails(task)
            elif action == "reply":
                result = await self._reply_email(task)
            elif action == "forward":
                result = await self._forward_email(task)
            elif action == "delete":
                result = await self._delete_email(task)
            elif action == "classify":
                result = await self._classify_email(task)
            else:
                result = {"success": False, "error": f"Unknown action: {action}"}
                
        except Exception as e:
            logger.error(f"Task execution failed: {e}")
            result = {"success": False, "error": str(e)}
        finally:
            self.state = AgentState.IDLE
            
        return result

    async def _send_email(self, task: Dict) -> Dict:
        """Envía un email."""
        to_addresses = task.get("to", [])
        subject = task.get("subject", "")
        body = task.get("body", "")
        cc_addresses = task.get("cc", [])
        attachments = task.get("attachments", [])
        is_html = task.get("is_html", False)
        
        if not to_addresses:
            return {"success": False, "error": "No recipient addresses provided"}
            
        if not self.email_user:
            return {"success": False, "error": "Email credentials not configured"}
            
        try:
            import smtplib
            from email.mime.multipart import MIMEMultipart
            from email.mime.text import MIMEText
            from email.mime.base import MIMEBase
            from email import encoders
            
            # Crear mensaje
            msg = MIMEMultipart()
            msg['From'] = self.email_user
            msg['To'] = ", ".join(to_addresses)
            msg['Subject'] = subject
            
            if cc_addresses:
                msg['Cc'] = ", ".join(cc_addresses)
                to_addresses.extend(cc_addresses)
            
            # Adjuntar cuerpo
            msg_type = "html" if is_html else "plain"
            msg.attach(MIMEText(body, msg_type))
            
            # Adjuntar archivos
            for filepath in attachments:
                if os.path.exists(filepath):
                    with open(filepath, "rb") as attachment:
                        part = MIMEBase('application', 'octet-stream')
                        part.set_payload(attachment.read())
                        encoders.encode_base64(part)
                        part.add_header(
                            'Content-Disposition',
                            f'attachment; filename={os.path.basename(filepath)}'
                        )
                        msg.attach(part)
                else:
                    logger.warning(f"Attachment not found: {filepath}")
            
            # Conectar y enviar
            server = smtplib.SMTP(self.smtp_host, self.smtp_port)
            server.starttls()
            server.login(self.email_user, self.email_password)
            server.sendmail(self.email_user, to_addresses, msg.as_string())
            server.quit()
            
            logger.info(f"Email sent to {to_addresses}")
            return {
                "success": True,
                "message": "Email sent successfully",
                "recipients": to_addresses,
                "subject": subject
            }
            
        except Exception as e:
            return {"success": False, "error": f"SMTP error: {str(e)}"}

    async def _receive_emails(self, task: Dict) -> Dict:
        """Recibe emails de la bandeja de entrada."""
        limit = task.get("limit", 10)
        folder = task.get("folder", "INBOX")
        unread_only = task.get("unread_only", False)
        
        if not self.email_user:
            return {"success": False, "error": "Email credentials not configured"}
            
        try:
            import imaplib
            from email.parser import BytesParser
            
            # Conectar al servidor IMAP
            mail = imaplib.IMAP4_SSL(self.imap_host, self.imap_port)
            mail.login(self.email_user, self.email_password)
            mail.select(folder)
            
            # Buscar mensajes
            search_criteria = 'UNSEEN' if unread_only else 'ALL'
            status, messages = mail.search(None, search_criteria)
            
            if status != 'OK':
                mail.close()
                mail.logout()
                return {"success": False, "error": "Failed to search messages"}
                
            email_ids = messages[0].split()
            total = len(email_ids)
            to_fetch = min(limit, total)
            
            emails = []
            for email_id in email_ids[-to_fetch:]:  # Obtener los más recientes
                status, msg_data = mail.fetch(email_id, '(RFC822)')
                if status == 'OK':
                    parser = BytesParser()
                    email_obj = parser.parsebytes(msg_data[0][1])
                    
                    emails.append({
                        "id": email_id.decode(),
                        "subject": email_obj.get('Subject', ''),
                        "from": email_obj.get('From', ''),
                        "date": email_obj.get('Date', ''),
                        "body": self._get_email_body(email_obj)
                    })
            
            mail.close()
            mail.logout()
            
            logger.info(f"Retrieved {len(emails)} emails from {folder}")
            return {
                "success": True,
                "emails": emails,
                "total_in_folder": total,
                "fetched": len(emails)
            }
            
        except Exception as e:
            return {"success": False, "error": f"IMAP error: {str(e)}"}

    def _get_email_body(self, email_obj) -> str:
        """Extrae el cuerpo del email."""
        body = ""
        
        if email_obj.is_multipart():
            for part in email_obj.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition"))
                
                if content_type == "text/plain" and "attachment" not in content_disposition:
                    try:
                        body = part.get_payload(decode=True).decode()
                        break
                    except:
                        pass
        else:
            try:
                body = email_obj.get_payload(decode=True).decode()
            except:
                pass
                
        return body

    async def _search_emails(self, task: Dict) -> Dict:
        """Busca emails por criterios."""
        query = task.get("query", "")
        folder = task.get("folder", "INBOX")
        limit = task.get("limit", 50)
        
        if not self.email_user:
            return {"success": False, "error": "Email credentials not configured"}
            
        try:
            import imaplib
            from email.parser import BytesParser
            
            mail = imaplib.IMAP4_SSL(self.imap_host, self.imap_port)
            mail.login(self.email_user, self.email_password)
            mail.select(folder)
            
            # Búsqueda simple por asunto
            status, messages = mail.search(None, f'(SUBJECT "{query}")')
            
            if status != 'OK':
                mail.close()
                mail.logout()
                return {"success": False, "error": "Search failed"}
                
            email_ids = messages[0].split()[:limit]
            results = []
            
            for email_id in email_ids:
                status, msg_data = mail.fetch(email_id, '(RFC822.HEADER)')
                if status == 'OK':
                    parser = BytesParser()
                    email_obj = parser.parsebytes(msg_data[0][1])
                    results.append({
                        "id": email_id.decode(),
                        "subject": email_obj.get('Subject', ''),
                        "from": email_obj.get('From', ''),
                        "date": email_obj.get('Date', '')
                    })
            
            mail.close()
            mail.logout()
            
            return {
                "success": True,
                "results": results,
                "count": len(results),
                "query": query
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _reply_email(self, task: Dict) -> Dict:
        """Responde a un email."""
        original_message_id = task.get("message_id")
        body = task.get("body", "")
        include_original = task.get("include_original", True)
        
        # Implementación simplificada - requiere contexto del email original
        return {
            "success": False,
            "error": "Reply functionality requires email context. Use send action instead."
        }

    async def _forward_email(self, task: Dict) -> Dict:
        """Reenvía un email."""
        original_message_id = task.get("message_id")
        to_addresses = task.get("to", [])
        
        return {
            "success": False,
            "error": "Forward functionality requires email context. Use send action instead."
        }

    async def _delete_email(self, task: Dict) -> Dict:
        """Elimina un email."""
        message_id = task.get("message_id")
        folder = task.get("folder", "INBOX")
        
        if not message_id:
            return {"success": False, "error": "Message ID required"}
            
        if not self.email_user:
            return {"success": False, "error": "Email credentials not configured"}
            
        try:
            import imaplib
            
            mail = imaplib.IMAP4_SSL(self.imap_host, self.imap_port)
            mail.login(self.email_user, self.email_password)
            mail.select(folder)
            
            # Marcar como eliminado
            mail.store(message_id.encode(), '+FLAGS', '\\Deleted')
            mail.expunge()
            
            mail.close()
            mail.logout()
            
            logger.info(f"Email {message_id} deleted")
            return {"success": True, "message": "Email deleted"}
            
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _classify_email(self, task: Dict) -> Dict:
        """Clasifica un email usando reglas o ML."""
        subject = task.get("subject", "")
        body = task.get("body", "")
        
        # Clasificación básica por keywords
        categories = {
            "urgent": ["urgent", "asap", "immediate", "priority"],
            "spam": ["winner", "lottery", "free money", "click here"],
            "newsletter": ["newsletter", "subscription", "unsubscribe"],
            "work": ["meeting", "deadline", "project", "report"]
        }
        
        text = f"{subject} {body}".lower()
        detected_categories = []
        
        for category, keywords in categories.items():
            if any(keyword in text for keyword in keywords):
                detected_categories.append(category)
                
        return {
            "success": True,
            "categories": detected_categories,
            "confidence": "low"  # Clasificación básica
        }

    async def shutdown(self):
        """Detiene el agente limpiando recursos."""
        logger.info(f"Shutting down {self.name}...")
        self.connected = False
        self.state = AgentState.STOPPED
        logger.info(f"{self.name} stopped.")
