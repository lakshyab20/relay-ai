use aios_core::{IpcEngine, Scheduler};
use std::fs;
use std::sync::Arc;
use tracing_subscriber::{layer::SubscriberExt, util::SubscriberInitExt};

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    tracing_subscriber::registry()
        .with(tracing_subscriber::EnvFilter::new("info"))
        .with(tracing_subscriber::fmt::layer())
        .init();

    println!("==================================================================");
    println!("  AI-OS Native Kernel Daemon (aiosd) v1.0.0                      ");
    println!("  Native Rust / Tokio Async Multithreaded Cognitive Kernel        ");
    println!("==================================================================");

    let base_dir = std::env::current_dir()?;
    let data_dir = base_dir.join("unified").join("data");
    let db_path = data_dir.join("aios.db");
    let _ = fs::create_dir_all(&data_dir);

    // Write kernel PID file
    let pid_file = data_dir.join("kernel.pid");
    fs::write(&pid_file, std::process::id().to_string())?;

    let scheduler = Arc::new(Scheduler::new(
        b"aios_rust_kernel_ring0_entropy_2026",
        db_path,
        base_dir,
    )?);

    let ipc_engine = IpcEngine::new(scheduler, &data_dir);
    println!("[*] Kernel PID    : {}", std::process::id());
    println!("[*] Database      : SQLite WAL (rusqlite)");
    println!("[*] Scheduler     : Tokio Async Multithreaded Pool");
    println!("[*] Security Gate : Ring-0 HMAC-SHA256 Capability Tokens");

    // Run IPC event loop
    ipc_engine.run_loop().await;

    Ok(())
}
