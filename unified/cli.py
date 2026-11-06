#!/usr/bin/env python3
"""
AI-OS Master Command-Line Interface (aios)
The single unified command line controlling:
- Live Semantic Filesystem (`aios fs`) -> Turns folders into live semantic queries & agent dropboxes
- Self-Healing Command Supervisor (`aios heal`) -> Wraps any build/script & diagnoses crashes in milliseconds
- Process Supervisor (`ps`, `spawn`, `pause`, `resume`, `kill`, `logs`, `pipe`)
- Kernel Telemetry & Ambient Context (`status`, `context`)
- Associative Semantic Memory (`memory search`, `memory insert`)
- Security Audit & DLP Log (`audit`)
- Natural Language System Queries (`ask`)
"""

import sys
import os
import json
import time
import uuid
import argparse

UNIFIED_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(UNIFIED_DIR)
DATA_DIR = os.path.join(UNIFIED_DIR, "data")
IPC_DIR = os.path.join(DATA_DIR, "ipc")
REQ_DIR = os.path.join(IPC_DIR, "requests")
RESP_DIR = os.path.join(IPC_DIR, "responses")
PID_FILE = os.path.join(DATA_DIR, "kernel.pid")

os.makedirs(REQ_DIR, exist_ok=True)
os.makedirs(RESP_DIR, exist_ok=True)

def send_kernel_request(req: dict) -> dict:
    if not os.path.exists(PID_FILE):
        print("[!] aiosd kernel daemon is not running.")
        print("    Starting background kernel daemon automatically...")
        import subprocess
        subprocess.Popen([sys.executable, os.path.join(UNIFIED_DIR, "kernel.py")])
        time.sleep(1.0)

    req_id = uuid.uuid4().hex[:8]
    req["req_id"] = req_id
    req_path = os.path.join(REQ_DIR, f"req_{req_id}.json")
    resp_path = os.path.join(RESP_DIR, f"resp_{req_id}.json")

    with open(req_path, "w") as f:
        json.dump(req, f)

    start = time.perf_counter()
    timeout = 8.0
    while (time.perf_counter() - start) < timeout:
        if os.path.exists(resp_path):
            try:
                with open(resp_path, "r") as f:
                    resp = json.load(f)
                os.remove(resp_path)
                return resp
            except Exception:
                time.sleep(0.005)
        time.sleep(0.005)

    if os.path.exists(req_path):
        os.remove(req_path)
    print(f"[!] Kernel IPC timed out after {timeout}s.")
    sys.exit(1)

def cmd_status(args):
    res = send_kernel_request({"command": "status"})
    print("\n================ AI-OS MASTER KERNEL TELEMETRY ================")
    print(f"  Daemon State            : ONLINE (aiosd v1.0.0-production)")
    print(f"  Uptime                  : {res['uptime_seconds']} seconds")
    print(f"  Active Agent Processes  : {res['active_processes']} running (total: {res['total_processes']})")
    print(f"  Total Token Consumption : {res['total_tokens_consumed']} tokens")
    print(f"  Semantic Memory Graph   : {res['memory_entities']} indexed entities (SQLite WAL)")
    print("\n-- Live Ambient Perception Context --")
    for k, v in res["perception"].items():
        print(f"  {k:24}: {v}")
    print("===============================================================\n")

def cmd_ps(args):
    res = send_kernel_request({"command": "ps"})
    procs = res.get("processes", [])
    print("\n" + "=" * 98)
    print(f"{'PID':<6} {'NAME':<18} {'STATUS':<12} {'STEP':<8} {'TOKENS':<14} {'ELAPSED':<9} {'GOAL'}")
    print("-" * 98)
    if not procs:
        print("  (No active or queued agent processes)")
    for p in procs:
        status = p["status"]
        if status == "RUNNING":
            status_disp = f"\033[92m{status}\033[0m"
        elif status == "COMPLETED":
            status_disp = f"\033[94m{status}\033[0m"
        elif status in ["FAILED", "KILLED"]:
            status_disp = f"\033[91m{status}\033[0m"
        elif status == "PAUSED":
            status_disp = f"\033[93m{status}\033[0m"
        else:
            status_disp = status

        elapsed = p.get("elapsed_sec", round(time.time() - p.get("created_at", time.time()), 1))
        step_str = p.get("step", f"{p.get('current_step', 0)}/{p.get('total_steps', 3)}")
        tokens_str = p.get("tokens", f"{p.get('tokens_used', 0)}/{p.get('max_tokens', 0)}")
        print(f"{p['pid']:<6} {p['name']:<18} {status_disp:<21} {step_str:<8} {tokens_str:<14} {elapsed:<8}s {p['goal'][:28]}")
    print("=" * 98 + "\n")

