"""
Tests reales para la matriz de certificación de seguridad.
Prueba zeroing de memoria, validación de rutas y triggers SQLite.
Sin mocks, código funcional.
"""
import pytest
import sqlite3
import os
from pathlib import Path
import sys

# Asegurar que el directorio raíz del proyecto esté en el path
sys.path.insert(0, str(Path(__file__).parent.parent))

from ai_engine.core.crypto_manager import zero_memory
from ai_engine.core.security.path_validator import validate_path
from ai_engine.core.audit_logger import AuditLogger


class TestZeroMemory:
    """Pruebas reales para la función zero_memory."""

    def test_zero_memory_overwrites_data(self):
        """Verifica que zero_memory sobrescribe físicamente los datos con ceros."""
        # Crear un bytearray con datos específicos
        original_data = bytearray(b'\xDE\xAD\xBE\xEF\xCA\xFE\xBA\xBE')
        data_copy = bytearray(original_data)  # Copia para comparar
        
        # Verificar que tiene datos antes de limpiar
        assert any(b != 0 for b in data_copy), "Los datos iniciales no deberían ser cero"
        
        # Ejecutar zero_memory
        zero_memory(data_copy)
        
        # Verificar que todos los bytes son ahora cero
        assert all(b == 0 for b in data_copy), "Todos los bytes deberían ser cero después de zero_memory"
        assert len(data_copy) == len(original_data), "La longitud debería mantenerse"

    def test_zero_memory_empty_buffer(self):
        """Verifica que zero_memory maneja buffers vacíos correctamente."""
        empty_data = bytearray()
        zero_memory(empty_data)
        assert len(empty_data) == 0

    def test_zero_memory_large_buffer(self):
        """Verifica zero_memory con un buffer grande."""
        size = 1024 * 1024  # 1 MB
        large_data = bytearray(os.urandom(size))
        
        # Verificar que hay datos no cero
        assert any(b != 0 for b in large_data), "El buffer aleatorio debería tener datos no cero"
        
        zero_memory(large_data)
        
        # Verificar que todo es cero
        assert all(b == 0 for b in large_data), "Todo el buffer grande debería ser cero"


class TestPathValidator:
    """Pruebas reales para el validador de rutas."""

    def test_validate_path_inside_workspace(self, tmp_path):
        """Verifica que rutas dentro del workspace son válidas."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        target = workspace / "subdir" / "file.txt"
        target.parent.mkdir()
        target.write_text("test content")
        
        # Debería retornar la ruta resuelta sin lanzar excepción
        result = validate_path(workspace, target)
        assert result == target.resolve()

    def test_validate_path_outside_workspace_raises(self, tmp_path):
        """Verifica que rutas fuera del workspace lanzan PermissionError."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        outside = tmp_path / "outside" / "secret.txt"
        outside.parent.mkdir()
        outside.write_text("secret")
        
        # Debería lanzar PermissionError
        with pytest.raises(PermissionError):
            validate_path(workspace, outside)

    def test_validate_path_symlink_escape_raises(self, tmp_path):
        """Verifica que symlinks que escapan del workspace lanzan PermissionError."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        
        outside = tmp_path / "outside"
        outside.mkdir()
        secret_file = outside / "secret.txt"
        secret_file.write_text("secret")
        
        # Crear symlink dentro del workspace que apunta fuera
        symlink = workspace / "escape_link"
        symlink.symlink_to(secret_file)
        
        # Debería lanzar PermissionError porque el objetivo real está fuera
        with pytest.raises(PermissionError):
            validate_path(workspace, symlink)

    def test_validate_path_relative_path(self, tmp_path, monkeypatch):
        """Verifica que rutas relativas se resuelven correctamente."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        target = workspace / "file.txt"
        target.write_text("test")
        
        # Cambiar al directorio workspace para probar rutas relativas
        monkeypatch.chdir(workspace)
        
        result = validate_path(workspace, Path("file.txt"))
        assert result == target.resolve()


