"""
IPC con mTLS - Sección 5.4 del Kernel Inmutable

Comunicación interna entre Kernel y Workers usando Unix Domain Sockets
con TLS Mutuo (mTLS) y certificados X.509 efímeros generados en memoria.
"""

import asyncio
import logging
import os
import socket
import ssl
import sys
import tempfile
from pathlib import Path
from typing import Optional, Dict, Any, Callable, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
import json

logger = logging.getLogger(__name__)

try:
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.backends import default_backend
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False
    logger.warning("cryptography no disponible. mTLS desactivado.")


@dataclass
class IPCMessage:
    message_id: str
    message_type: str
    source: str
    destination: str
    payload: Dict[str, Any]
    timestamp: float


class CertificateManager:
    """Genera y gestiona certificados X.509 efímeros para mTLS."""
    
    def __init__(self, validity_days: int = 1):
        self.validity_days = validity_days
        self._ca_cert: Optional[x509.Certificate] = None
        self._ca_key: Optional[rsa.RSAPrivateKey] = None
    
    def generate_ca(self) -> Tuple[bytes, bytes]:
        """Genera CA raíz efímera en memoria."""
        if not CRYPTO_AVAILABLE:
            raise RuntimeError("cryptography library not available")
        
        key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )
        
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
            x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "CA"),
            x509.NameAttribute(NameOID.LOCALITY_NAME, "Helios"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Helios Kernel"),
            x509.NameAttribute(NameOID.COMMON_NAME, "Helios Root CA"),
        ])
        
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.utcnow())
            .not_valid_after(datetime.utcnow() + timedelta(days=self.validity_days))
            .add_extension(
                x509.BasicConstraints(ca=True, path_length=None),
                critical=True,
            )
            .sign(key, hashes.SHA256(), default_backend())
        )
        
        self._ca_cert = cert
        self._ca_key = key
        
        return (
            cert.public_bytes(serialization.Encoding.PEM),
            key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption()
            )
        )
    
    def generate_worker_cert(
        self,
        worker_id: str,
        common_name: str
    ) -> Tuple[bytes, bytes, bytes]:
        """Genera certificado de cliente para un Worker."""
        if not CRYPTO_AVAILABLE or self._ca_key is None:
            raise RuntimeError("CA not initialized")
        
        key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )
        
        subject = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
            x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "CA"),
            x509.NameAttribute(NameOID.LOCALITY_NAME, "Helios"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Helios Workers"),
            x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, worker_id),
            x509.NameAttribute(NameOID.COMMON_NAME, common_name),
        ])
        
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(self._ca_cert.subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.utcnow())
            .not_valid_after(datetime.utcnow() + timedelta(days=self.validity_days))
            .add_extension(
                x509.BasicConstraints(ca=False, path_length=None),
                critical=True,
            )
            .add_extension(
                x509.ExtendedKeyUsage([
                    x509.OID_CLIENT_AUTH,
                    x509.OID_SERVER_AUTH,
                ]),
                critical=False,
            )
            .sign(self._ca_key, hashes.SHA256(), default_backend())
        )
        
        return (
            cert.public_bytes(serialization.Encoding.PEM),
            key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption()
            ),
            self._ca_cert.public_bytes(serialization.Encoding.PEM)
        )


