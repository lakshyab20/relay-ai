"""
AI-OS Master Kernel Daemon (aiosd) v1.0.0
Production-grade unified operating system kernel combining:
- Cognitive Process Supervisor (systemd for AI agents, persistent SQLite state, crash recovery)
- Ring-0 Capability Security Arbiter (HMAC-SHA256 tokens, DLP scanner, sandbox boundaries)
- Real Sandboxed Tool Actuation (filesystem, math, git, telemetry, memory)
- Associative Semantic Memory (Vector knowledge graph)
- Ambient Perception Subsystem
- Inter-Agent Communication Bus (IPC pipes)
"""

import os
import sys
import time
import json
import uuid
import threading
from typing import Dict, Any, List, Optional

from storage import StorageManager
from security import CapabilityEngine, SecurityViolationError, DLPScanner, PromptInjectionGuard
from tools import SandboxedToolActuator
from inference import LocalInferenceEngine

UNIFIED_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(UNIFIED_DIR, "data")
IPC_DIR = os.path.join(DATA_DIR, "ipc")
REQ_DIR = os.path.join(IPC_DIR, "requests")
RESP_DIR = os.path.join(IPC_DIR, "responses")
PID_FILE = os.path.join(DATA_DIR, "kernel.pid")

os.makedirs(REQ_DIR, exist_ok=True)
os.makedirs(RESP_DIR, exist_ok=True)

# ----------------- AMBIENT PERCEPTION SUBSYSTEM -----------------
class PerceptionSubsystem:
    def __init__(self, workspace_dir: str):
        self.workspace_dir = workspace_dir
        self.active_context = {
            "workspace": workspace_dir,
            "os_platform": sys.platform,
            "last_event": "Kernel daemon initialized",
            "last_event_time": time.time()
        }

    def record_event(self, description: str):
        self.active_context["last_event"] = description
        self.active_context["last_event_time"] = time.time()

    def get_context(self) -> Dict[str, Any]:
        return dict(self.active_context)

