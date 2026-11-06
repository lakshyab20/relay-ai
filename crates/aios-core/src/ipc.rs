use crate::process::ProcessStatus;
use crate::scheduler::Scheduler;
use crate::token::ActionScope;
use serde::{Deserialize, Serialize};
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::Arc;
use tokio::time::{sleep, Duration};
use tracing::info;

#[derive(Debug, Serialize, Deserialize)]
pub struct IpcRequest {
    pub req_id: Option<String>,
    pub command: String,
    pub name: Option<String>,
    pub goal: Option<String>,
    pub max_tokens: Option<usize>,
    pub pid: Option<u32>,
    pub query: Option<String>,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct IpcResponse {
    pub status: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub message: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub pid: Option<u32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub answer: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub processes: Option<Vec<crate::process::ProcessState>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub logs: Option<Vec<String>>,
}

pub struct IpcEngine {
    scheduler: Arc<Scheduler>,
    req_dir: PathBuf,
    resp_dir: PathBuf,
}

impl IpcEngine {
    pub fn new<P: AsRef<Path>>(scheduler: Arc<Scheduler>, data_dir: P) -> Self {
        let req_dir = data_dir.as_ref().join("ipc").join("requests");
        let resp_dir = data_dir.as_ref().join("ipc").join("responses");
        let _ = fs::create_dir_all(&req_dir);
        let _ = fs::create_dir_all(&resp_dir);

        Self {
            scheduler,
            req_dir,
            resp_dir,
        }
    }

    pub async fn run_loop(&self) {
        info!("Rust aiosd IPC Queue Engine active at {:?}", self.req_dir);

        loop {
            if let Ok(entries) = fs::read_dir(&self.req_dir) {
                for entry in entries.flatten() {
                    let path = entry.path();
                    if path.is_file() && path.extension().and_then(|s| s.to_str()) == Some("json") {
                        if let Ok(content) = fs::read_to_string(&path) {
                            if let Ok(req) = serde_json::from_str::<IpcRequest>(&content) {
                                let resp = self.handle_request(req).await;
                                let req_id = path
                                    .file_stem()
                                    .unwrap()
                                    .to_str()
                                    .unwrap()
                                    .replace("req_", "");
                                let resp_path = self.resp_dir.join(format!("resp_{}.json", req_id));

                                if let Ok(resp_json) = serde_json::to_string(&resp) {
                                    let _ = fs::write(&resp_path, resp_json);
                                }
                                let _ = fs::remove_file(&path);
                            }
                        }
                    }
                }
            }
            sleep(Duration::from_millis(15)).await;
        }
    }

    async fn handle_request(&self, req: IpcRequest) -> IpcResponse {
        match req.command.as_str() {
            "status" => {
                let procs = self.scheduler.process_table().list().await;
                let active = procs
                    .iter()
                    .filter(|p| p.status == ProcessStatus::Running)
                    .count();
                IpcResponse {
                    status: "ok".into(),
                    message: Some(format!("Rust aiosd active: {} processes running", active)),
                    pid: None,
                    answer: None,
                    processes: Some(procs),
                    logs: None,
                }
            }
            "ps" => {
                let procs = self.scheduler.process_table().list().await;
                IpcResponse {
                    status: "ok".into(),
                    message: None,
                    pid: None,
                    answer: None,
                    processes: Some(procs),
                    logs: None,
                }
            }
            "spawn" => {
                let name = req.name.unwrap_or_else(|| "agent".into());
                let goal = req.goal.unwrap_or_else(|| "General task".into());
                let max_tokens = req.max_tokens.unwrap_or(4000);
                let scopes = vec![
                    ActionScope::MemoryRead {
                        namespace: "*".into(),
                    },
                    ActionScope::ToolExecute {
                        tool_name: "sys_info".into(),
                    },
                    ActionScope::MemoryWrite {
                        namespace: "*".into(),
                    },
                ];

                match self
                    .scheduler
                    .spawn_agent(name.clone(), goal, max_tokens, scopes)
                    .await
                {
                    Ok(pid) => IpcResponse {
                        status: "ok".into(),
                        message: Some(format!(
                            "Agent '{}' spawned successfully with PID {}",
                            name, pid
                        )),
                        pid: Some(pid),
                        answer: None,
                        processes: None,
                        logs: None,
                    },
                    Err(e) => IpcResponse {
                        status: "error".into(),
                        message: Some(e),
                        pid: None,
                        answer: None,
                        processes: None,
                        logs: None,
                    },
                }
            }
            "logs" => {
                let pid = req.pid.unwrap_or(0);
                match self.scheduler.storage().get_logs(pid) {
                    Ok(logs) => IpcResponse {
                        status: "ok".into(),
                        message: None,
                        pid: Some(pid),
                        answer: None,
                        processes: None,
                        logs: Some(logs),
                    },
                    Err(e) => IpcResponse {
                        status: "error".into(),
                        message: Some(format!("Logs query failed: {:?}", e)),
                        pid: Some(pid),
                        answer: None,
                        processes: None,
                        logs: None,
                    },
                }
            }
            "ask" => {
                let q = req.query.unwrap_or_default();
                let ans = format!(
                    "[Rust AI-OS Master Kernel Answer]\nQuery: '{}'\nPlatform: macOS Darwin (Apple Silicon Metal / Tokio)\nStatus: Deterministically executed via native compiled Rust.",
                    q
                );
                IpcResponse {
                    status: "ok".into(),
                    message: None,
                    pid: None,
                    answer: Some(ans),
                    processes: None,
                    logs: None,
                }
            }
            _ => IpcResponse {
                status: "error".into(),
                message: Some(format!("Unknown command: '{}'", req.command)),
                pid: None,
                answer: None,
                processes: None,
                logs: None,
            },
        }
    }
}