class MTLSIPCChannel:
    """Canal de comunicación IPC con mTLS entre Kernel y Workers."""
    
    def __init__(
        self,
        socket_path: str,
        node_id: str,
        is_server: bool = False,
        cert_manager: Optional[CertificateManager] = None
    ):
        self.socket_path = Path(socket_path)
        self.node_id = node_id
        self.is_server = is_server
        self.cert_manager = cert_manager or CertificateManager()
        
        # Detectar si estamos en Windows para usar TCP en lugar de Unix sockets
        self.is_windows = os.name == 'nt'
        self.tcp_host = "127.0.0.1"
        self.tcp_port = 50421  # Puerto default para Helios IPC
        
        self._socket: Optional[socket.socket] = None
        self._ssl_socket: Optional[ssl.SSLSocket] = None
        self._server_socket: Optional[socket.socket] = None
        self._running = False
        self._message_handlers: Dict[str, Callable] = {}
        self._ca_cert_pem: Optional[bytes] = None
        self._cert_pem: Optional[bytes] = None
        self._key_pem: Optional[bytes] = None
    
    async def initialize(self) -> None:
        """Inicializa el canal IPC con mTLS."""
        if not CRYPTO_AVAILABLE:
            logger.warning("mTLS no disponible, usando socket sin cifrar")
            return
        
        try:
            if self.is_server:
                self._ca_cert_pem, _ = self.cert_manager.generate_ca()
                self._cert_pem, self._key_pem, _ = (
                    self.cert_manager.generate_worker_cert(
                        "kernel",
                        "kernel.helios.local"
                    )
                )
            else:
                self._cert_pem, self._key_pem, self._ca_cert_pem = (
                    self.cert_manager.generate_worker_cert(
                        self.node_id,
                        f"{self.node_id}.helios.local"
                    )
                )
            
            logger.info(f"Certificados mTLS generados para {self.node_id}")
        except Exception as e:
            logger.error(f"Error generando certificados: {e}")
            raise
    
    def _create_ssl_context(self) -> ssl.SSLContext:
        """Crea contexto SSL para mTLS."""
        if not CRYPTO_AVAILABLE or not self._ca_cert_pem:
            raise RuntimeError("Certificates not initialized")
        
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLSv1_3)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_REQUIRED
        
        with tempfile.NamedTemporaryFile(delete=False) as ca_file:
            ca_file.write(self._ca_cert_pem)
            ca_path = ca_file.name
        
        with tempfile.NamedTemporaryFile(delete=False) as cert_file:
            cert_file.write(self._cert_pem)
            cert_path = cert_file.name
        
        with tempfile.NamedTemporaryFile(delete=False) as key_file:
            key_file.write(self._key_pem)
            key_path = key_file.name
        
        try:
            ctx.load_verify_locations(cafile=ca_path)
            ctx.load_cert_chain(certfile=cert_path, keyfile=key_path)
        finally:
            for path in [ca_path, cert_path, key_path]:
                try:
                    os.unlink(path)
                except Exception:
                    pass
        
        return ctx
    
    async def start_server(self) -> None:
        """Inicia el servidor IPC (Kernel)."""
        if self.is_server:
            await self.initialize()
        
        if self.is_windows:
            # Windows: usar TCP socket en lugar de Unix Domain Socket
            self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._server_socket.bind((self.tcp_host, self.tcp_port))
            self._server_socket.listen(5)
            self._server_socket.setblocking(False)
            logger.info(f"Servidor IPC TCP iniciado en {self.tcp_host}:{self.tcp_port}")
        else:
            # Unix/Linux/macOS: usar Unix Domain Socket
            socket_dir = self.socket_path.parent
            socket_dir.mkdir(parents=True, exist_ok=True)
            
            if self.socket_path.exists():
                self.socket_path.unlink()
            
            self._socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._socket.bind(str(self.socket_path))
            
            os.chmod(self.socket_path, 0o600)
            logger.info(f"Socket IPC creado: {self.socket_path} (chmod 600)")
            
            self._socket.listen(5)
            self._socket.setblocking(False)
            logger.info(f"Servidor IPC Unix iniciado en {self.socket_path}")
        
        self._running = True
    
    async def accept_connection(self) -> 'MTLSIPCChannel':
        """Acepta conexión de un Worker."""
        if self.is_windows:
            if not self._server_socket:
                raise RuntimeError("Server socket not started")
            
            loop = asyncio.get_event_loop()
            client_socket, _ = await loop.sock_accept(self._server_socket)
        else:
            if not self._socket:
                raise RuntimeError("Server not started")
            
            loop = asyncio.get_event_loop()
            client_socket, _ = await loop.sock_accept(self._socket)
        
        client_channel = MTLSIPCChannel(
            socket_path=str(self.socket_path),
            node_id="client",
            is_server=False,
            cert_manager=self.cert_manager
        )
        client_channel._socket = client_socket
        
        if CRYPTO_AVAILABLE and self._ca_cert_pem:
            ssl_ctx = self._create_ssl_context()
            client_channel._ssl_socket = ssl_ctx.wrap_socket(
                client_socket,
                server_side=True,
                do_handshake_on_connect=True
            )
            logger.info("Conexión mTLS establecida con Worker")
        
        return client_channel
    
    async def connect(self) -> None:
        """Conecta al servidor IPC (Worker)."""
        if not self.is_server:
            await self.initialize()
        
        max_retries = 10
        
        if self.is_windows:
            # Windows: conectar via TCP
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            
            for attempt in range(max_retries):
                try:
                    self._socket.connect((self.tcp_host, self.tcp_port))
                    break
                except ConnectionRefusedError:
                    if attempt == max_retries - 1:
                        raise
                    await asyncio.sleep(0.1 * (attempt + 1))
        else:
            # Unix/Linux/macOS: conectar via Unix Domain Socket
            self._socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            
            for attempt in range(max_retries):
                try:
                    self._socket.connect(str(self.socket_path))
                    break
                except FileNotFoundError:
                    if attempt == max_retries - 1:
                        raise
                    await asyncio.sleep(0.1 * (attempt + 1))
        
        if CRYPTO_AVAILABLE and self._ca_cert_pem:
            ssl_ctx = self._create_ssl_context()
            self._ssl_socket = ssl_ctx.wrap_socket(
                self._socket,
                server_side=False,
                do_handshake_on_connect=True
            )
            logger.info("Conexión mTLS establecida con Kernel")
        
        self._running = True
    
    def register_handler(
        self,
        message_type: str,
        handler: Callable[[IPCMessage], Any]
    ) -> None:
        """Registra handler para tipo de mensaje."""
        self._message_handlers[message_type] = handler
    
    async def send_message(self, message: IPCMessage) -> None:
        """Envía mensaje a través del canal."""
        data = json.dumps({
            "message_id": message.message_id,
            "message_type": message.message_type,
            "source": message.source,
            "destination": message.destination,
            "payload": message.payload,
            "timestamp": message.timestamp
        }).encode('utf-8')
        
        length_prefix = len(data).to_bytes(4, byteorder='big')
        
        sock = self._ssl_socket or self._socket
        if not sock:
            raise RuntimeError("Socket not connected")
        
        loop = asyncio.get_event_loop()
        await loop.sock_sendall(sock, length_prefix + data)
        logger.debug(f"Mensaje enviado: {message.message_type}")
    
    async def receive_message(self) -> Optional[IPCMessage]:
        """Recibe mensaje del canal."""
        sock = self._ssl_socket or self._socket
        if not sock:
            raise RuntimeError("Socket not connected")
        
        loop = asyncio.get_event_loop()
        
        length_data = await loop.sock_recv(sock, 4)
        if not length_data:
            return None
        
        length = int.from_bytes(length_data, byteorder='big')
        data = await loop.sock_recv(sock, length)
        
        msg_dict = json.loads(data.decode('utf-8'))
        
        message = IPCMessage(
            message_id=msg_dict["message_id"],
            message_type=msg_dict["message_type"],
            source=msg_dict["source"],
            destination=msg_dict["destination"],
            payload=msg_dict["payload"],
            timestamp=msg_dict["timestamp"]
        )
        
        logger.debug(f"Mensaje recibido: {message.message_type}")
        return message
    
    async def listen(self) -> None:
        """Escucha mensajes entrantes continuamente."""
        while self._running:
            try:
                message = await self.receive_message()
                if message and message.message_type in self._message_handlers:
                    handler = self._message_handlers[message.message_type]
                    if asyncio.iscoroutinefunction(handler):
                        await handler(message)
                    else:
                        handler(message)
            except Exception as e:
                if self._running:
                    logger.error(f"Error escuchando mensajes: {e}")
                break
    
    def close(self) -> None:
        """Cierra el canal IPC."""
        self._running = False
        
        if self._ssl_socket:
            try:
                self._ssl_socket.close()
            except Exception:
                pass
        
        if self._socket:
            try:
                self._socket.close()
            except Exception:
                pass
        
        if self.is_server and not self.is_windows and self.socket_path.exists():
            try:
                self.socket_path.unlink()
            except Exception:
                pass
        
        if self.is_server and self._server_socket:
            try:
                self._server_socket.close()
            except Exception:
                pass
        
        logger.info("Canal IPC cerrado")