class TestAuditLoggerTriggers:
    """Pruebas reales para los triggers de auditoría SQLite."""

    def test_audit_logger_creates_table_and_triggers(self, tmp_path):
        """Verifica que la tabla y los triggers se crean correctamente."""
        db_path = tmp_path / "audit_test.db"
        
        # Crear el logger (esto crea la tabla y triggers)
        logger = AuditLogger(str(db_path))
        
        # Conectar directamente para verificar la estructura
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        # Verificar que la tabla existe
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='audit_events'")
        assert cursor.fetchone() is not None, "La tabla audit_events debería existir"
        
        # Verificar que los triggers existen
        cursor.execute("SELECT name FROM sqlite_master WHERE type='trigger'")
        triggers = [row[0] for row in cursor.fetchall()]
        assert 'trg_block_audit_update' in triggers, "El trigger de UPDATE debería existir"
        assert 'trg_block_audit_delete' in triggers, "El trigger de DELETE debería existir"
        
        conn.close()

    def test_audit_logger_insert_works(self, tmp_path):
        """Verifica que las inserciones funcionan correctamente."""
        db_path = tmp_path / "audit_test.db"
        logger = AuditLogger(str(db_path))
        
        # Registrar un evento (action debe ser string, details para datos complejos)
        import json
        event_id = logger.log_event("TEST_EVENT", "test_action", user_id="user123", details=json.dumps({"key": "value"}))
        
        assert event_id is not None
        assert isinstance(event_id, int)
        
        # Verificar en la base de datos
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT event_type, action, details, user_id FROM audit_events WHERE id=?", (event_id,))
        row = cursor.fetchone()
        
        assert row is not None
        assert row[0] == "TEST_EVENT"
        assert row[1] == "test_action"
        assert row[2] == '{"key": "value"}'
        assert row[3] == "user123"
        
        conn.close()

    def test_audit_logger_update_blocked(self, tmp_path):
        """Verifica que los UPDATE están bloqueados por el trigger."""
        db_path = tmp_path / "audit_test.db"
        logger = AuditLogger(str(db_path))
        
        # Insertar un evento
        event_id = logger.log_event("TEST_EVENT", "test_action", details='{"data": "original"}')
        
        # Intentar actualizar directamente con SQL
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        with pytest.raises(sqlite3.DatabaseError) as exc_info:
            cursor.execute("UPDATE audit_events SET action=? WHERE id=?", ("MODIFIED", event_id))
        
        assert "IMMUTABLE" in str(exc_info.value).upper() or "FAIL" in str(exc_info.value).upper()
        conn.close()
        
        # Verificar que los datos no cambiaron
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT action FROM audit_events WHERE id=?", (event_id,))
        row = cursor.fetchone()
        assert row[0] == "test_action", "El evento no debería haber sido modificado"
        conn.close()

    def test_audit_logger_delete_blocked(self, tmp_path):
        """Verifica que los DELETE están bloqueados por el trigger."""
        db_path = tmp_path / "audit_test.db"
        logger = AuditLogger(str(db_path))
        
        # Insertar un evento
        event_id = logger.log_event("TEST_EVENT", "test_action", details='{"data": "to_delete"}')
        
        # Intentar eliminar directamente con SQL
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        with pytest.raises(sqlite3.DatabaseError) as exc_info:
            cursor.execute("DELETE FROM audit_events WHERE id=?", (event_id,))
        
        assert "IMMUTABLE" in str(exc_info.value).upper() or "FAIL" in str(exc_info.value).upper()
        conn.close()
        
        # Verificar que el registro sigue existiendo
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM audit_events WHERE id=?", (event_id,))
        count = cursor.fetchone()[0]
        assert count == 1, "El evento no debería haber sido eliminado"
        conn.close()

    def test_audit_logger_wal_mode(self, tmp_path):
        """Verifica que la base de datos está en modo WAL."""
        db_path = tmp_path / "audit_test.db"
        logger = AuditLogger(str(db_path))
        
        # Conectar y verificar el modo journal
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode")
        mode = cursor.fetchone()[0]
        
        assert mode.lower() == "wal", f"El modo journal debería ser WAL, pero es {mode}"
        conn.close()