def cmd_spawn(args):
    req = {
        "command": "spawn",
        "name": args.name,
        "goal": args.goal,
        "max_tokens": args.budget
    }
    if args.attack:
        req["scopes"] = ["tool:memory_recall"]
    res = send_kernel_request(req)
    if res.get("status") == "error":
        print(f"\n\033[91m[!] SECURITY GATE REJECTED: {res['message']}\033[0m\n")
        return
    print(f"\n[+] {res['message']}")
    print(f"    Assigned PID   : {res['pid']}")
    print(f"    Token Budget   : {args.budget} tokens")
    print(f"    Monitor with   : ./aios logs {res['pid']}\n")

def cmd_logs(args):
    res = send_kernel_request({"command": "logs", "pid": int(args.pid)})
    if res.get("status") == "error":
        print(f"[!] {res['message']}")
        return
    print(f"\n========== EXECUTION & SECURITY AUDIT FOR PID {args.pid} ==========")
    for line in res.get("logs", []):
        print(f"  {line}")
    print("=" * 64 + "\n")

def cmd_pause(args):
    res = send_kernel_request({"command": "pause", "pid": int(args.pid)})
    print(f"[*] {res['message']}")

def cmd_resume(args):
    res = send_kernel_request({"command": "resume", "pid": int(args.pid)})
    print(f"[*] {res['message']}")

def cmd_kill(args):
    res = send_kernel_request({"command": "kill", "pid": int(args.pid)})
    print(f"[*] {res['message']}")

def cmd_pipe(args):
    res = send_kernel_request({"command": "pipe", "from_pid": int(args.from_pid), "to_pid": int(args.to_pid)})
    print(f"[+] {res['message']}")

def cmd_context(args):
    res = send_kernel_request({"command": "context"})
    print("\n======== AMBIENT PERCEPTION CONTEXT ========")
    for k, v in res["context"].items():
        print(f"  {k:24}: {v}")
    print("============================================\n")

def cmd_memory(args):
    if args.action == "search":
        res = send_kernel_request({"command": "memory_search", "query": args.text})
        print(f"\n===== ASSOCIATIVE MEMORY MATCHES FOR: '{args.text}' =====")
        matches = res.get("matches", [])
        if not matches:
            print("  (No semantic matches found in associative graph)")
        for m in matches:
            sim = m.get("similarity", 0.0)
            mid = m.get("id", "-")
            src = m.get("source", "system")
            print(f"  * [Sim: {sim:.3f}] (ID: {mid}) [Source: {src}]")
            print(f"    {m.get('content', '')}\n")
    elif args.action == "insert":
        res = send_kernel_request({"command": "memory_insert", "content": args.text})
        print(f"[+] Inserted into memory graph: {res.get('id', 'ok')}")

def cmd_audit(args):
    res = send_kernel_request({"command": "audit"})
    audits = res.get("audits", [])
    print("\n" + "=" * 92)
    print(f"{'TIME':<10} {'PID':<6} {'EVENT':<18} {'TARGET':<18} {'DECISION':<10} {'REASON'}")
    print("-" * 92)
    for a in audits:
        tstr = time.strftime('%H:%M:%S', time.localtime(a['timestamp']))
        dec = f"\033[92m{a['decision']}\033[0m" if a['decision'] == "ALLOWED" else f"\033[91m{a['decision']}\033[0m"
        print(f"{tstr:<10} {str(a.get('pid', '-')):<6} {a['event_type']:<18} {a['target']:<18} {dec:<19} {a['reason'][:28]}")
    print("=" * 92 + "\n")

def cmd_ask(args):
    res = send_kernel_request({"command": "ask", "query": args.query})
    print("\n" + res["answer"] + "\n")

def cmd_fs(args):
    from semantic_fs import LiveSemanticEngine
    engine = LiveSemanticEngine(root_dir=BASE_DIR)
    if args.query:
        q_folder = os.path.join(engine.mount_dir, f"@query: {args.query}")
        os.makedirs(q_folder, exist_ok=True)
        print(f"[+] Created magic semantic query folder: SemanticFS/@query: {args.query}")
    engine.step()
    print(f"[+] SemanticFS synchronized ({len(engine.file_index)} workspace files indexed) at {engine.mount_dir}")
    print("    Open 'SemanticFS' in Finder or run: ls -la SemanticFS/")
    if args.watch:
        engine.run_daemon()

def cmd_heal(args):
    from healer import SelfHealingRunner
    runner = SelfHealingRunner(workspace_dir=BASE_DIR)
    cmd_list = args.cmd
    if cmd_list and cmd_list[0] == "--":
        cmd_list = cmd_list[1:]
    if not cmd_list:
        print("[!] Provide a command to supervise, e.g.: ./aios heal -- python3 script.py")
        sys.exit(1)
    rc = runner.run_and_heal(cmd_list, auto_fix=args.fix)
    sys.exit(rc)

