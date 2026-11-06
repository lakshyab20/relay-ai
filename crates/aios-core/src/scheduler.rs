use crate::process::{ProcessStatus, ProcessTable};
use crate::security::{DLPScanner, PromptInjectionGuard};
use crate::storage::StorageManager;
use crate::token::{ActionScope, CapabilityEngine};
use aios_sandbox::SandboxedActuator;
use std::path::PathBuf;
use std::sync::Arc;
use tokio::time::{sleep, Duration};
use tracing::{info, warn};

pub struct Scheduler {
    process_table: Arc<ProcessTable>,
    storage: Arc<StorageManager>,
    cap_engine: Arc<CapabilityEngine>,
    actuator: Arc<SandboxedActuator>,
}

impl Scheduler {
    pub fn new(
        secret_key: &[u8],
        db_path: PathBuf,
        workspace_dir: PathBuf,
    ) -> anyhow::Result<Self> {
        let storage = Arc::new(StorageManager::new(db_path)?);
        let cap_engine = Arc::new(CapabilityEngine::new(secret_key));
        let process_table = Arc::new(ProcessTable::new());
        let actuator = Arc::new(SandboxedActuator::new(workspace_dir));

        Ok(Self {
            process_table,
            storage,
            cap_engine,
            actuator,
        })
    }

    pub fn storage(&self) -> &StorageManager {
        &self.storage
    }

    pub fn process_table(&self) -> &ProcessTable {
        &self.process_table
    }

    pub async fn spawn_agent(
        &self,
        name: String,
        goal: String,
        max_tokens: usize,
        scopes: Vec<ActionScope>,
    ) -> Result<u32, String> {
        // 1. Prompt Injection Inspection
        PromptInjectionGuard::inspect(&goal)?;

        // 2. Issue Capability Token
        let token =
            self.cap_engine
                .issue_token(&format!("agent-{}", name), scopes, 3600, max_tokens);

        let pid = self
            .process_table
            .spawn(name.clone(), goal.clone(), max_tokens, token.id.to_string())
            .await;

        let process_table = Arc::clone(&self.process_table);
        let storage = Arc::clone(&self.storage);
        let cap_engine = Arc::clone(&self.cap_engine);
        let actuator = Arc::clone(&self.actuator);
        let token_clone = token.clone();

        // 3. Spawn asynchronous autonomous agent task under Tokio supervisor
        tokio::spawn(async move {
            info!("Agent PID {} ({}) running under Tokio scheduler", pid, name);
            let _ = storage.append_log(
                pid,
                0,
                &format!(
                    "Spawned under Cognitive Supervisor. Token: {}",
                    token_clone.id
                ),
                "INFO",
            );

            let steps = [
                (
                    "Context Recall",
                    "tool:memory_recall",
                    ActionScope::MemoryRead {
                        namespace: "*".into(),
                    },
                ),
                (
                    "Tool Execution",
                    "tool:sys_info",
                    ActionScope::ToolExecute {
                        tool_name: "sys_info".into(),
                    },
                ),
                (
                    "Synthesis",
                    "memory:write",
                    ActionScope::MemoryWrite {
                        namespace: "*".into(),
                    },
                ),
            ];

            for (step_idx, (step_name, tool_name, req_scope)) in steps.iter().enumerate() {
                let current_step = step_idx + 1;

                // Capability Check
                match cap_engine.verify_token(&token_clone, req_scope) {
                    Ok(_) => {
                        let _ = storage.append_log(
                            pid,
                            current_step,
                            &format!("Capability verified for {}", tool_name),
                            "INFO",
                        );
                    }
                    Err(e) => {
                        warn!("Security violation for PID {}: {:?}", pid, e);
                        let _ = storage.append_log(
                            pid,
                            current_step,
                            &format!("SECURITY VIOLATION BLOCKED: {:?}", e),
                            "SECURITY",
                        );
                        let _ = storage.log_security(
                            Some(pid),
                            "CAPABILITY_GATE",
                            tool_name,
                            "BLOCKED",
                            &format!("{:?}", e),
                        );
                        process_table.set_status(pid, ProcessStatus::Failed).await;
                        return;
                    }
                }

                // Execute sandboxed tool if applicable
                if *tool_name == "tool:sys_info" {
                    match actuator.execute("sys_info", "") {
                        Ok(res) => {
                            let (clean_res, _) = DLPScanner::sanitize(&res);
                            let _ = storage.append_log(
                                pid,
                                current_step,
                                &format!("Tool output: {}", clean_res),
                                "SUCCESS",
                            );
                        }
                        Err(err) => {
                            let _ = storage.append_log(
                                pid,
                                current_step,
                                &format!("Tool error: {:?}", err),
                                "INFO",
                            );
                        }
                    }
                }

                // Simulate token burn & check budget
                sleep(Duration::from_millis(600)).await;
                let step_tokens = 140;
                if let Err(e) = process_table.update_tokens(pid, step_tokens).await {
                    let _ = storage.append_log(pid, current_step, &e, "SECURITY");
                    return;
                }

                let _ = storage.append_log(
                    pid,
                    current_step,
                    &format!("Completed {}. Consumed {} tokens.", step_name, step_tokens),
                    "INFO",
                );
            }

            process_table
                .set_status(pid, ProcessStatus::Completed)
                .await;
            let _ = storage.append_log(
                pid,
                3,
                "Goal successfully achieved. Process exited cleanly.",
                "SUCCESS",
            );
            let _ = storage.insert_memory(
                &format!(
                    "Outcome of agent PID {} ({}): Completed successfully.",
                    pid, name
                ),
                &format!("agent-{}", pid),
            );
        });

        Ok(pid)
    }
}