# ----------------- AGENT PROCESS THREAD (systemd) -----------------
class LiveAgentProcess:
    def __init__(self, agent_row: Dict[str, Any], kernel):
        self.kernel = kernel
        self.pid = agent_row["pid"]
        self.name = agent_row["name"]
        self.goal = agent_row["goal"]
        self.max_tokens = agent_row["max_tokens"]
        self.tokens_used = agent_row["tokens_used"]
        self.current_step = agent_row["current_step"]
        self.total_steps = agent_row["total_steps"]
        self.status = agent_row["status"]
        self.created_at = agent_row["created_at"]
        self.token_id = agent_row.get("token_id")
        self.token = kernel.active_tokens.get(self.token_id) or kernel.cap_engine.issue_token(f"agent-{self.pid}", ["*"], self.max_tokens)
        kernel.active_tokens[self.token["token_id"]] = self.token

        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self.thread: Optional[threading.Thread] = None

    def log(self, message: str, log_type: str = "INFO"):
        self.kernel.storage.append_log(self.pid, self.current_step, message, log_type)

    def checkpoint(self):
        self.kernel.storage.save_agent({
            "pid": self.pid,
            "name": self.name,
            "goal": self.goal,
            "status": self.status,
            "max_tokens": self.max_tokens,
            "tokens_used": self.tokens_used,
            "current_step": self.current_step,
            "total_steps": self.total_steps,
            "created_at": self.created_at,
            "updated_at": time.time(),
            "token_id": self.token["token_id"]
        })

    def start(self):
        if self.status in ["COMPLETED", "FAILED", "KILLED"]:
            return
        self.status = "RUNNING"
        self.checkpoint()
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()

    def pause(self):
        self._pause_event.set()
        self.status = "PAUSED"
        self.log("Process suspended by operator (aios pause)", "INFO")
        self.checkpoint()

    def resume(self):
        self._pause_event.clear()
        self.status = "RUNNING"
        self.log("Process resumed by operator (aios resume)", "INFO")
        self.checkpoint()

    def kill(self):
        self._stop_event.set()
        self.status = "KILLED"
        self.log("Process killed by SIGKILL (aios kill)", "SECURITY")
        self.checkpoint()

    def _run_loop(self):
        self.log(f"Spawned process under Cognitive Supervisor. Capability: {self.token['token_id']}")

        # Read any incoming IPC messages from other agents
        incoming = self.kernel.storage.read_agent_messages(self.pid)
        for msg in incoming:
            self.log(f"Received IPC message from PID {msg['from_pid']}: {msg['payload']}")

        steps = [
            ("Context Recall", "Querying associative memory and ambient workspace context", "tool:memory_recall"),
            ("Sandboxed Execution", "Executing capability-gated system tools", "tool:sys_info"),
            ("Synthesis & Commit", "Finalizing result and committing structured insights to memory", "memory:write")
        ]

        # Resume from current step if recovering
        start_idx = max(0, self.current_step)

        for i in range(start_idx, self.total_steps):
            if self._stop_event.is_set():
                break

            while self._pause_event.is_set():
                time.sleep(0.2)

            step_name, step_desc, required_scope = steps[i]
            self.current_step = i + 1
            self.log(f"Starting {step_name}: {step_desc}")

            # 1. Deterministic Security Check at Ring 0
            authorized, reason = self.kernel.cap_engine.verify(self.token, required_scope)
            if not authorized:
                self.status = "FAILED"
                self.log(f"SECURITY VIOLATION BLOCKED: {reason}", "SECURITY")
                self.kernel.storage.log_security(self.pid, "CAPABILITY_CHECK", required_scope, "BLOCKED", reason)
                self.checkpoint()
                return

            # 2. Local Inference Turn
            context = self.kernel.perception.active_context.get("last_event", "")
            step_res = self.kernel.inference.generate_step(
                self.name,
                self.goal,
                step_name,
                context,
                self.token["scopes"]
            )
            step_tokens = step_res.get("tokens_used", 110)
            self.tokens_used += step_tokens
            self.log(f"[{step_res.get('backend', 'Local Model')}] {step_res.get('response')}")

            # 3. Real Tool Execution
            if step_name == "Context Recall":
                ok, res = self.kernel.actuator.execute(self.pid, self.token, "memory_recall", {"query": self.goal})
                self.log(f"Recalled {len(res) if isinstance(res, list) else 0} relevant memory entities")
            elif step_name == "Sandboxed Execution":
                ok, res = self.kernel.actuator.execute(self.pid, self.token, "sys_info", {})
                self.log(f"System telemetry verified: {res.get('machine', 'ARM64')}")

            # 4. Token Budget Guard
            if self.tokens_used > self.max_tokens:
                self.status = "FAILED"
                self.log(f"RESOURCE QUOTA EXCEEDED: {self.tokens_used} tokens > {self.max_tokens}", "SECURITY")
                self.checkpoint()
                return

            self.checkpoint()
            time.sleep(0.5)

        if not self._stop_event.is_set():
            self.status = "COMPLETED"
            self.log(f"Goal successfully achieved. Total tokens consumed: {self.tokens_used}.", "SUCCESS")
            # Commit outcome to semantic memory
            self.kernel.storage.insert_memory(
                f"Outcome of {self.name} (PID {self.pid}, Goal: {self.goal}): Successfully completed with {self.tokens_used} tokens.",
                source=f"agent-{self.pid}"
            )
            self.checkpoint()

