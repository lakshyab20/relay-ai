"""
AI-OS Sandboxed Tool Actuation Subsystem
Provides capability-gated, deterministic execution of real system tools:
- Filesystem (fs_read, fs_write) with path sandbox bounds
- High-precision arithmetic (eval_math)
- System telemetry (sys_info)
- Git repository status (git_status)
- Associative memory recall (memory_recall)
"""

import os
import sys
import platform
import subprocess
from typing import Dict, Any, Tuple
from security import CapabilityEngine, SecurityViolationError, DLPScanner

class SandboxedToolActuator:
    def __init__(self, storage, cap_engine: CapabilityEngine, base_dir: str):
        self.storage = storage
        self.cap_engine = cap_engine
        self.base_dir = os.path.abspath(base_dir)

    def _sanitize_path(self, target_path: str) -> str:
        """Enforces path containment within authorized workspace."""
        if os.path.isabs(target_path):
            abs_p = os.path.abspath(target_path)
        else:
            abs_p = os.path.abspath(os.path.join(self.base_dir, target_path))

        # Sandbox path check
        if not abs_p.startswith(self.base_dir) and not abs_p.startswith("/tmp"):
            raise SecurityViolationError(f"Path escape attempted outside workspace: '{target_path}'")
        return abs_p

    def execute(self, pid: int, token: Dict[str, Any], tool_name: str, params: Dict[str, Any]) -> Tuple[bool, Any]:
        """
        Kernel entry point for tool execution.
        Deterministically checks capability token BEFORE any code runs.
        """
        required_scope = f"tool:{tool_name}"
        authorized, reason = self.cap_engine.verify(token, required_scope)

        if not authorized:
            self.storage.log_security(pid, "TOOL_EXECUTE", tool_name, "BLOCKED", reason)
            raise SecurityViolationError(f"Access Denied to '{tool_name}': {reason}")

        try:
            if tool_name == "fs_read":
                path = self._sanitize_path(params.get("path", ""))
                if not os.path.exists(path):
                    return False, f"File not found: '{path}'"
                with open(path, "r", errors="ignore") as f:
                    content = f.read(params.get("max_bytes", 8192))
                clean_content, leaked = DLPScanner.sanitize(content)
                self.storage.log_security(pid, "TOOL_EXECUTE", tool_name, "ALLOWED", f"Read {len(clean_content)} bytes")
                return True, clean_content

            elif tool_name == "fs_write":
                path = self._sanitize_path(params.get("path", ""))
                content = params.get("content", "")
                clean_content, leaked = DLPScanner.sanitize(content)
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w") as f:
                    f.write(clean_content)
                self.storage.log_security(pid, "TOOL_EXECUTE", tool_name, "ALLOWED", f"Wrote {len(clean_content)} bytes to {os.path.basename(path)}")
                return True, f"Successfully wrote {len(clean_content)} bytes to {os.path.basename(path)}"

            elif tool_name == "eval_math":
                expr = params.get("expression", "").strip()
                # Safe mathematical evaluation without eval()
                clean = expr.replace(" ", "")
                result = None
                for op, fn in [('+', lambda a, b: a + b), ('-', lambda a, b: a - b), ('*', lambda a, b: a * b), ('/', lambda a, b: a / b if b != 0 else "DivZero")]:
                    if op in clean and not (op == '-' and clean.startswith('-')):
                        parts = clean.split(op, 1)
                        try:
                            l, r = float(parts[0]), float(parts[1])
                            result = fn(l, r)
                            break
                        except ValueError:
                            pass
                if result is None:
                    return False, f"Unsupported mathematical expression: '{expr}'"
                self.storage.log_security(pid, "TOOL_EXECUTE", tool_name, "ALLOWED", f"Computed {expr} = {result}")
                return True, f"{expr} = {result}"

            elif tool_name == "sys_info":
                info = {
                    "platform": platform.platform(),
                    "machine": platform.machine(),
                    "python_version": platform.python_version(),
                    "load_avg": os.getloadavg() if hasattr(os, "getloadavg") else "N/A",
                    "workspace": self.base_dir
                }
                self.storage.log_security(pid, "TOOL_EXECUTE", tool_name, "ALLOWED", "System telemetry retrieved")
                return True, info

            elif tool_name == "git_status":
                path = self._sanitize_path(params.get("path", self.base_dir))
                res = subprocess.run(["git", "status", "--short"], cwd=path, capture_output=True, text=True)
                output = res.stdout.strip() or "Working directory clean"
                self.storage.log_security(pid, "TOOL_EXECUTE", tool_name, "ALLOWED", "Git status retrieved")
                return True, output

            elif tool_name == "memory_recall":
                query = params.get("query", "")
                matches = self.storage.search_memory(query, top_k=params.get("top_k", 3))
                self.storage.log_security(pid, "TOOL_EXECUTE", tool_name, "ALLOWED", f"Recalled {len(matches)} memory nodes")
                return True, matches

            else:
                return False, f"Unknown tool: '{tool_name}'"

        except Exception as e:
            return False, f"Tool execution failed: {str(e)}"
