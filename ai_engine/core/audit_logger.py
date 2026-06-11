"""
Audit Logger Module for AI Engine.
Connects to SQLite in WAL mode and creates an immutable audit trail.
Uses SQL triggers to physically block UPDATE and DELETE operations.
"""

import sqlite3
import os
from pathlib import Path
from typing import Optional


class AuditLogger:
    """
    Manages SQLite audit logging with Write-Ahead Logging (WAL) mode
    and strict immutability enforced via SQL triggers.
    """

    def __init__(self, db_path: str = "audit_log.db"):
        """
        Initialize the Audit Logger.
        
        Args:
            db_path: Path to the SQLite database file.
        """
        self.db_path = Path(db_path)
        self.conn: Optional[sqlite3.Connection] = None
        self._initialize_db()

    def _initialize_db(self) -> None:
        """
        Establish connection, enable WAL mode, and create schema with triggers.
        """
        # Ensure parent directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Connect to SQLite
        self.conn = sqlite3.connect(str(self.db_path))
        
        # Enable WAL mode immediately
        self.conn.execute("PRAGMA journal_mode=WAL;")
        
        # Create table and triggers
        self._create_schema()

    def _create_schema(self) -> None:
        """
        Create the audit_events table and immutability triggers.
        """
        cursor = self.conn.cursor()

        # Create the audit_events table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL DEFAULT (datetime('now')),
                event_type TEXT NOT NULL,
                user_id TEXT,
                action TEXT NOT NULL,
                resource TEXT,
                details TEXT,
                ip_address TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
        """)

        # Create index for performance
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_timestamp 
            ON audit_events(timestamp);
        """)

        # Trigger to BLOCK UPDATE operations
        # This uses RAISE(FAIL) to abort any transaction attempting to modify a row
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS trg_block_audit_update
            BEFORE UPDATE ON audit_events
            BEGIN
                SELECT RAISE(FAIL, 'IMMUTABLE: Update operations on audit_events are forbidden.');
            END;
        """)

        # Trigger to BLOCK DELETE operations
        # This uses RAISE(FAIL) to abort any transaction attempting to remove a row
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS trg_block_audit_delete
            BEFORE DELETE ON audit_events
            BEGIN
                SELECT RAISE(FAIL, 'IMMUTABLE: Delete operations on audit_events are forbidden.');
            END;
        """)

        self.conn.commit()

    def log_event(
        self,
        event_type: str,
        action: str,
        user_id: Optional[str] = None,
        resource: Optional[str] = None,
        details: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> int:
        """
        Record a new audit event.
        
        Args:
            event_type: Type of event (e.g., 'LOGIN', 'ACCESS', 'ERROR').
            action: Description of the action performed.
            user_id: Identifier of the user performing the action.
            resource: Resource affected by the action.
            details: JSON string or text with additional details.
            ip_address: IP address of the requester.
            
        Returns:
            The ID of the newly inserted row.
        """
        if self.conn is None:
            raise RuntimeError("Database connection not initialized.")

        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO audit_events (event_type, user_id, action, resource, details, ip_address)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (event_type, user_id, action, resource, details, ip_address))
        
        self.conn.commit()
        return cursor.lastrowid

    def get_events(self, limit: int = 100) -> list:
        """
        Retrieve recent audit events.
        
        Args:
            limit: Maximum number of events to return.
            
        Returns:
            List of dictionaries containing event data.
        """
        if self.conn is None:
            raise RuntimeError("Database connection not initialized.")

        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT id, timestamp, event_type, user_id, action, resource, details, ip_address
            FROM audit_events
            ORDER BY timestamp DESC
            LIMIT ?
        """, (limit,))
        
        columns = ['id', 'timestamp', 'event_type', 'user_id', 'action', 'resource', 'details', 'ip_address']
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def test_immutability(self) -> bool:
        """
        Verify that the triggers are active and blocking modifications.
        Returns True if the database correctly rejects updates/deletes.
        """
        if self.conn is None:
            raise RuntimeError("Database connection not initialized.")

        cursor = self.conn.cursor()
        
        # Insert a test row
        cursor.execute("""
            INSERT INTO audit_events (event_type, action, details)
            VALUES ('TEST', 'VERIFY_IMMUTABILITY', 'Temporary test row')
        """)
        test_id = cursor.lastrowid
        self.conn.commit()

        update_blocked = False
        delete_blocked = False

        # Attempt UPDATE (should fail)
        try:
            cursor.execute("UPDATE audit_events SET details = 'HACKED' WHERE id = ?", (test_id,))
            self.conn.commit()
        except sqlite3.DatabaseError as e:
            if "IMMUTABLE" in str(e) or "FAIL" in str(e):
                update_blocked = True

        # Attempt DELETE (should fail)
        try:
            cursor.execute("DELETE FROM audit_events WHERE id = ?", (test_id,))
            self.conn.commit()
        except sqlite3.DatabaseError as e:
            if "IMMUTABLE" in str(e) or "FAIL" in str(e):
                delete_blocked = True
        
        # Cleanup: Since we can't delete via SQL, we must rely on the test logic 
        # actually failing to delete, leaving the row there. 
        # In a real scenario, you might need to drop the trigger to clean up test data,
        # but for this verification function, we just confirm the block worked.
        # Note: The test row remains in the DB because the delete was blocked.
        
        return update_blocked and delete_blocked

    def close(self) -> None:
        """Close the database connection."""
        if self.conn:
            self.conn.close()
            self.conn = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


if __name__ == "__main__":
    # Demo usage
    import tempfile
    
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_file = tmp.name

    try:
        logger = AuditLogger(db_file)
        
        # Log some events
        logger.log_event("LOGIN", "User authenticated", user_id="u123", ip_address="192.168.1.1")
        logger.log_event("ACCESS", "File downloaded", resource="/data/report.pdf", user_id="u123")
        
        print("Events logged:")
        for event in logger.get_events():
            print(f" - [{event['timestamp']}] {event['event_type']}: {event['action']}")
        
        # Verify immutability
        if logger.test_immutability():
            print("\n[SUCCESS] Immutability triggers are active. UPDATE and DELETE are blocked.")
        else:
            print("\n[FAILURE] Triggers did not block modifications.")
            
        logger.close()
        
    finally:
        # Clean up temp file
        if os.path.exists(db_file):
            os.remove(db_file)
        # Remove WAL/SHM files if they exist
        for suffix in ["-wal", "-shm"]:
            path = db_file + suffix
            if os.path.exists(path):
                os.remove(path)
