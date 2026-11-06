use clap::{Parser, Subcommand};
use serde::{Deserialize, Serialize};
use std::fs;
use std::time::{Duration, Instant};

#[derive(Parser)]
#[command(
    name = "aios",
    version = "1.0.0",
    about = "AI-OS Native Command-Line Interface"
)]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    /// Inspect kernel health and telemetry
    Status,
    /// List active agent processes
    Ps,
    /// Spawn an autonomous agent process
    Spawn {
        #[arg(short, long)]
        name: String,
        #[arg(short, long)]
        goal: String,
        #[arg(short, long, default_value_t = 4000)]
        budget: usize,
    },
    /// View logs for a process
    Logs { pid: u32 },
    /// Ask a question grounded in ambient context and memory
    Ask { query: String },
}

#[derive(Serialize, Deserialize)]
struct IpcRequest {
    req_id: Option<String>,
    command: String,
    name: Option<String>,
    goal: Option<String>,
    max_tokens: Option<usize>,
    pid: Option<u32>,
    query: Option<String>,
}

#[derive(Serialize, Deserialize)]
struct IpcResponse {
    status: String,
    message: Option<String>,
    pid: Option<u32>,
    answer: Option<String>,
    processes: Option<Vec<aios_core::ProcessState>>,
    logs: Option<Vec<String>>,
}

fn send_request(req: IpcRequest) -> anyhow::Result<IpcResponse> {
    let base_dir = std::env::current_dir()?;
    let ipc_dir = base_dir.join("unified").join("data").join("ipc");
    let req_dir = ipc_dir.join("requests");
    let resp_dir = ipc_dir.join("responses");

    let _ = fs::create_dir_all(&req_dir);
    let _ = fs::create_dir_all(&resp_dir);

    let req_id = uuid::Uuid::new_v4().to_string();
    let req_path = req_dir.join(format!("req_{}.json", req_id));
    let resp_path = resp_dir.join(format!("resp_{}.json", req_id));

    let json = serde_json::to_string(&req)?;
    fs::write(&req_path, json)?;

    let start = Instant::now();
    let timeout = Duration::from_secs(6);

    while start.elapsed() < timeout {
        if resp_path.exists() {
            if let Ok(content) = fs::read_to_string(&resp_path) {
                let _ = fs::remove_file(&resp_path);
                if let Ok(resp) = serde_json::from_str::<IpcResponse>(&content) {
                    return Ok(resp);
                }
            }
        }
        std::thread::sleep(Duration::from_millis(10));
    }

    let _ = fs::remove_file(&req_path);
    anyhow::bail!("Kernel daemon response timed out. Ensure 'cargo run --bin aiosd' is running.")
}

fn main() -> anyhow::Result<()> {
    let cli = Cli::parse();

    match cli.command {
        Commands::Status => {
            let resp = send_request(IpcRequest {
                req_id: None,
                command: "status".into(),
                name: None,
                goal: None,
                max_tokens: None,
                pid: None,
                query: None,
            })?;
            println!("\n================ RUST AI-OS KERNEL TELEMETRY ================");
            println!("  Daemon State : ONLINE (Rust aiosd v1.0.0)");
            if let Some(msg) = resp.message {
                println!("  Summary      : {}", msg);
            }
            println!("===============================================================\n");
        }
        Commands::Ps => {
            let resp = send_request(IpcRequest {
                req_id: None,
                command: "ps".into(),
                name: None,
                goal: None,
                max_tokens: None,
                pid: None,
                query: None,
            })?;
            println!("\n============================================================================================");
            println!(
                "{:<6} {:<18} {:<12} {:<8} {:<14} {:<8} GOAL",
                "PID", "NAME", "STATUS", "STEP", "TOKENS", "ELAPSED"
            );
            println!("--------------------------------------------------------------------------------------------");
            if let Some(procs) = resp.processes {
                for p in procs {
                    let step = format!("{}/{}", p.current_step, p.total_steps);
                    let tokens = format!("{}/{}", p.tokens_used, p.max_tokens);
                    println!(
                        "{:<6} {:<18} {:<12?} {:<8} {:<14} {:<8} {}",
                        p.pid, p.name, p.status, step, tokens, "active", p.goal
                    );
                }
            }
            println!("============================================================================================\n");
        }
        Commands::Spawn { name, goal, budget } => {
            let resp = send_request(IpcRequest {
                req_id: None,
                command: "spawn".into(),
                name: Some(name),
                goal: Some(goal),
                max_tokens: Some(budget),
                pid: None,
                query: None,
            })?;
            if let Some(msg) = resp.message {
                println!("[+] {}", msg);
            }
        }
        Commands::Logs { pid } => {
            let resp = send_request(IpcRequest {
                req_id: None,
                command: "logs".into(),
                name: None,
                goal: None,
                max_tokens: None,
                pid: Some(pid),
                query: None,
            })?;
            println!("\n========== EXECUTION LOG FOR PID {} ==========", pid);
            if let Some(logs) = resp.logs {
                for l in logs {
                    println!("  {}", l);
                }
            }
            println!("====================================================\n");
        }
        Commands::Ask { query } => {
            let resp = send_request(IpcRequest {
                req_id: None,
                command: "ask".into(),
                name: None,
                goal: None,
                max_tokens: None,
                pid: None,
                query: Some(query),
            })?;
            if let Some(ans) = resp.answer {
                println!("\n{}\n", ans);
            }
        }
    }

    Ok(())
}
