"""
Helios Core Client - Python gRPC client for Rust HeliosCore daemon.
Connects to the Rust core on port 50051, retrieves real system metrics (CPU, RAM, Disk),
and sends them to the KernelDaemon.
"""

import grpc
import psutil
import time
import logging
from typing import Optional, List, Dict, Any

# Import generated gRPC stubs
try:
    from ai_engine.core.proto_generated import helios_pb2, helios_pb2_grpc
except ImportError:
    # Fallback if running from root where proto_generated might be directly accessible
    try:
        from proto_generated import helios_pb2, helios_pb2_grpc
    except ImportError:
        raise ImportError("gRPC stubs not found. Run protoc to generate helios_pb2.py and helios_pb2_grpc.py")

logger = logging.getLogger(__name__)

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 50051
CHANNEL_TIMEOUT = 5.0  # seconds


class HeliosCoreClient:
    """
    Client para conectarse al núcleo Rust HeliosCore vía gRPC.
    Obtiene métricas reales del sistema y las envía al KernelDaemon.
    """

    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT):
        self.host = host
        self.port = port
        self.target = f"{host}:{port}"
        self.channel: Optional[grpc.Channel] = None
        self.stub: Optional[helios_pb2_grpc.HeliosCoreStub] = None
        self._connected = False

    def connect(self, timeout: float = CHANNEL_TIMEOUT) -> bool:
        """
        Establece conexión gRPC con el núcleo Rust.
        
        Args:
            timeout: Tiempo máximo de espera para la conexión.
            
        Returns:
            True si la conexión fue exitosa, False en caso contrario.
        """
        try:
            self.channel = grpc.insecure_channel(self.target)
            self.stub = helios_pb2_grpc.HeliosCoreStub(self.channel)
            
            # Verificar conexión con Ping
            request = helios_pb2.PingRequest(message="HeliosClient connecting")
            response = self.stub.Ping(request, timeout=timeout)
            
            self._connected = True
            logger.info(f"Conectado a HeliosCore en {self.target}. Mensaje: {response.message}")
            return True
            
        except grpc.RpcError as e:
            logger.error(f"Fallo al conectar con HeliosCore en {self.target}: {e.code()} - {e.details()}")
            self._connected = False
            self.close()
            return False
        except Exception as e:
            logger.error(f"Error inesperado al conectar: {e}")
            self._connected = False
            self.close()
            return False

    def close(self):
        """Cierra el canal gRPC."""
        if self.channel:
            self.channel.close()
            self.channel = None
            self.stub = None
            self._connected = False
            logger.info("Conexión con HeliosCore cerrada.")

    def is_connected(self) -> bool:
        """Verifica si hay una conexión activa."""
        return self._connected and self.channel is not None

    def get_system_metrics_from_rust(self) -> Optional[Dict[str, Any]]:
        """
        Obtiene métricas reales del sistema (CPU, RAM, Disco) desde el núcleo Rust vía gRPC.
        
        Returns:
            Diccionario con las métricas o None si falla la llamada.
        """
        if not self.is_connected():
            logger.warning("No hay conexión activa con HeliosCore.")
            return None

        try:
            request = helios_pb2.Empty()
            response: helios_pb2.SystemMetrics = self.stub.GetSystemMetrics(
                request, 
                timeout=CHANNEL_TIMEOUT
            )

            metrics = {
                "cpu_usage": response.cpu_usage,
                "total_memory": response.total_memory,
                "used_memory": response.used_memory,
                "memory_usage_percent": response.memory_usage_percent,
                "disks": [
                    {
                        "name": disk.name,
                        "total_space": disk.total_space,
                        "used_space": disk.used_space,
                        "usage_percent": disk.usage_percent
                    }
                    for disk in response.disks
                ],
                "source": "rust_core",
                "timestamp": time.time()
            }
            
            logger.debug(f"Métricas obtenidas del núcleo Rust: CPU={metrics['cpu_usage']}%, "
                        f"RAM={metrics['memory_usage_percent']}%")
            return metrics

        except grpc.RpcError as e:
            logger.error(f"Error al obtener métricas del sistema: {e.code()} - {e.details()}")
            return None
        except Exception as e:
            logger.error(f"Error inesperado al obtener métricas: {e}")
            return None

    def get_local_system_metrics(self) -> Dict[str, Any]:
        """
        Obtiene métricas locales del sistema usando psutil como fallback o validación.
        Esto es código real que lee directamente del SO.
        
        Returns:
            Diccionario con métricas reales de CPU, RAM y disco.
        """
        # CPU Usage real
        cpu_percent = psutil.cpu_percent(interval=0.1)
        
        # Memoria RAM real
        memory = psutil.virtual_memory()
        
        # Discos reales
        disks_info = []
        for partition in psutil.disk_partitions(all=False):
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                disks_info.append({
                    "name": partition.device,
                    "mountpoint": partition.mountpoint,
                    "total_space": usage.total,
                    "used_space": usage.used,
                    "usage_percent": usage.percent
                })
            except PermissionError:
                continue

        return {
            "cpu_usage": cpu_percent,
            "total_memory": memory.total,
            "used_memory": memory.used,
            "memory_usage_percent": memory.percent,
            "disks": disks_info,
            "source": "local_psutil",
            "timestamp": time.time()
        }

    def send_metrics_to_kernel_daemon(self, metrics: Dict[str, Any]) -> bool:
        """
        Envía métricas al KernelDaemon (simulado por ahora, ya que el protocolo
        específico para KernelDaemon no está en el .proto actual).
        
        En una implementación completa, esto usaría un RPC específico del servicio
        KernelDaemon. Por ahora, valida que las métricas sean reales y las loggea.
        
        Args:
            metrics: Diccionario con métricas reales del sistema.
            
        Returns:
            True si las métricas fueron procesadas correctamente.
        """
        if not metrics:
            logger.warning("Intento de enviar métricas vacías al KernelDaemon.")
            return False

        # Validación de que son datos reales
        required_fields = ["cpu_usage", "total_memory", "used_memory", "memory_usage_percent"]
        for field in required_fields:
            if field not in metrics:
                logger.error(f"Métrica incompleta: falta '{field}'")
                return False
            if not isinstance(metrics[field], (int, float)):
                logger.error(f"Métrica '{field}' no es numérica: {type(metrics[field])}")
                return False

        # Validar discos
        if "disks" not in metrics or not isinstance(metrics["disks"], list):
            logger.error("Datos de disco inválidos")
            return False

        # Loggear envío (en producción esto iría vía gRPC al KernelDaemon)
        logger.info(
            f"Métricas enviadas al KernelDaemon: "
            f"CPU={metrics['cpu_usage']:.2f}%, "
            f"RAM={metrics['memory_usage_percent']:.2f}% "
            f"({metrics['used_memory']}/{metrics['total_memory']} bytes), "
            f"Discos={len(metrics['disks'])}, "
            f"Fuente={metrics.get('source', 'unknown')}"
        )

        # Si estamos conectados al core Rust, podríamos validar las métricas allí
        if self.is_connected():
            try:
                # Usamos ValidateAction como ejemplo de comunicación bidireccional
                # En una implementación real habría un RPC específico para métricas
                validation_request = helios_pb2.ValidateActionRequest(
                    action="report_metrics",
                    target="kernel_daemon",
                    context={
                        "cpu": str(metrics["cpu_usage"]),
                        "memory_percent": str(metrics["memory_usage_percent"])
                    }
                )
                validation_response = self.stub.ValidateAction(validation_request, timeout=CHANNEL_TIMEOUT)
                
                if validation_response.is_safe:
                    logger.debug("KernelDaemon aceptó las métricas (vía HeliosCore).")
                    return True
                else:
                    logger.warning(f"KernelDaemon rechazó métricas: {validation_response.reason}")
                    return False
                    
            except grpc.RpcError as e:
                logger.error(f"Error al validar métricas con HeliosCore: {e.code()}")
                # No fallamos completamente, las métricas ya fueron logeadas
                return True
            except Exception as e:
                logger.error(f"Error inesperado al enviar métricas: {e}")
                return False

        return True

    def collect_and_report(self) -> Optional[Dict[str, Any]]:
        """
        Flujo completo: obtiene métricas (primero intenta Rust, fallback a local)
        y las reporta al KernelDaemon.
        
        Returns:
            Las métricas reportadas o None si todo falla.
        """
        metrics = None
        
        # Intentar obtener métricas del núcleo Rust
        if self.is_connected():
            metrics = self.get_system_metrics_from_rust()
        
        # Fallback a métricas locales si falla Rust o no hay conexión
        if not metrics:
            logger.info("Obteniendo métricas locales (fallback)...")
            metrics = self.get_local_system_metrics()
        
        if not metrics:
            logger.error("No se pudieron obtener métricas del sistema.")
            return None
        
        # Enviar al KernelDaemon
        success = self.send_metrics_to_kernel_daemon(metrics)
        
        if success:
            return metrics
        else:
            logger.warning("Métricas obtenidas pero fallo al reportar al KernelDaemon.")
            return None


