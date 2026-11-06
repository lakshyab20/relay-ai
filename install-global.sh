#!/usr/bin/env bash
# ==============================================================================
# Relay macOS Installer (`install-global.sh`)
# Installs the local UI command and registers the MCP server in supported clients:
# 1. Installs `aios` globally so you never need to `cd` into aios-poc.
# 2. Registers the MCP server in:
#    - Claude Desktop (`~/Library/Application Support/Claude/claude_desktop_config.json`)
#    - Cursor (`~/.cursor/mcp.json`)
#    - OpenAI Codex (`~/.codex/config.toml`)
# Chat histories are not imported. Other clients require their own MCP setup.
# ==============================================================================

set -e

AIOS_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MCP_SERVER="$AIOS_ROOT/mission_control/mcp_server.py"

echo "======================================================================"
echo "  ⚡ Installing AIOS Continuity Globally on your Mac                  "
echo "======================================================================"

# 1. Prepare the user command directory.
mkdir -p "$HOME/.local/bin"
mkdir -p "$HOME/.cursor" "$HOME/.codex"
mkdir -p "$HOME/.cursor" "$HOME/.codex"

# 2. Link `aios` into /opt/homebrew/bin (if writable) and ~/.local/bin
install_link() {
    source_path="$1"
    target_path="$2"
    if [ -e "$target_path" ] && [ ! -L "$target_path" ]; then
        echo "[!] Keeping existing file at $target_path; install the Relay command manually if needed."
        return
    fi
    if [ -L "$target_path" ] && [ "$(readlink "$target_path")" != "$source_path" ]; then
        echo "[!] Keeping existing symlink at $target_path."
        return
    fi
    ln -sfn "$source_path" "$target_path"
}

if [ -w "/opt/homebrew/bin" ]; then
    install_link "$AIOS_ROOT/aios" "/opt/homebrew/bin/aios"
    echo "[✓] Installed global command: /opt/homebrew/bin/aios (Run 'aios' from ANY folder!)"
else
    install_link "$AIOS_ROOT/aios" "$HOME/.local/bin/aios"
    echo "[✓] Installed global command: ~/.local/bin/aios"
fi

# 3. Register the MCP server in Claude Desktop without replacing other settings.
CLAUDE_CONFIG_DIR="$HOME/Library/Application Support/Claude"
CLAUDE_CONFIG_FILE="$CLAUDE_CONFIG_DIR/claude_desktop_config.json"
mkdir -p "$CLAUDE_CONFIG_DIR"

python3 - "$CLAUDE_CONFIG_FILE" "$MCP_SERVER" << 'PYEOF'
import sys, os, json
cfg_path, mcp_script = sys.argv[1], sys.argv[2]
data = {}
if os.path.exists(cfg_path):
    with open(cfg_path, "r") as f:
        data = json.load(f)
if "mcpServers" not in data or not isinstance(data["mcpServers"], dict):
    if "mcpServers" in data:
        raise SystemExit("Existing mcpServers setting is not an object; leaving config unchanged.")
    data["mcpServers"] = {}
if "aios-continuity" not in data["mcpServers"]:
    data["mcpServers"]["aios-continuity"] = {"command": "python3", "args": [mcp_script]}
else:
    print("[i] Claude Desktop already has an aios-continuity entry; leaving it unchanged.")
with open(cfg_path, "w") as f:
    json.dump(data, f, indent=2)
print(f"[✓] Registered Global MCP in Claude Desktop: {cfg_path}")
PYEOF

# 4. Register the MCP server in Cursor without replacing other settings.
CURSOR_CONFIG_FILE="$HOME/.cursor/mcp.json"
python3 - "$CURSOR_CONFIG_FILE" "$MCP_SERVER" << 'PYEOF'
import sys, os, json
cfg_path, mcp_script = sys.argv[1], sys.argv[2]
data = {}
if os.path.exists(cfg_path):
    with open(cfg_path, "r") as f:
        data = json.load(f)
if "mcpServers" not in data or not isinstance(data["mcpServers"], dict):
    if "mcpServers" in data:
        raise SystemExit("Existing mcpServers setting is not an object; leaving config unchanged.")
    data["mcpServers"] = {}
if "aios-continuity" not in data["mcpServers"]:
    data["mcpServers"]["aios-continuity"] = {"command": "python3", "args": [mcp_script]}
else:
    print("[i] Cursor already has an aios-continuity entry; leaving it unchanged.")
with open(cfg_path, "w") as f:
    json.dump(data, f, indent=2)
print(f"[✓] Registered Global MCP in Cursor IDE: {cfg_path}")
PYEOF

# 5. Register the MCP server in OpenAI Codex Global Config (~/.codex/config.toml).
CODEX_CONFIG_FILE="$HOME/.codex/config.toml"
if ! grep -q "aios-continuity" "$CODEX_CONFIG_FILE" 2>/dev/null; then
    cat << EOF >> "$CODEX_CONFIG_FILE"

[mcp_servers.aios-continuity]
command = "python3"
args = ["$MCP_SERVER"]
EOF
    echo "[✓] Registered Global MCP in OpenAI Codex: $CODEX_CONFIG_FILE"
else
    echo "[✓] OpenAI Codex Global MCP already registered: $CODEX_CONFIG_FILE"
fi

echo "======================================================================"
echo "  ✓ Relay command installed and supported MCP clients configured.    "
echo "  Shared memories are available to configured clients on this store. "
echo "  Chat histories are not imported automatically.                     "
echo "======================================================================"
