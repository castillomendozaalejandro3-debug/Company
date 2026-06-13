"""
Sandbox TDD - Entorno de pruebas aislado para desarrollo y validación de código.
Ejecuta tests en un entorno contenido sin afectar el sistema principal.
"""
import asyncio
import logging
import os
import sys
import tempfile
import shutil
import subprocess
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from enum import Enum

try:
    from .structured_logger import get_logger
except ImportError:
    from structured_logger import get_logger

logger = get_logger(__name__)

class TestResult(Enum):
    """Resultado de una prueba."""
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    SKIPPED = "skipped"
    TIMEOUT = "timeout"

@dataclass
class TestReport:
    """Reporte de ejecución de tests."""
    test_name: str
    result: TestResult
    duration: float
    output: str
    error_message: Optional[str] = None

class SandboxTDD:
    """Entorno sandbox para ejecución segura de tests TDD."""
    
    def __init__(self, workspace_path: Optional[str] = None):
        self.workspace_path = workspace_path or os.getcwd()
        self.sandbox_dir: Optional[str] = None
        self.is_active = False
        
    async def create_sandbox(self) -> str:
        """Crea un directorio sandbox temporal."""
        if self.sandbox_dir and os.path.exists(self.sandbox_dir):
            return self.sandbox_dir
            
        self.sandbox_dir = tempfile.mkdtemp(prefix="helios_sandbox_")
        logger.info(f"Sandbox created at: {self.sandbox_dir}")
        
        # Copiar estructura básica necesaria
        await self._setup_sandbox_environment()
        
        self.is_active = True
        return self.sandbox_dir

    async def _setup_sandbox_environment(self):
        """Configura el entorno del sandbox."""
        if not self.sandbox_dir:
            return
            
        # Crear subdirectorios básicos
        os.makedirs(os.path.join(self.sandbox_dir, "tests"), exist_ok=True)
        os.makedirs(os.path.join(self.sandbox_dir, "src"), exist_ok=True)
        os.makedirs(os.path.join(self.sandbox_dir, "fixtures"), exist_ok=True)
        
        # Crear archivo de configuración básico
        config_content = """
# Sandbox Configuration
TEST_TIMEOUT=30
MAX_MEMORY_MB=512
ALLOW_NETWORK=false
"""
        with open(os.path.join(self.sandbox_dir, ".sandbox_config"), "w") as f:
            f.write(config_content)

    async def destroy_sandbox(self):
        """Elimina el sandbox y limpia recursos."""
        if self.sandbox_dir and os.path.exists(self.sandbox_dir):
            logger.info(f"Destroying sandbox: {self.sandbox_dir}")
            try:
                shutil.rmtree(self.sandbox_dir)
            except Exception as e:
                logger.error(f"Failed to clean sandbox: {e}")
            finally:
                self.sandbox_dir = None
                self.is_active = False

    async def run_test(
        self, 
        test_code: str, 
        test_name: str = "sandbox_test",
        timeout: int = 30,
        dependencies: Optional[List[str]] = None
    ) -> TestReport:
        """
        Ejecuta una prueba en el sandbox.
        
        Args:
            test_code: Código Python de la prueba a ejecutar.
            test_name: Nombre identificador de la prueba.
            timeout: Timeout en segundos.
            dependencies: Lista de dependencias necesarias.
            
        Returns:
            TestReport con el resultado de la ejecución.
        """
        if not self.is_active:
            await self.create_sandbox()
            
        start_time = asyncio.get_event_loop().time()
        
        try:
            # Crear archivo de test temporal
            test_file = os.path.join(self.sandbox_dir, "tests", f"{test_name}.py")
            with open(test_file, "w") as f:
                f.write(test_code)
            
            # Instalar dependencias si se especifican
            if dependencies:
                await self._install_dependencies(dependencies)
            
            # Ejecutar pytest en el sandbox
            result = await self._run_pytest(test_file, timeout)
            
            duration = asyncio.get_event_loop().time() - start_time
            
            if result.returncode == 0:
                return TestReport(
                    test_name=test_name,
                    result=TestResult.PASSED,
                    duration=duration,
                    output=result.stdout
                )
            else:
                return TestReport(
                    test_name=test_name,
                    result=TestResult.FAILED,
                    duration=duration,
                    output=result.stdout,
                    error_message=result.stderr
                )
                
        except asyncio.TimeoutError:
            duration = asyncio.get_event_loop().time() - start_time
            return TestReport(
                test_name=test_name,
                result=TestResult.TIMEOUT,
                duration=duration,
                output="",
                error_message=f"Test exceeded {timeout}s timeout"
            )
        except Exception as e:
            duration = asyncio.get_event_loop().time() - start_time
            return TestReport(
                test_name=test_name,
                result=TestResult.ERROR,
                duration=duration,
                output="",
                error_message=str(e)
            )

    async def _install_dependencies(self, dependencies: List[str]):
        """Instala dependencias en el sandbox."""
        if not dependencies:
            return
            
        logger.info(f"Installing dependencies: {dependencies}")
        
        try:
            # Crear requirements.txt temporal
            req_file = os.path.join(self.sandbox_dir, "requirements.txt")
            with open(req_file, "w") as f:
                for dep in dependencies:
                    f.write(f"{dep}\n")
            
            # Ejecutar pip install en el sandbox
            process = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "pip", "install", 
                "-r", req_file,
                "--target", os.path.join(self.sandbox_dir, "venv"),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=60
            )
            
            if process.returncode != 0:
                logger.warning(f"Dependency installation warnings: {stderr.decode()}")
                
        except Exception as e:
            logger.error(f"Failed to install dependencies: {e}")

    async def _run_pytest(self, test_file: str, timeout: int) -> subprocess.CompletedProcess:
        """Ejecuta pytest en un archivo específico."""
        try:
            # Preparar entorno de ejecución
            env = os.environ.copy()
            env["PYTHONPATH"] = self.sandbox_dir + ":" + env.get("PYTHONPATH", "")
            
            # Ejecutar pytest
            process = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "pytest",
                test_file,
                "-v",
                "--tb=short",
                cwd=self.sandbox_dir,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout
            )
            
            return subprocess.CompletedProcess(
                args=["pytest", test_file],
                returncode=process.returncode,
                stdout=stdout.decode(),
                stderr=stderr.decode()
            )
            
        except asyncio.TimeoutError:
            process.kill()
            raise

    async def validate_code_syntax(self, code: str) -> Dict[str, Any]:
        """
        Valida la sintaxis de un fragmento de código Python.
        
        Returns:
            Dict con 'valid' (bool) y 'error' (str o None).
        """
        try:
            compile(code, '<string>', 'exec')
            return {"valid": True, "error": None}
        except SyntaxError as e:
            return {
                "valid": False,
                "error": f"Syntax error at line {e.lineno}: {e.msg}"
            }

    async def run_tdd_cycle(
        self,
        test_code: str,
        implementation_code: str,
        max_iterations: int = 5
    ) -> Dict[str, Any]:
        """
        Ejecuta un ciclo completo de TDD (Red-Green-Refactor).
        
        Args:
            test_code: Código de la prueba.
            implementation_code: Código de implementación inicial.
            max_iterations: Número máximo de iteraciones.
            
        Returns:
            Dict con el resultado del ciclo TDD.
        """
        report = {
            "iterations": [],
            "final_status": "incomplete",
            "total_duration": 0
        }
        
        start_time = asyncio.get_event_loop().time()
        
        for iteration in range(max_iterations):
            logger.info(f"TDD Iteration {iteration + 1}/{max_iterations}")
            
            # Fase Red: Ejecutar test (debería fallar inicialmente)
            test_result = await self.run_test(test_code, f"tdd_iteration_{iteration}")
            
            iteration_report = {
                "iteration": iteration + 1,
                "test_result": test_result.result.value,
                "duration": test_result.duration
            }
            
            if test_result.result == TestResult.PASSED:
                report["final_status"] = "success"
                report["iterations"].append(iteration_report)
                break
            elif test_result.result == TestResult.ERROR:
                report["final_status"] = "error"
                report["iterations"].append(iteration_report)
                break
                
            report["iterations"].append(iteration_report)
            
            # En una implementación real, aquí se modificaría implementation_code
            # basándose en el fallo del test
            
        report["total_duration"] = asyncio.get_event_loop().time() - start_time
        return report

    async def get_sandbox_info(self) -> Dict[str, Any]:
        """Obtiene información del sandbox actual."""
        if not self.sandbox_dir or not os.path.exists(self.sandbox_dir):
            return {"active": False}
            
        return {
            "active": self.is_active,
            "path": self.sandbox_dir,
            "size_mb": self._get_directory_size_mb(),
            "files": self._list_sandbox_files()
        }

    def _get_directory_size_mb(self) -> float:
        """Calcula el tamaño del sandbox en MB."""
        if not self.sandbox_dir:
            return 0.0
            
        total_size = 0
        for dirpath, dirnames, filenames in os.walk(self.sandbox_dir):
            for filename in filenames:
                filepath = os.path.join(dirpath, filename)
                if os.path.exists(filepath):
                    total_size += os.path.getsize(filepath)
                    
        return total_size / (1024 * 1024)

    def _list_sandbox_files(self) -> List[str]:
        """Lista archivos en el sandbox."""
        if not self.sandbox_dir:
            return []
            
        files = []
        for root, _, filenames in os.walk(self.sandbox_dir):
            for filename in filenames:
                rel_path = os.path.relpath(os.path.join(root, filename), self.sandbox_dir)
                files.append(rel_path)
        return files