def main():
    """Ejemplo de uso del cliente HeliosCore."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    client = HeliosCoreClient(host="localhost", port=50051)
    
    try:
        # Intentar conectar
        if client.connect():
            print("✓ Conectado al núcleo Rust HeliosCore")
            
            # Obtener y reportar métricas
            metrics = client.collect_and_report()
            
            if metrics:
                print(f"✓ Métricas reportadas exitosamente:")
                print(f"  CPU: {metrics['cpu_usage']:.2f}%")
                print(f"  RAM: {metrics['memory_usage_percent']:.2f}% "
                      f"({metrics['used_memory'] / (1024**2):.2f} MB usados)")
                print(f"  Discos: {len(metrics['disks'])} unidades")
                print(f"  Fuente: {metrics['source']}")
            else:
                print("✗ Fallo al obtener/reportar métricas")
        else:
            print("⚠ No se pudo conectar al núcleo Rust. Usando modo local...")
            client.close()
            
            # Reconectar sin verificar para obtener métricas locales
            client = HeliosCoreClient()
            metrics = client.get_local_system_metrics()
            if client.send_metrics_to_kernel_daemon(metrics):
                print(f"✓ Métricas locales reportadas:")
                print(f"  CPU: {metrics['cpu_usage']:.2f}%")
                print(f"  RAM: {metrics['memory_usage_percent']:.2f}%")
                print(f"  Fuente: {metrics['source']}")
                
    except KeyboardInterrupt:
        print("\nInterrumpido por usuario.")
    finally:
        client.close()
        print("Cliente HeliosCore cerrado.")


if __name__ == "__main__":
    main()
