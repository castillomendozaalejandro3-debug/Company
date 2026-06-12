"""
Git Rollback - Sistema de rollback atómico de versiones usando Git.
Permite revertir cambios de forma segura ante fallos críticos.
"""
import asyncio
import logging
import subprocess
import os
from typing import Optional, List, Tuple
from dataclasses import dataclass

try:
    from .structured_logger import get_logger
except ImportError:
    from structured_logger import get_logger

logger = get_logger(__name__)

@dataclass
class CommitInfo:
    """Información de un commit."""
    hash: str
    short_hash: str
    message: str
    author: str
    timestamp: str

class GitRollback:
    """Gestor de operaciones de rollback con Git."""
    
    def __init__(self, repo_path: Optional[str] = None):
        self.repo_path = repo_path or os.getcwd()
        self._verify_git_repo()

    def _verify_git_repo(self):
        """Verifica que el directorio sea un repositorio Git válido."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--is-inside-work-tree"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True
            )
            if result.stdout.strip() != "true":
                raise RuntimeError("Not a git repository")
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Git verification failed: {e}")
        except FileNotFoundError:
            raise RuntimeError("Git is not installed or not in PATH")

    def _run_git_command(self, args: List[str]) -> Tuple[bool, str, str]:
        """Ejecuta un comando git y devuelve (success, stdout, stderr)."""
        try:
            result = subprocess.run(
                ["git"] + args,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=30
            )
            return (result.returncode == 0, result.stdout, result.stderr)
        except subprocess.TimeoutExpired:
            return (False, "", "Command timed out")
        except Exception as e:
            return (False, "", str(e))

    async def get_current_commit(self) -> Optional[CommitInfo]:
        """Obtiene información del commit actual."""
        success, stdout, stderr = self._run_git_command(["rev-parse", "HEAD"])
        if not success:
            logger.error(f"Failed to get current commit: {stderr}")
            return None
            
        full_hash = stdout.strip()
        
        # Obtener detalles del commit
        success, details, _ = self._run_git_command([
            "show", "-s", 
            "--format=%h|%an|%ad|%s",
            "--date=iso",
            full_hash
        ])
        
        if not success:
            return None
            
        parts = details.strip().split("|")
        if len(parts) >= 4:
            return CommitInfo(
                hash=full_hash,
                short_hash=parts[0],
                author=parts[1],
                timestamp=parts[2],
                message=parts[3]
            )
        return None

    async def get_commit_history(self, limit: int = 10) -> List[CommitInfo]:
        """Obtiene el historial de commits recientes."""
        success, stdout, stderr = self._run_git_command([
            "log", 
            f"-{limit}",
            "--format=%H|%h|%an|%ad|%s",
            "--date=iso"
        ])
        
        if not success:
            logger.error(f"Failed to get commit history: {stderr}")
            return []
            
        commits = []
        for line in stdout.strip().split("\n"):
            if line:
                parts = line.split("|")
                if len(parts) >= 5:
                    commits.append(CommitInfo(
                        hash=parts[0],
                        short_hash=parts[1],
                        author=parts[2],
                        timestamp=parts[3],
                        message="|".join(parts[4:])
                    ))
        return commits

    async def rollback_last_commit(self, preserve_changes: bool = False) -> bool:
        """
        Realiza rollback del último commit.
        
        Args:
            preserve_changes: Si True, mantiene los cambios en working directory.
                             Si False, descarta todos los cambios.
        """
        logger.info("Initiating rollback of last commit...")
        
        # Verificar estado actual
        current = await self.get_current_commit()
        if not current:
            logger.error("Cannot rollback: unable to determine current commit")
            return False
            
        logger.info(f"Current commit: {current.short_hash} - {current.message}")
        
        # Obtener commit anterior
        history = await self.get_commit_history(limit=2)
        if len(history) < 2:
            logger.error("Cannot rollback: no previous commit found")
            return False
            
        previous = history[1]
        logger.info(f"Rolling back to: {previous.short_hash} - {previous.message}")
        
        # Crear backup del estado actual (tag)
        backup_tag = f"backup-before-rollback-{current.short_hash}"
        success, _, stderr = self._run_git_command(["tag", backup_tag])
        if success:
            logger.info(f"Created backup tag: {backup_tag}")
        else:
            logger.warning(f"Failed to create backup tag: {stderr}")
        
        # Ejecutar rollback
        if preserve_changes:
            # Reset soft (mantiene cambios staged)
            success, _, stderr = self._run_git_command(["reset", "--soft", previous.hash])
        else:
            # Reset hard (descarta todos los cambios)
            logger.warning("Discarding all local changes!")
            success, _, stderr = self._run_git_command(["reset", "--hard", previous.hash])
            
        if not success:
            logger.error(f"Rollback failed: {stderr}")
            # Intentar restaurar desde tag de backup
            await self.restore_from_tag(backup_tag)
            return False
            
        logger.info(f"Successfully rolled back to {previous.short_hash}")
        
        # Registrar en auditoría si está disponible
        try:
            from .audit_logger import AuditLogger
            audit = AuditLogger()
            audit.log_event(
                event_type="GIT_ROLLBACK",
                details={
                    "from_commit": current.hash,
                    "to_commit": previous.hash,
                    "preserve_changes": preserve_changes,
                    "backup_tag": backup_tag
                }
            )
        except Exception:
            pass  # Auditoría no crítica para el rollback
            
        return True

    async def rollback_to_commit(self, target_hash: str, force: bool = False) -> bool:
        """
        Realiza rollback a un commit específico.
        
        Args:
            target_hash: Hash del commit objetivo (completo o corto).
            force: Si True, fuerza el rollback incluso con cambios no commiteados.
        """
        logger.info(f"Initiating rollback to commit: {target_hash}")
        
        # Verificar si hay cambios no commiteados
        success, stdout, _ = self._run_git_command(["status", "--porcelain"])
        if stdout.strip() and not force:
            logger.error("Cannot rollback: uncommitted changes exist. Use force=True to discard them.")
            return False
            
        # Verificar que el commit existe
        success, _, stderr = self._run_git_command(["rev-parse", "--verify", target_hash])
        if not success:
            logger.error(f"Target commit not found: {stderr}")
            return False
            
        # Crear backup
        current = await self.get_current_commit()
        backup_tag = None
        if current:
            backup_tag = f"backup-before-rollback-{current.short_hash}"
            self._run_git_command(["tag", backup_tag])
            
        # Ejecutar rollback hard
        success, _, stderr = self._run_git_command(["reset", "--hard", target_hash])
        
        if not success:
            logger.error(f"Rollback to {target_hash} failed: {stderr}")
            if backup_tag:
                await self.restore_from_tag(backup_tag)
            return False
            
        logger.info(f"Successfully rolled back to {target_hash}")
        return True

    async def restore_from_tag(self, tag_name: str) -> bool:
        """Restaura el estado desde un tag de backup."""
        logger.info(f"Restoring from backup tag: {tag_name}")
        
        success, _, stderr = self._run_git_command([
            "rev-parse", "--verify", f"refs/tags/{tag_name}"
        ])
        
        if not success:
            logger.error(f"Backup tag not found: {tag_name}")
            return False
            
        success, _, stderr = self._run_git_command(["reset", "--hard", tag_name])
        
        if success:
            logger.info(f"Successfully restored from {tag_name}")
            return True
        else:
            logger.error(f"Restore failed: {stderr}")
            return False

    async def create_checkpoint(self, message: str = "Manual checkpoint") -> Optional[str]:
        """
        Crea un checkpoint (commit) manual del estado actual.
        
        Returns:
            Hash del commit creado o None si falla.
        """
        logger.info(f"Creating checkpoint: {message}")
        
        # Stage all changes
        success, _, stderr = self._run_git_command(["add", "-A"])
        if not success:
            logger.error(f"Failed to stage changes: {stderr}")
            return None
            
        # Crear commit
        success, stdout, stderr = self._run_git_command([
            "commit", "-m", f"[CHECKPOINT] {message}"
        ])
        
        if not success:
            # Puede fallar si no hay cambios
            if "nothing to commit" in stderr.lower():
                logger.info("No changes to commit")
                current = await self.get_current_commit()
                return current.hash if current else None
            logger.error(f"Failed to create checkpoint: {stderr}")
            return None
            
        # Obtener hash del nuevo commit
        current = await self.get_current_commit()
        if current:
            logger.info(f"Checkpoint created: {current.short_hash}")
            return current.hash
            
        return None

    async def get_uncommitted_changes(self) -> List[str]:
        """Lista archivos con cambios no commiteados."""
        success, stdout, _ = self._run_git_command(["status", "--porcelain"])
        if not success or not stdout.strip():
            return []
            
        files = []
        for line in stdout.strip().split("\n"):
            if line.strip():
                # Formato: " M file.txt" o "M file.txt"
                parts = line.split()
                if len(parts) >= 2:
                    files.append(parts[-1])
                elif len(parts) == 1:
                    files.append(parts[0])
        return files

    async def has_uncommitted_changes(self) -> bool:
        """Verifica si hay cambios no commiteados."""
        changes = await self.get_uncommitted_changes()
        return len(changes) > 0
