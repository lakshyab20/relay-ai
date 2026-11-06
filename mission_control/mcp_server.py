#!/usr/bin/env python3
"""
AIOS Universal MCP Server (`mcp_server.py`)
Implements the standard JSON-RPC 2.0 Model Context Protocol over stdio.
Plug this single server into Claude Desktop, Claude Code, Cursor, Gemini, Antigravity, or Codex CLI.
It exposes 4 universal OS tools to every AI app on your Mac:
1. `aios_remember`: Saves an architectural rule, decision, or note in the local shared store.
2. `aios_recall`: Reads memories saved by configured clients from that local store.
3. `aios_safe_write`: Modifies a file while automatically creating a 1-click Time-Machine restore point.
4. `aios_time_machine_revert`: Reverts any file back to its pre-edit snapshot in milliseconds.
"""

import sys
import os
import json
import tempfile
from typing import Dict, Any

MC_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, MC_DIR)

from gateway_engine import MissionControlEngine

engine = MissionControlEngine()

TOOLS_SCHEMA = [
    {
        "name": "aios_remember",
        "description": "Save an architectural decision, API contract, or preference to the local AIOS Shared Brain. Configured clients can retrieve it with aios_recall; chat histories are not imported automatically.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source_app": {"type": "string", "description": "Name of the AI app saving this memory (e.g., Claude Code, Gemini, Cursor)"},
                "category": {"type": "string", "description": "Category (e.g., Architecture Rule, Bug Root Cause, API Contract)"},
                "content": {"type": "string", "description": "The exact rule or context to broadcast across all AI tools"}
            },
            "required": ["source_app", "category", "content"]
        }
    },
    {
        "name": "aios_recall",
        "description": "Retrieve all shared memories, architectural rules, and recent file snapshots across Claude, Gemini, Cursor, and Codex.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "aios_safe_write",
        "description": "Write or update a workspace file with automatic AIOS Time-Machine snapshotting and DLP secret scrubbing.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_app": {"type": "string", "description": "Name of the AI agent modifying the file"},
                "rel_path": {"type": "string", "description": "Relative file path inside the workspace"},
                "content": {"type": "string", "description": "New file content"}
            },
            "required": ["agent_app", "rel_path", "content"]
        }
    },
    {
        "name": "aios_time_machine_revert",
        "description": "Revert a file back to its exact byte-for-byte state before an AI agent modified it using the snapshot ID.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "snapshot_id": {"type": "string", "description": "The snapshot ID (e.g. snap_1a2b3c4d) to roll back"}
            },
            "required": ["snapshot_id"]
        }
    }
]


