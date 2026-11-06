"""
AI-OS Persistent Storage Subsystem
Production-grade transactional SQLite storage with WAL (Write-Ahead Logging) mode.
Maintains persistent state for:
- Agent Process Table (survives reboots)
- Capability Tokens
- Security Audit Log
- Associative Semantic Memory (Vector Graph)
- Inter-Agent Message Bus (IPC)
"""

import os
import time
import json
import sqlite3
import math
import hashlib
from typing import Dict, Any, List, Optional

UNIFIED_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(UNIFIED_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "aios.db")

os.makedirs(DATA_DIR, exist_ok=True)

class StorageManager:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA busy_timeout = 5000;")
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            # 1. Agent Processes
            conn.execute("""
            CREATE TABLE IF NOT EXISTS agents (
                pid INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                goal TEXT NOT NULL,
                status TEXT NOT NULL,
                max_tokens INTEGER NOT NULL,
                tokens_used INTEGER NOT NULL DEFAULT 0,
                current_step INTEGER NOT NULL DEFAULT 0,
                total_steps INTEGER NOT NULL DEFAULT 3,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                token_id TEXT
            );
            """)

            # 2. Agent Logs
            conn.execute("""
            CREATE TABLE IF NOT EXISTS agent_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pid INTEGER NOT NULL,
                step INTEGER NOT NULL,
                message TEXT NOT NULL,
                log_type TEXT NOT NULL DEFAULT 'INFO',
                timestamp REAL NOT NULL,
                FOREIGN KEY(pid) REFERENCES agents(pid)
            );
            """)

            # 3. Capability Tokens
            conn.execute("""
            CREATE TABLE IF NOT EXISTS capability_tokens (
                token_id TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL,
                issued_at INTEGER NOT NULL,
                expires_at INTEGER NOT NULL,
                max_tokens INTEGER NOT NULL,
                scopes_json TEXT NOT NULL,
                signature TEXT NOT NULL
            );
            """)

            # 4. Semantic Associative Memory
            conn.execute("""
            CREATE TABLE IF NOT EXISTS semantic_memory (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                vector_json TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'system',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                timestamp REAL NOT NULL
            );
            """)

            # 5. Security Audit Log
            conn.execute("""
            CREATE TABLE IF NOT EXISTS security_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pid INTEGER,
                event_type TEXT NOT NULL,
                target TEXT NOT NULL,
                decision TEXT NOT NULL,
                reason TEXT NOT NULL,
                timestamp REAL NOT NULL
            );
            """)

            # 6. Inter-Agent Communication Bus (IPC)
            conn.execute("""
            CREATE TABLE IF NOT EXISTS inter_agent_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_pid INTEGER NOT NULL,
                to_pid INTEGER NOT NULL,
                payload_json TEXT NOT NULL,
                is_read INTEGER NOT NULL DEFAULT 0,
                timestamp REAL NOT NULL
            );
            """)
            conn.commit()

        self._seed_default_memories()

    def _seed_default_memories(self):
        if self.count_memories() > 0:
            return
        defaults = [
            ("mem_001", "Architecture: Microkernel abstraction with seL4-inspired capability tokens and Rust IPC.", "system"),
            ("mem_002", "Hardware: Apple Silicon unified memory acceleration for local quantized models (MPS/Metal).", "system"),
            ("mem_003", "Security Policy: Outbound network calls require hardware biometric or user confirmation.", "policy"),
            ("mem_004", "Telemetry: Target turnaround latency sub-50ms for local intent-to-action pipeline.", "telemetry")
        ]
        for mid, text, src in defaults:
            self.insert_memory(text, source=src, custom_id=mid)

    # Agent Operations
    def save_agent(self, agent_dict: Dict[str, Any]):
        with self._get_connection() as conn:
            conn.execute("""
            INSERT INTO agents (pid, name, goal, status, max_tokens, tokens_used, current_step, total_steps, created_at, updated_at, token_id)
            VALUES (:pid, :name, :goal, :status, :max_tokens, :tokens_used, :current_step, :total_steps, :created_at, :updated_at, :token_id)
            ON CONFLICT(pid) DO UPDATE SET
                status = excluded.status,
                tokens_used = excluded.tokens_used,
                current_step = excluded.current_step,
                updated_at = excluded.updated_at;
            """, agent_dict)
            conn.commit()

    def get_agent(self, pid: int) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute("SELECT * FROM agents WHERE pid = ?", (pid,))
            row = cur.fetchone()
            return dict(row) if row else None

    def list_agents(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute("SELECT * FROM agents ORDER BY pid ASC")
            return [dict(r) for r in cur.fetchall()]

    def append_log(self, pid: int, step: int, message: str, log_type: str = "INFO"):
        with self._get_connection() as conn:
            conn.execute("""
            INSERT INTO agent_logs (pid, step, message, log_type, timestamp)
            VALUES (?, ?, ?, ?, ?)
            """, (pid, step, message, log_type, time.time()))
            conn.commit()

    def get_logs(self, pid: int, limit: int = 50) -> List[str]:
        with self._get_connection() as conn:
            cur = conn.execute("""
            SELECT timestamp, step, message, log_type FROM agent_logs
            WHERE pid = ? ORDER BY id ASC LIMIT ?
            """, (pid, limit))
            logs = []
            for ts, step, msg, ltype in cur.fetchall():
                tstr = time.strftime('%H:%M:%S', time.localtime(ts))
                prefix = f"[{tstr}] [Step {step}]"
                if ltype == "SECURITY":
                    logs.append(f"{prefix} \033[91m[SECURITY BLOCK] {msg}\033[0m")
                elif ltype == "SUCCESS":
                    logs.append(f"{prefix} \033[92m{msg}\033[0m")
                else:
                    logs.append(f"{prefix} {msg}")
            return logs

    # Security Audit
    def log_security(self, pid: Optional[int], event_type: str, target: str, decision: str, reason: str):
        with self._get_connection() as conn:
            conn.execute("""
            INSERT INTO security_audit (pid, event_type, target, decision, reason, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
            """, (pid, event_type, target, decision, reason, time.time()))
            conn.commit()

    def list_security_audits(self, limit: int = 25) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute("SELECT * FROM security_audit ORDER BY id DESC LIMIT ?", (limit,))
            return [dict(r) for r in cur.fetchall()]

    # Semantic Associative Memory
    def insert_memory(self, content: str, source: str = "user", custom_id: Optional[str] = None) -> str:
        eid = custom_id or f"mem_{hashlib.sha256(content.encode()).hexdigest()[:8]}"
        # Generate 4-dimensional normalized vector
        h = hashlib.sha256(content.encode()).digest()
        vec = [float(b) / 255.0 for b in h[:4]]
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        norm_vec = [x / norm for x in vec]

        with self._get_connection() as conn:
            conn.execute("""
            INSERT OR REPLACE INTO semantic_memory (id, content, vector_json, source, metadata_json, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
            """, (eid, content, json.dumps(norm_vec), source, "{}", time.time()))
            conn.commit()
        return eid

    def search_memory(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        h = hashlib.sha256(query.encode()).digest()
        q_vec = [float(b) / 255.0 for b in h[:4]]
        norm_q = math.sqrt(sum(x * x for x in q_vec)) or 1.0
        norm_q_vec = [x / norm_q for x in q_vec]

        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute("SELECT id, content, vector_json, source, timestamp FROM semantic_memory")
            rows = cur.fetchall()

        results = []
        for r in rows:
            vec = json.loads(r["vector_json"])
            dot = sum(a * b for a, b in zip(norm_q_vec, vec))
            results.append({
                "id": r["id"],
                "content": r["content"],
                "source": r["source"],
                "similarity": round(dot, 3),
                "timestamp": r["timestamp"]
            })
        results.sort(key=lambda x: x["similarity"], reverse=True)
        return results[:top_k]

    def count_memories(self) -> int:
        with self._get_connection() as conn:
            cur = conn.execute("SELECT COUNT(*) FROM semantic_memory")
            return cur.fetchone()[0]

    # Inter-Agent IPC
    def send_agent_message(self, from_pid: int, to_pid: int, payload: Dict[str, Any]):
        with self._get_connection() as conn:
            conn.execute("""
            INSERT INTO inter_agent_messages (from_pid, to_pid, payload_json, timestamp)
            VALUES (?, ?, ?, ?)
            """, (from_pid, to_pid, json.dumps(payload), time.time()))
            conn.commit()

    def read_agent_messages(self, to_pid: int) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute("""
            SELECT id, from_pid, payload_json, timestamp FROM inter_agent_messages
            WHERE to_pid = ? AND is_read = 0 ORDER BY id ASC
            """, (to_pid,))
            rows = cur.fetchall()
            ids = [r["id"] for r in rows]
            if ids:
                conn.execute(f"UPDATE inter_agent_messages SET is_read = 1 WHERE id IN ({','.join(map(str, ids))})")
                conn.commit()
            return [{"id": r["id"], "from_pid": r["from_pid"], "payload": json.loads(r["payload_json"]), "timestamp": r["timestamp"]} for r in rows]