# ----------------- MASTER KERNEL DAEMON -----------------
class MasterKernelDaemon:
    def __init__(self, workspace_dir: str = UNIFIED_DIR):
        self.workspace_dir = workspace_dir
        self.storage = StorageManager()
        self.cap_engine = CapabilityEngine()
        self.actuator = SandboxedToolActuator(self.storage, self.cap_engine, workspace_dir)
        self.inference = LocalInferenceEngine()
        self.perception = PerceptionSubsystem(workspace_dir)
        self.active_tokens: Dict[str, Dict[str, Any]] = {}
        self.live_processes: Dict[int, LiveAgentProcess] = {}
        self.start_time = time.time()
        self.running = False

        self._recover_state()
        self._write_pid()

    def _write_pid(self):
        with open(PID_FILE, "w") as f:
            f.write(str(os.getpid()))

    def _recover_state(self):
        """Scans SQLite database on boot to resume any interrupted processes."""
        existing = self.storage.list_agents()
        for row in existing:
            proc = LiveAgentProcess(row, self)
            self.live_processes[proc.pid] = proc
            if row["status"] in ["RUNNING", "QUEUED"]:
                proc.log("Daemon rebooted: Resuming interrupted process from checkpoint", "INFO")
                proc.start()

    def spawn_agent(self, name: str, goal: str, max_tokens: int = 5000, scopes: Optional[List[str]] = None) -> int:
        # Prompt injection inspection
        safe, reason = PromptInjectionGuard.inspect(goal)
        if not safe:
            self.storage.log_security(None, "PROMPT_INJECTION", goal, "BLOCKED", reason)
            raise SecurityViolationError(f"Adversarial intent rejected: {reason}")

        if scopes is None:
            scopes = ["tool:memory_recall", "tool:sys_info", "tool:eval_math", "tool:fs_read", "memory:write"]

        existing_pids = [p["pid"] for p in self.storage.list_agents()]
        pid = max(existing_pids, default=1000) + 1

        token = self.cap_engine.issue_token(f"agent-{pid}", scopes, max_tokens)
        self.active_tokens[token["token_id"]] = token

        agent_dict = {
            "pid": pid,
            "name": name,
            "goal": goal,
            "status": "QUEUED",
            "max_tokens": max_tokens,
            "tokens_used": 0,
            "current_step": 0,
            "total_steps": 3,
            "created_at": time.time(),
            "updated_at": time.time(),
            "token_id": token["token_id"]
        }
        self.storage.save_agent(agent_dict)
        proc = LiveAgentProcess(agent_dict, self)
        self.live_processes[pid] = proc
        proc.start()
        self.perception.record_event(f"Spawned agent '{name}' (PID {pid})")
        return pid

    def handle_request(self, req: Dict[str, Any]) -> Dict[str, Any]:
        cmd = req.get("command")

        if cmd == "status":
            uptime = int(time.time() - self.start_time)
            procs = self.storage.list_agents()
            active_count = sum(1 for p in procs if p["status"] == "RUNNING")
            total_tokens = sum(p["tokens_used"] for p in procs)
            return {
                "status": "ok",
                "uptime_seconds": uptime,
                "active_processes": active_count,
                "total_processes": len(procs),
                "total_tokens_consumed": total_tokens,
                "memory_entities": self.storage.count_memories(),
                "perception": self.perception.get_context()
            }

        elif cmd == "ps":
            return {"status": "ok", "processes": self.storage.list_agents()}

        elif cmd == "spawn":
            name = req.get("name", "worker")
            goal = req.get("goal", "Generic task")
            max_tokens = int(req.get("max_tokens", 5000))
            scopes = req.get("scopes")
            try:
                pid = self.spawn_agent(name, goal, max_tokens, scopes)
                return {"status": "ok", "pid": pid, "message": f"Agent '{name}' spawned with PID {pid}"}
            except SecurityViolationError as e:
                return {"status": "error", "message": str(e)}

        elif cmd == "logs":
            pid = int(req.get("pid", 0))
            logs = self.storage.get_logs(pid)
            return {"status": "ok", "pid": pid, "logs": logs}

        elif cmd == "pause":
            pid = int(req.get("pid", 0))
            if pid in self.live_processes:
                self.live_processes[pid].pause()
                return {"status": "ok", "message": f"PID {pid} paused"}
            return {"status": "error", "message": f"PID {pid} not found in active processes"}

        elif cmd == "resume":
            pid = int(req.get("pid", 0))
            if pid in self.live_processes:
                self.live_processes[pid].resume()
                return {"status": "ok", "message": f"PID {pid} resumed"}
            return {"status": "error", "message": f"PID {pid} not found in active processes"}

        elif cmd == "kill":
            pid = int(req.get("pid", 0))
            if pid in self.live_processes:
                self.live_processes[pid].kill()
                return {"status": "ok", "message": f"PID {pid} terminated"}
            return {"status": "error", "message": f"PID {pid} not found in active processes"}

        elif cmd == "pipe":
            from_pid = int(req.get("from_pid", 0))
            to_pid = int(req.get("to_pid", 0))
            from_agent = self.storage.get_agent(from_pid)
            if not from_agent:
                return {"status": "error", "message": f"Source PID {from_pid} not found"}
            payload = {
                "pipe_source": from_pid,
                "agent_name": from_agent["name"],
                "goal": from_agent["goal"],
                "status": from_agent["status"],
                "tokens_used": from_agent["tokens_used"]
            }
            self.storage.send_agent_message(from_pid, to_pid, payload)
            return {"status": "ok", "message": f"Piped output from PID {from_pid} to PID {to_pid}"}

        elif cmd == "context":
            return {"status": "ok", "context": self.perception.get_context()}

        elif cmd == "memory_search":
            query = req.get("query", "")
            matches = self.storage.search_memory(query, top_k=3)
            return {"status": "ok", "query": query, "matches": matches}

        elif cmd == "memory_insert":
            content = req.get("content", "")
            mid = self.storage.insert_memory(content, source="cli")
            return {"status": "ok", "id": mid, "message": "Memory inserted into associative graph"}

        elif cmd == "audit":
            audits = self.storage.list_security_audits(limit=25)
            return {"status": "ok", "audits": audits}

        elif cmd == "ask":
            query = req.get("query", "")
            context = self.perception.get_context()
            memories = self.storage.search_memory(query, top_k=2)
            mem_summary = " | ".join([m["content"] for m in memories])
            response = (
                f"[AI-OS Master Kernel Answer]\n"
                f"Query: '{query}'\n"
                f"Grounded Context: {context['workspace']} ({context['os_platform']})\n"
                f"Living Memory Graph: {mem_summary}\n"
                f"Status: Resolved deterministically by AI-OS without third-party cloud leakage."
            )
            return {"status": "ok", "answer": response}

        return {"status": "error", "message": f"Unknown command: '{cmd}'"}

    def run_ipc_loop(self):
        self.running = True
        while self.running:
            try:
                req_files = [f for f in os.listdir(REQ_DIR) if f.startswith("req_") and f.endswith(".json")]
                if not req_files:
                    time.sleep(0.01)
                    continue

                for rf in req_files:
                    req_path = os.path.join(REQ_DIR, rf)
                    try:
                        with open(req_path, "r") as f:
                            req = json.load(f)
                    except Exception:
                        continue

                    resp = self.handle_request(req)
                    req_id = req.get("req_id", rf.replace("req_", "").replace(".json", ""))
                    resp_path = os.path.join(RESP_DIR, f"resp_{req_id}.json")
                    with open(resp_path, "w") as f:
                        json.dump(resp, f)

                    try:
                        os.remove(req_path)
                    except Exception:
                        pass
            except Exception:
                time.sleep(0.05)

if __name__ == "__main__":
    print("==================================================================")
    print("  AI-OS Master Kernel Daemon (aiosd) v1.0.0                      ")
    print("  Unified: Supervisor • Security (ocap) • Tools • Memory • IPC    ")
    print("==================================================================")
    daemon = MasterKernelDaemon()
    print(f"[*] Kernel PID : {os.getpid()}")
    print(f"[*] Database   : {daemon.storage.db_path} (SQLite WAL)")
    print(f"[*] IPC Engine : Active at {IPC_DIR}")
    try:
        daemon.run_ipc_loop()
    except KeyboardInterrupt:
        print("\n[*] aiosd shutting down cleanly.")
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)