class IPCKernelDaemon:
    """Daemon del Kernel que gestiona comunicaciones IPC con Workers."""
    
    def __init__(self, socket_path: str = "/tmp/helios_kernel.sock"):
        self.socket_path = socket_path
        self.channel: Optional[MTLSIPCChannel] = None
        self.cert_manager = CertificateManager()
        self._workers: Dict[str, MTLSIPCChannel] = {}
        self._running = False
    
    async def start(self) -> None:
        """Inicia el daemon IPC del Kernel."""
        self.channel = MTLSIPCChannel(
            socket_path=self.socket_path,
            node_id="kernel",
            is_server=True,
            cert_manager=self.cert_manager
        )
        
        await self.channel.start_server()
        
        self.channel.register_handler("worker_request", self._handle_worker_request)
        self.channel.register_handler("worker_response", self._handle_worker_response)
        self.channel.register_handler("heartbeat", self._handle_heartbeat)
        
        self._running = True
        logger.info(f"Kernel IPC Daemon iniciado en {self.socket_path}")
        
        asyncio.create_task(self._accept_workers())
    
    async def _accept_workers(self) -> None:
        """Acepta conexiones de Workers."""
        while self._running:
            try:
                worker_channel = await self.channel.accept_connection()
                worker_id = f"worker_{len(self._workers)}"
                self._workers[worker_id] = worker_channel
                logger.info(f"Worker conectado: {worker_id}")
                
                asyncio.create_task(self._handle_worker(worker_id, worker_channel))
            except Exception as e:
                if self._running:
                    logger.error(f"Error aceptando Worker: {e}")
                break
    
    async def _handle_worker(
        self,
        worker_id: str,
        channel: MTLSIPCChannel
    ) -> None:
        """Maneja comunicación con un Worker específico."""
        try:
            await channel.listen()
        except Exception as e:
            logger.error(f"Error con Worker {worker_id}: {e}")
        finally:
            self._workers.pop(worker_id, None)
            channel.close()
            logger.info(f"Worker desconectado: {worker_id}")
    
    async def _handle_worker_request(self, message: IPCMessage) -> None:
        """Procesa solicitud de Worker."""
        logger.info(f"Solicitud de Worker: {message.message_type}")
    
    async def _handle_worker_response(self, message: IPCMessage) -> None:
        """Procesa respuesta de Worker."""
        logger.info(f"Respuesta de Worker: {message.message_type}")
    
    async def _handle_heartbeat(self, message: IPCMessage) -> None:
        """Procesa heartbeat de Worker."""
        logger.debug(f"Heartbeat de {message.source}")
    
    async def broadcast_to_workers(
        self,
        message_type: str,
        payload: Dict[str, Any]
    ) -> None:
        """Envía mensaje a todos los Workers conectados."""
        import time
        import uuid
        
        message = IPCMessage(
            message_id=str(uuid.uuid4()),
            message_type=message_type,
            source="kernel",
            destination="broadcast",
            payload=payload,
            timestamp=time.time()
        )
        
        for worker_id, channel in self._workers.items():
            try:
                await channel.send_message(message)
            except Exception as e:
                logger.error(f"Error enviando a {worker_id}: {e}")
    
    async def stop(self) -> None:
        """Detiene el daemon."""
        self._running = False
        
        for worker_id, channel in list(self._workers.items()):
            channel.close()
        
        if self.channel:
            self.channel.close()
        
        logger.info("Kernel IPC Daemon detenido")


def get_default_socket_path() -> str:
    """Obtiene ruta de socket por defecto según OS."""
    if os.name == 'nt':
        # Windows usa TCP, no named pipes en esta implementación
        return "tcp://127.0.0.1:50421"
    else:
        return "/tmp/helios_kernel.sock"
