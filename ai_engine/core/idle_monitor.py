"""
Idle Time Monitor - Sección 5.2 del Kernel Inmutable

Sensor de telemetría del mouse humano que detecta movimiento real del usuario
e interrumpe Workers del Dominio 2 (Asistente) cuando hay intervención humana.
"""

import asyncio
import logging
import threading
import time
from typing import Optional, Callable, Dict, Any
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)

try:
    from pynput import mouse, keyboard
    PYNPUT_AVAILABLE = True
except ImportError:
    PYNPUT_AVAILABLE = False
    logger.warning("pynput no disponible. Idle monitor en modo simulado.")

try:
    import pyautogui
    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False


class WorkerDomain(Enum):
    DOMAIN_1_CORE = "core"
    DOMAIN_2_ASSISTANT = "assistant"
    DOMAIN_3_TOOLS = "tools"


@dataclass
class IdleEvent:
    timestamp: float
    event_type: str
    source: str
    position: Optional[tuple] = None
    worker_id: Optional[str] = None


@dataclass
class MonitorState:
    last_human_activity: float = field(default_factory=time.time)
    last_worker_activity: float = field(default_factory=time.time)
    is_monitoring: bool = False
    active_workers: Dict[str, WorkerDomain] = field(default_factory=dict)
    interruption_count: int = 0
    total_idle_time: float = 0.0


