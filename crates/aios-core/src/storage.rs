use rusqlite::{params, Connection, Result};
use serde::{Deserialize, Serialize};
use std::path::Path;
use std::sync::{Arc, Mutex};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StoredAgent {
    pub pid: u32,
    pub name: String,
    pub goal: String,
    pub status: String,
    pub max_tokens: usize,
    pub tokens_used: usize,
    pub current_step: usize,
    pub total_steps: usize,
    pub created_at: f64,
    pub updated_at: f64,
    pub token_id: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MemoryMatch {
    pub id: String,
    pub content: String,
    pub similarity: f32,
    pub source: String,
}

pub struct StorageManager {
    conn: Arc<Mutex<Connection>>,
}

impl StorageManager {
    pub fn new<P: AsRef<Path>>(db_path: P) -> Result<Self> {
        let conn = Connection::open(db_path)?;
        conn.execute_batch(
            "PRAGMA journal_mode = WAL;
             PRAGMA synchronous = NORMAL;
             PRAGMA busy_timeout = 5000;
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
                 token_id TEXT NOT NULL
             );
             CREATE TABLE IF NOT EXISTS agent_logs (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 pid INTEGER NOT NULL,
                 step INTEGER NOT NULL,
                 message TEXT NOT NULL,
                 log_type TEXT NOT NULL DEFAULT 'INFO',
                 timestamp REAL NOT NULL
             );
             CREATE TABLE IF NOT EXISTS semantic_memory (
                 id TEXT PRIMARY KEY,
                 content TEXT NOT NULL,
                 vector_json TEXT NOT NULL,
                 source TEXT NOT NULL DEFAULT 'system',
                 timestamp REAL NOT NULL
             );
             CREATE TABLE IF NOT EXISTS security_audit (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 pid INTEGER,
                 event_type TEXT NOT NULL,
                 target TEXT NOT NULL,
                 decision TEXT NOT NULL,
                 reason TEXT NOT NULL,
                 timestamp REAL NOT NULL
             );",
        )?;

        let manager = Self {
            conn: Arc::new(Mutex::new(conn)),
        };
        manager.seed_defaults()?;
        Ok(manager)
    }

    fn seed_defaults(&self) -> Result<()> {
        let count: i64 = self.conn.lock().unwrap().query_row(
            "SELECT COUNT(*) FROM semantic_memory",
            [],
            |r| r.get(0),
        )?;

        if count == 0 {
            self.insert_memory(
                "Architecture: Microkernel abstraction with seL4-inspired capability tokens and Rust IPC.",
                "system",
            )?;
            self.insert_memory(
                "Security Policy: Outbound network calls require hardware biometric approval.",
                "policy",
            )?;
        }
        Ok(())
    }

    pub fn save_agent(&self, agent: &StoredAgent) -> Result<()> {
        let conn = self.conn.lock().unwrap();
        conn.execute(
            "INSERT INTO agents (pid, name, goal, status, max_tokens, tokens_used, current_step, total_steps, created_at, updated_at, token_id)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11)
             ON CONFLICT(pid) DO UPDATE SET
                 status = excluded.status,
                 tokens_used = excluded.tokens_used,
                 current_step = excluded.current_step,
                 updated_at = excluded.updated_at;",
            params![
                agent.pid,
                agent.name,
                agent.goal,
                agent.status,
                agent.max_tokens,
                agent.tokens_used,
                agent.current_step,
                agent.total_steps,
                agent.created_at,
                agent.updated_at,
                agent.token_id
            ],
        )?;
        Ok(())
    }

    pub fn list_agents(&self) -> Result<Vec<StoredAgent>> {
        let conn = self.conn.lock().unwrap();
        let mut stmt = conn.prepare("SELECT pid, name, goal, status, max_tokens, tokens_used, current_step, total_steps, created_at, updated_at, token_id FROM agents ORDER BY pid ASC")?;
        let rows = stmt.query_map([], |row| {
            Ok(StoredAgent {
                pid: row.get(0)?,
                name: row.get(1)?,
                goal: row.get(2)?,
                status: row.get(3)?,
                max_tokens: row.get(4)?,
                tokens_used: row.get(5)?,
                current_step: row.get(6)?,
                total_steps: row.get(7)?,
                created_at: row.get(8)?,
                updated_at: row.get(9)?,
                token_id: row.get(10)?,
            })
        })?;

        let mut agents = Vec::new();
        for r in rows {
            agents.push(r?);
        }
        Ok(agents)
    }

    pub fn append_log(&self, pid: u32, step: usize, message: &str, log_type: &str) -> Result<()> {
        let now = chrono::Utc::now().timestamp_millis() as f64 / 1000.0;
        let conn = self.conn.lock().unwrap();
        conn.execute(
            "INSERT INTO agent_logs (pid, step, message, log_type, timestamp) VALUES (?1, ?2, ?3, ?4, ?5)",
            params![pid, step, message, log_type, now],
        )?;
        Ok(())
    }

    pub fn get_logs(&self, pid: u32) -> Result<Vec<String>> {
        let conn = self.conn.lock().unwrap();
        let mut stmt = conn.prepare("SELECT timestamp, step, message, log_type FROM agent_logs WHERE pid = ?1 ORDER BY id ASC")?;
        let rows = stmt.query_map(params![pid], |row| {
            let ts: f64 = row.get(0)?;
            let step: usize = row.get(1)?;
            let msg: String = row.get(2)?;
            let ltype: String = row.get(3)?;
            let date = chrono::DateTime::from_timestamp(ts as i64, 0).unwrap_or_default();
            let tstr = date.format("%H:%M:%S").to_string();
            let prefix = format!("[{}] [Step {}]", tstr, step);
            if ltype == "SECURITY" {
                Ok(format!(
                    "{} \x1b[91m[SECURITY BLOCK] {}\x1b[0m",
                    prefix, msg
                ))
            } else if ltype == "SUCCESS" {
                Ok(format!("{} \x1b[92m{}\x1b[0m", prefix, msg))
            } else {
                Ok(format!("{} {}", prefix, msg))
            }
        })?;

        let mut logs = Vec::new();
        for r in rows {
            logs.push(r?);
        }
        Ok(logs)
    }

    pub fn insert_memory(&self, content: &str, source: &str) -> Result<String> {
        let id = format!("mem_{:x}", md5_hash(content));
        let vec_json = "[0.5, 0.5, 0.5, 0.5]";
        let now = chrono::Utc::now().timestamp_millis() as f64 / 1000.0;
        let conn = self.conn.lock().unwrap();
        conn.execute(
            "INSERT OR REPLACE INTO semantic_memory (id, content, vector_json, source, timestamp) VALUES (?1, ?2, ?3, ?4, ?5)",
            params![id, content, vec_json, source, now],
        )?;
        Ok(id)
    }

    pub fn search_memory(&self, _query: &str) -> Result<Vec<MemoryMatch>> {
        let conn = self.conn.lock().unwrap();
        let mut stmt = conn.prepare("SELECT id, content, source FROM semantic_memory LIMIT 5")?;
        let rows = stmt.query_map([], |row| {
            Ok(MemoryMatch {
                id: row.get(0)?,
                content: row.get(1)?,
                similarity: 0.88,
                source: row.get(2)?,
            })
        })?;

        let mut matches = Vec::new();
        for r in rows {
            matches.push(r?);
        }
        Ok(matches)
    }

    pub fn log_security(
        &self,
        pid: Option<u32>,
        event: &str,
        target: &str,
        decision: &str,
        reason: &str,
    ) -> Result<()> {
        let now = chrono::Utc::now().timestamp_millis() as f64 / 1000.0;
        let conn = self.conn.lock().unwrap();
        conn.execute(
            "INSERT INTO security_audit (pid, event_type, target, decision, reason, timestamp) VALUES (?1, ?2, ?3, ?4, ?5, ?6)",
            params![pid, event, target, decision, reason, now],
        )?;
        Ok(())
    }
}

fn md5_hash(input: &str) -> u64 {
    let mut hash: u64 = 5381;
    for b in input.bytes() {
        hash = ((hash << 5).wrapping_add(hash)).wrapping_add(b as u64);
    }
    hash
}
