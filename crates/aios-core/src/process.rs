use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use std::sync::atomic::{AtomicU32, Ordering};
use std::sync::Arc;
use tokio::sync::RwLock;

static PID_COUNTER: AtomicU32 = AtomicU32::new(1001);

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum ProcessStatus {
    Queued,
    Running,
    Suspended,
    Completed,
    Failed,
    Killed,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProcessState {
    pub pid: u32,
    pub name: String,
    pub goal: String,
    pub status: ProcessStatus,
    pub max_tokens: usize,
    pub tokens_used: usize,
    pub current_step: usize,
    pub total_steps: usize,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
    pub token_id: String,
}

pub struct ProcessTable {
    processes: Arc<RwLock<Vec<ProcessState>>>,
}

impl ProcessTable {
    pub fn new() -> Self {
        Self {
            processes: Arc::new(RwLock::new(Vec::new())),
        }
    }

    pub async fn spawn(
        &self,
        name: String,
        goal: String,
        max_tokens: usize,
        token_id: String,
    ) -> u32 {
        let pid = PID_COUNTER.fetch_add(1, Ordering::SeqCst);
        let now = Utc::now();
        let state = ProcessState {
            pid,
            name,
            goal,
            status: ProcessStatus::Running,
            max_tokens,
            tokens_used: 0,
            current_step: 0,
            total_steps: 3,
            created_at: now,
            updated_at: now,
            token_id,
        };

        let mut lock = self.processes.write().await;
        lock.push(state);
        pid
    }

    pub async fn update_tokens(&self, pid: u32, additional: usize) -> Result<usize, String> {
        let mut lock = self.processes.write().await;
        if let Some(proc) = lock.iter_mut().find(|p| p.pid == pid) {
            proc.tokens_used += additional;
            proc.updated_at = Utc::now();
            if proc.tokens_used > proc.max_tokens {
                proc.status = ProcessStatus::Failed;
                return Err(format!(
                    "ResourceQuotaExceeded: {} > {}",
                    proc.tokens_used, proc.max_tokens
                ));
            }
            Ok(proc.tokens_used)
        } else {
            Err(format!("PID {} not found", pid))
        }
    }

    pub async fn set_status(&self, pid: u32, status: ProcessStatus) {
        let mut lock = self.processes.write().await;
        if let Some(proc) = lock.iter_mut().find(|p| p.pid == pid) {
            proc.status = status;
            proc.updated_at = Utc::now();
        }
    }

    pub async fn list(&self) -> Vec<ProcessState> {
        let lock = self.processes.read().await;
        lock.clone()
    }
}