def cmd_restart(args):
    import signal
    import subprocess
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE) as f:
                pid = int(f.read().strip())
            os.kill(pid, signal.SIGTERM)
            print(f"[*] Stopped previous aiosd daemon (PID {pid})")
        except Exception as e:
            print(f"[*] Note: {e}")
        try:
            os.remove(PID_FILE)
        except Exception:
            pass
    time.sleep(0.5)
    subprocess.Popen([sys.executable, os.path.join(UNIFIED_DIR, "kernel.py")])
    time.sleep(1.0)
    print("[+] AI-OS master kernel daemon (aiosd) restarted fresh.")

def cmd_control(args):
    import subprocess
    server_script = os.path.join(BASE_DIR, "mission_control", "server.py")
    subprocess.run([sys.executable, server_script])

def main():
    parser = argparse.ArgumentParser(description="AI-OS Unified Command-Line Interface (aios)")
    sub = parser.add_subparsers(dest="subcommand", help="Available aios commands")

    # 0. Killer Feature: Visual AI Mission Control + Time-Machine UI
    sub.add_parser("control", help="Launch the visual AIOS Mission Control Dashboard & Time-Machine UI").set_defaults(func=cmd_control)

    # 1. Killer Feature: SemanticFS
    p_fs = sub.add_parser("fs", help="Sync or watch the Live Semantic Filesystem (SemanticFS/)")
    p_fs.add_argument("--query", "-q", help="Create a new '@query: ...' magic folder and populate it immediately")
    p_fs.add_argument("--watch", "-w", action="store_true", help="Run continuous real-time watcher daemon")
    p_fs.set_defaults(func=cmd_fs)

    # 2. Killer Feature: Self-Healing Process Supervisor
    p_heal = sub.add_parser("heal", help="Run any command under the AI-OS Self-Healing Crash Interceptor")
    p_heal.add_argument("--fix", action="store_true", help="Automatically apply surgical fixes on crash")
    p_heal.add_argument("cmd", nargs=argparse.REMAINDER, help="Command to run (e.g., -- cargo build)")
    p_heal.set_defaults(func=cmd_heal)

    sub.add_parser("status", help="Inspect kernel health and telemetry").set_defaults(func=cmd_status)
    sub.add_parser("ps", help="List active agent processes").set_defaults(func=cmd_ps)
    sub.add_parser("restart", help="Restart the aiosd master kernel daemon").set_defaults(func=cmd_restart)

    p_sp = sub.add_parser("spawn", help="Spawn an autonomous agent process")
    p_sp.add_argument("--name", required=True, help="Agent name")
    p_sp.add_argument("--goal", required=True, help="Task objective")
    p_sp.add_argument("--budget", type=int, default=5000, help="Token budget quota")
    p_sp.add_argument("--attack", action="store_true", help="Omit required capability token to test security block")
    p_sp.set_defaults(func=cmd_spawn)

    p_log = sub.add_parser("logs", help="View logs and audit events for a process")
    p_log.add_argument("pid", help="Process ID")
    p_log.set_defaults(func=cmd_logs)

    p_p = sub.add_parser("pause", help="Suspend an agent process")
    p_p.add_argument("pid", help="PID")
    p_p.set_defaults(func=cmd_pause)

    p_r = sub.add_parser("resume", help="Resume a paused agent process")
    p_r.add_argument("pid", help="PID")
    p_r.set_defaults(func=cmd_resume)

    p_k = sub.add_parser("kill", help="Terminate an agent process (SIGKILL)")
    p_k.add_argument("pid", help="PID")
    p_k.set_defaults(func=cmd_kill)

    p_pipe = sub.add_parser("pipe", help="Pipe output from one agent to another")
    p_pipe.add_argument("from_pid", help="Source PID")
    p_pipe.add_argument("to_pid", help="Target PID")
    p_pipe.set_defaults(func=cmd_pipe)

    sub.add_parser("context", help="Inspect live ambient workspace perception").set_defaults(func=cmd_context)

    p_mem = sub.add_parser("memory", help="Query or add to the semantic knowledge graph")
    p_mem.add_argument("action", choices=["search", "insert"], help="Action")
    p_mem.add_argument("text", help="Query string or text content to insert")
    p_mem.set_defaults(func=cmd_memory)

    sub.add_parser("audit", help="Inspect kernel security audit log").set_defaults(func=cmd_audit)

    p_ask = sub.add_parser("ask", help="Ask a question grounded in ambient context and memory")
    p_ask.add_argument("query", help="Question")
    p_ask.set_defaults(func=cmd_ask)

    args = parser.parse_args()
    if not args.subcommand:
        parser.print_help()
        sys.exit(0)
    args.func(args)

if __name__ == "__main__":
    main()