class IdleTimeMonitor:
    """
    Monitor de tiempo inactivo con detección de intervención humana.
    Detecta movimiento real y emite señales para congelar Workers del Dominio 2.
    """
    
    def __init__(
        self,
        idle_threshold: float = 5.0,
        check_interval: float = 0.5,
        interrupt_on_human: bool = True
    ):
        self.idle_threshold = idle_threshold
        self.check_interval = check_interval
        self.interrupt_on_human = interrupt_on_human
        
        self._state = MonitorState()
        self._lock = threading.RLock()
        self._interruption_callbacks: Dict[str, Callable] = {}
        self._running = False
        self._monitor_thread: Optional[threading.Thread] = None
        self._mouse_listener: Optional[Any] = None
        self._keyboard_listener: Optional[Any] = None
    
    def register_worker(
        self,
        worker_id: str,
        domain: WorkerDomain,
        interrupt_callback: Optional[Callable] = None
    ) -> None:
        with self._lock:
            self._state.active_workers[worker_id] = domain
            if interrupt_callback and domain == WorkerDomain.DOMAIN_2_ASSISTANT:
                self._interruption_callbacks[worker_id] = interrupt_callback
                logger.debug(f"Worker {worker_id} registrado para interrupción")
    
    def unregister_worker(self, worker_id: str) -> None:
        with self._lock:
            self._state.active_workers.pop(worker_id, None)
            self._interruption_callbacks.pop(worker_id, None)
    
    def record_human_activity(
        self,
        event_type: str = "unknown",
        position: Optional[tuple] = None
    ) -> None:
        with self._lock:
            now = time.time()
            self._state.last_human_activity = now
            
            if self.interrupt_on_human and self._running:
                self._check_and_interrupt_workers(event_type, position)
            
            logger.debug(f"Actividad humana: {event_type}")
    
    def record_worker_activity(self, worker_id: str) -> None:
        with self._lock:
            self._state.last_worker_activity = time.time()
    
    def _check_and_interrupt_workers(
        self,
        event_type: str,
        position: Optional[tuple]
    ) -> None:
        interrupted = []
        
        for worker_id, domain in self._state.active_workers.items():
            if domain != WorkerDomain.DOMAIN_2_ASSISTANT:
                continue
            if worker_id not in self._interruption_callbacks:
                continue
            
            callback = self._interruption_callbacks[worker_id]
            try:
                logger.warning(
                    f"INTERRUPCIÓN: Humano ({event_type}). "
                    f"Congelando Worker {worker_id}"
                )
                callback()
                self._state.interruption_count += 1
                interrupted.append(worker_id)
            except Exception as e:
                logger.error(f"Error al interrumpir {worker_id}: {e}")
        
        if interrupted:
            logger.info(f"Workers interrumpidos: {interrupted}")
    
    def get_idle_time(self) -> float:
        with self._lock:
            return time.time() - self._state.last_human_activity
    
    def is_idle(self) -> bool:
        return self.get_idle_time() >= self.idle_threshold
    
    def get_state(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "is_monitoring": self._state.is_monitoring,
                "idle_time": self.get_idle_time(),
                "is_idle": self.is_idle(),
                "active_workers": len(self._state.active_workers),
                "domain_2_workers": sum(
                    1 for d in self._state.active_workers.values()
                    if d == WorkerDomain.DOMAIN_2_ASSISTANT
                ),
                "interruption_count": self._state.interruption_count,
                "total_idle_time": self._state.total_idle_time,
            }
    
    def start(self) -> None:
        if self._running:
            return
        
        if not PYNPUT_AVAILABLE and not PYAUTOGUI_AVAILABLE:
            logger.warning("Modo simulado (sin pynput/pyautogui)")
            self._running = True
            self._state.is_monitoring = True
            self._start_simulation_mode()
            return
        
        self._running = True
        self._state.is_monitoring = True
        
        if PYNPUT_AVAILABLE:
            self._start_pynput_listeners()
        elif PYAUTOGUI_AVAILABLE:
            self._start_pyautogui_polling()
        
        logger.info("Idle monitor iniciado")
    
    def stop(self) -> None:
        self._running = False
        self._state.is_monitoring = False
        
        if self._mouse_listener:
            try:
                self._mouse_listener.stop()
            except Exception:
                pass
        
        if self._keyboard_listener:
            try:
                self._keyboard_listener.stop()
            except Exception:
                pass
        
        logger.info("Idle monitor detenido")
    
    def _start_pynput_listeners(self) -> None:
        def on_mouse_move(x, y):
            if self._running:
                self.record_human_activity("mouse_move", (x, y))
        
        def on_mouse_click(x, y, button, pressed):
            if self._running and pressed:
                self.record_human_activity("mouse_click", (x, y))
        
        def on_key_press(key):
            if self._running:
                self.record_human_activity("key_press")
        
        try:
            self._mouse_listener = mouse.Listener(
                on_move=on_mouse_move,
                on_click=on_mouse_click
            )
            self._mouse_listener.start()
            
            self._keyboard_listener = keyboard.Listener(
                on_press=on_key_press
            )
            self._keyboard_listener.start()
        except Exception as e:
            logger.error(f"Error listeners: {e}")
            self._start_pyautogui_polling()
    
    def _start_pyautogui_polling(self) -> None:
        if not PYAUTOGUI_AVAILABLE:
            return
        
        last_position = pyautogui.position()
        
        def poll_loop():
            nonlocal last_position
            while self._running:
                try:
                    current_position = pyautogui.position()
                    if current_position != last_position:
                        self.record_human_activity(
                            "mouse_move",
                            tuple(current_position)
                        )
                        last_position = current_position
                    time.sleep(self.check_interval)
                except Exception:
                    time.sleep(1)
        
        thread = threading.Thread(target=poll_loop, daemon=True)
        thread.start()
    
    def _start_simulation_mode(self) -> None:
        def simulation_loop():
            while self._running:
                with self._lock:
                    idle = self.get_idle_time()
                    if idle >= self.idle_threshold:
                        self._state.total_idle_time += self.check_interval
                time.sleep(self.check_interval)
        
        thread = threading.Thread(target=simulation_loop, daemon=True)
        thread.start()


_monitor_instance: Optional[IdleTimeMonitor] = None


def get_idle_monitor() -> IdleTimeMonitor:
    global _monitor_instance
    if _monitor_instance is None:
        _monitor_instance = IdleTimeMonitor()
    return _monitor_instance


def init_idle_monitor(
    idle_threshold: float = 5.0,
    interrupt_on_human: bool = True
) -> IdleTimeMonitor:
    global _monitor_instance
    _monitor_instance = IdleTimeMonitor(
        idle_threshold=idle_threshold,
        interrupt_on_human=interrupt_on_human
    )
    return _monitor_instance