def handle_rpc(msg: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0" or not isinstance(msg.get("method"), str):
        return {"jsonrpc": "2.0", "id": msg.get("id") if isinstance(msg, dict) else None,
                "error": {"code": -32600, "message": "Invalid Request"}}

    method = msg.get("method")
    req_id = msg.get("id")
    params = msg.get("params") or {}
    if not isinstance(params, dict):
        return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32602, "message": "Invalid params"}}

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "aios-universal-gateway", "version": "1.0.0"}
            }
        }

    elif method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": TOOLS_SCHEMA}
        }

    elif method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        if not isinstance(name, str) or not isinstance(args, dict):
            return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32602, "message": "Invalid params"}}

        if name == "aios_remember":
            res = engine.add_shared_memory(
                source_app=args.get("source_app", "MCP Client"),
                category=args.get("category", "Context"),
                content=args.get("content", "")
            )
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"content": [{"type": "text", "text": f"Saved to the local AIOS Shared Brain ({res['id']}); configured clients can retrieve it with aios_recall. Chat histories are not imported automatically. Memory: {res['content']}"}]}
            }

        elif name == "aios_recall":
            state = engine.get_dashboard_state()
            brain_lines = [f"- [{b['category']}] ({b['source_app']}): {b['content']}" for b in state["shared_brain"]]
            text = "=== AIOS Shared Brain ===\n" + "\n".join(brain_lines)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"content": [{"type": "text", "text": text}]}
            }

        elif name == "aios_safe_write":
            rel_path = args.get("rel_path", "")
            if not isinstance(rel_path, str) or not rel_path.strip():
                return {"jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": "rel_path must be a non-empty workspace-relative path."}], "isError": True}}
            full_path = os.path.realpath(os.path.join(engine.workspace_dir, rel_path))
            workspace = os.path.realpath(engine.workspace_dir)
            if os.path.commonpath([workspace, full_path]) != workspace or full_path == workspace:
                return {"jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": "Path must stay inside the AIOS workspace."}], "isError": True}}
            new_content, _ = engine.scrub_secrets(args.get("content", ""))
            before_content = ""
            if os.path.exists(full_path):
                with open(full_path, "r", errors="ignore") as f:
                    before_content = f.read()
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "w") as f:
                f.write(new_content)
            snap = engine.record_snapshot(
                agent_app=args.get("agent_app", "MCP Agent"),
                action_title=f"Safe-write on {rel_path}",
                rel_path=rel_path,
                before_content=before_content,
                after_content=new_content
            )
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"content": [{"type": "text", "text": f"File written & Time-Machine Snapshot {snap['id']} created (+{snap['lines_added']} / -{snap['lines_removed']} lines)."}]}
            }

        elif name == "aios_time_machine_revert":
            res = engine.rollback_snapshot(args.get("snapshot_id", ""))
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"content": [{"type": "text", "text": json.dumps(res)}]}
            }

        return {"jsonrpc": "2.0", "id": req_id,
                "result": {"content": [{"type": "text", "text": f"Unknown AIOS tool: {name}"}], "isError": True}}

    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Method not found: {method}"}}


def main():
    try:
        ensure_project_mcp_config()
    except Exception as e:
        sys.stderr.write(f"[AIOS MCP Config] {e}\n")

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
            if isinstance(msg, dict) and "id" in msg:
                resp = handle_rpc(msg)
                sys.stdout.write(json.dumps(resp) + "\n")
                sys.stdout.flush()
            elif not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0" or not isinstance(msg.get("method"), str):
                sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": None,
                                             "error": {"code": -32600, "message": "Invalid Request"}}) + "\n")
                sys.stdout.flush()
        except json.JSONDecodeError:
            sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": None,
                                         "error": {"code": -32700, "message": "Parse error"}}) + "\n")
            sys.stdout.flush()
        except Exception as e:
            sys.stderr.write(f"[AIOS MCP Error] {e}\n")
            if isinstance(locals().get("msg"), dict) and "id" in msg:
                sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": msg["id"],
                                             "error": {"code": -32603, "message": "Internal error"}}) + "\n")
                sys.stdout.flush()


def ensure_project_mcp_config():
    """Add the server to project MCP config without replacing user settings."""
    mcp_config_path = os.path.join(engine.workspace_dir, ".mcp.json")
    if os.path.exists(mcp_config_path):
        with open(mcp_config_path, "r") as f:
            cfg = json.load(f)
    else:
        cfg = {}
    servers = cfg.get("mcpServers", {})
    if not isinstance(servers, dict):
        raise ValueError("Existing mcpServers setting is not an object; config left unchanged.")
    if "aios-universal-gateway" in servers:
        return False
    servers["aios-universal-gateway"] = {
        "command": sys.executable,
        "args": [os.path.abspath(__file__)]
    }
    cfg["mcpServers"] = servers
    directory = os.path.dirname(mcp_config_path)
    with tempfile.NamedTemporaryFile("w", dir=directory, delete=False, encoding="utf-8") as f:
        temp_path = f.name
        json.dump(cfg, f, indent=2)
        f.write("\n")
    os.replace(temp_path, mcp_config_path)
    return True


if __name__ == "__main__":
    if "--install-config" in sys.argv:
        installed = ensure_project_mcp_config()
        mcp_config_path = os.path.join(engine.workspace_dir, ".mcp.json")
        action = "Registered" if installed else "Already configured"
        print(f"[+] {action} AIOS Universal MCP Gateway at {mcp_config_path}")
    else:
        main()
