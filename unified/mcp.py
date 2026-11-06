"""
AI-OS Model Context Protocol (MCP) Driver Subsystem
Implements standard JSON-RPC 2.0 client to interface with any open-source MCP server
(e.g., Filesystem, GitHub, Postgres, Web Search) as native OS device drivers.
"""

import sys
import os
import json
import subprocess
import threading
from typing import Dict, Any, List, Optional

class MCPServerDriver:
    """Manages an individual MCP server running as a sub-process over stdio."""
    def __init__(self, name: str, command: List[str], env: Optional[Dict[str, str]] = None):
        self.name = name
        self.command = command
        self.env = env or dict(os.environ)
        self.process: Optional[subprocess.Popen] = None
        self.request_id = 0
        self.pending_responses: Dict[int, Any] = {}
        self.lock = threading.Lock()
        self.tools_cache: List[Dict[str, Any]] = []

    def start(self):
        try:
            self.process = subprocess.Popen(
                self.command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                env=self.env
            )
            # Start background reader thread
            t = threading.Thread(target=self._read_loop, daemon=True)
            t.start()
            self._initialize()
        except Exception as e:
            sys.stderr.write(f"[AI-OS MCP] Failed to start driver '{self.name}': {e}\n")

    def _initialize(self):
        # MCP Protocol Initialization handshake
        init_req = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "roots": {"listChanged": True},
                    "sampling": {}
                },
                "clientInfo": {
                    "name": "aios-kernel",
                    "version": "1.0.0"
                }
            }
        }
        self.send_request(init_req)

    def _next_id(self) -> int:
        with self.lock:
            self.request_id += 1
            return self.request_id

    def send_request(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not self.process or self.process.poll() is not None:
            return None

        req_id = payload.get("id")
        raw = json.dumps(payload) + "\n"
        with self.lock:
            self.process.stdin.write(raw)
            self.process.stdin.flush()

        # Wait up to 5s for response
        start = time.time()
        while time.time() - start < 5.0:
            with self.lock:
                if req_id in self.pending_responses:
                    return self.pending_responses.pop(req_id)
            time.sleep(0.01)
        return None

    def list_tools(self) -> List[Dict[str, Any]]:
        req = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/list",
            "params": {}
        }
        resp = self.send_request(req)
        if resp and "result" in resp:
            self.tools_cache = resp["result"].get("tools", [])
            return self.tools_cache
        return []

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        req = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        }
        resp = self.send_request(req)
        if resp and "result" in resp:
            return resp["result"]
        elif resp and "error" in resp:
            raise RuntimeError(f"MCP Tool Error: {resp['error']}")
        return None

    def _read_loop(self):
        while self.process and self.process.poll() is None:
            line = self.process.stdout.readline()
            if not line:
                break
            try:
                msg = json.loads(line.strip())
                req_id = msg.get("id")
                if req_id is not None:
                    with self.lock:
                        self.pending_responses[req_id] = msg
            except Exception:
                pass

    def stop(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()

class MCPDriverRegistry:
    """System-wide registry for Model Context Protocol drivers."""
    def __init__(self):
        self.drivers: Dict[str, MCPServerDriver] = {}

    def register(self, name: str, command: List[str]):
        driver = MCPServerDriver(name, command)
        self.drivers[name] = driver

    def get_tool_map(self) -> Dict[str, MCPServerDriver]:
        mapping = {}
        for d in self.drivers.values():
            for t in d.tools_cache:
                mapping[f"mcp:{d.name}:{t['name']}"] = d
        return mapping
