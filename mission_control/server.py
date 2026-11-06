#!/usr/bin/env python3
"""Relay's local dashboard for handoffs, saved context, and file snapshots."""

import os
import sys
import json
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

MC_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, MC_DIR)

from gateway_engine import MissionControlEngine

PORT = 4050
engine = MissionControlEngine()

HTML_UI = """<!DOCTYPE html>
<html lang="en" class="dark">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Relay — Local AI Session Handoff</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script src="https://unpkg.com/lucide@latest"></script>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <script>
    tailwind.config = {
      darkMode: 'class',
      theme: {
        extend: {
          fontFamily: {
            sans: ['"Inter"', '-apple-system', 'BlinkMacSystemFont', 'sans-serif'],
            mono: ['"JetBrains Mono"', 'monospace'],
          }
        }
      }
    }
  </script>
  <style>
    :root {
      color-scheme: dark;
    }
    body {
      background-color: #08090A;
      color: #F3F4F6;
      font-feature-settings: "cv02", "cv03", "cv04", "cv11";
      -webkit-font-smoothing: antialiased;
    }
    .surface {
      background: #101214;
      border: 1px solid rgba(255, 255, 255, 0.07);
    }
    .surface-elevated {
      background: linear-gradient(180deg, rgba(24, 26, 30, 0.9) 0%, rgba(16, 18, 20, 0.95) 100%);
      border: 1px solid rgba(255, 255, 255, 0.09);
      box-shadow: 0 20px 40px -15px rgba(0, 0, 0, 0.7);
    }
    .pill-active {
      background: rgba(255, 255, 255, 0.09);
      border: 1px solid rgba(255, 255, 255, 0.14);
      color: #FFFFFF;
    }
    .diff-add { background: rgba(16, 185, 129, 0.12); color: #6EE7B7; }
    .diff-del { background: rgba(244, 63, 94, 0.12); color: #FDA4AF; }
  </style>
</head>
<body class="min-h-screen flex flex-col selection:bg-indigo-500/30 selection:text-indigo-200">

  <!-- MINIMAL TOP BAR (LINEAR / RAYCAST GRADE) -->
  <header class="border-b border-white/[0.06] bg-[#08090A]/80 backdrop-blur-xl sticky top-0 z-40">
    <div class="max-w-5xl mx-auto px-6 h-14 flex items-center justify-between">
      <div class="flex items-center space-x-3">
        <div class="w-6 h-6 rounded-md bg-white text-black flex items-center justify-center font-bold text-xs tracking-tighter">
          R
        </div>
        <span class="text-sm font-medium text-white tracking-tight">Relay</span>
        <span class="text-white/20">/</span>
        <span id="workspace-name" class="text-xs font-mono text-zinc-400">workspace</span>
      </div>

      <!-- Mode Switcher -->
      <div class="flex items-center space-x-1 bg-zinc-900/90 p-1 rounded-lg border border-white/[0.06] text-xs">
        <button onclick="switchTab('handoff')" id="tab-handoff" class="px-3 py-1 rounded-md font-medium transition pill-active">
          Session Handoff
        </button>
        <button onclick="switchTab('timemachine')" id="tab-timemachine" class="px-3 py-1 rounded-md font-medium text-zinc-400 hover:text-white transition">
          File Time-Machine <span id="snap-badge" class="ml-1 text-[10px] font-mono px-1.5 py-0.2 bg-white/10 rounded">0</span>
        </button>
      </div>

      <div class="flex items-center space-x-2.5 text-xs">
        <span class="flex items-center space-x-1.5 text-zinc-400">
          <span class="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
          <span>Local workspace</span>
        </span>
      </div>
    </div>
  </header>

  <!-- MAIN CONTAINER -->
  <main class="flex-1 max-w-5xl w-full mx-auto px-6 py-10">

    <!-- ================= VIEW 1: SESSION HANDOFF (DEFAULT) ================= -->
    <div id="view-handoff" class="space-y-8">

      <!-- Hero Handoff Banner -->
      <div class="flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div>
          <div class="inline-flex items-center space-x-2 text-xs font-mono text-amber-400/90 bg-amber-500/10 border border-amber-500/20 px-2.5 py-1 rounded-full mb-3">
            <i data-lucide="Flame" class="w-3.5 h-3.5"></i>
            <span>Local project handoff</span>
          </div>
          <h1 class="text-2xl font-semibold tracking-tight text-white">Carry useful context into your next AI session.</h1>
          <p class="text-sm text-zinc-400 mt-1">Build a handoff from memories saved here and file changes recorded in this workspace. Review the capsule before sharing it.</p>
        </div>
      </div>

      <!-- THE 3-STEP CONTINUITY PIPELINE CARD -->
      <div class="surface-elevated rounded-2xl p-6 md:p-8 space-y-6">

        <!-- Source -> Target Selector Bar -->
        <div class="grid grid-cols-1 md:grid-cols-11 gap-4 items-center">

          <!-- Step 1: Paused / Exhausted AI -->
          <div class="md:col-span-5 surface rounded-xl p-4 space-y-2">
            <div class="flex items-center justify-between text-xs">
              <span class="text-zinc-400 font-medium">1. Context source</span>
              <span class="text-[11px] font-mono px-2 py-0.5 rounded bg-white/5 text-zinc-400 border border-white/10">Selected app</span>
            </div>
            <select id="source-ai" onchange="buildHandoffCapsule()" class="w-full bg-transparent text-white font-semibold text-base outline-none cursor-pointer">
              <option value="Claude Desktop" class="bg-zinc-900">Claude Desktop (Opus / Sonnet)</option>
              <option value="Claude Code CLI" class="bg-zinc-900">Claude Code CLI</option>
              <option value="OpenAI Codex App" class="bg-zinc-900">OpenAI Codex App</option>
              <option value="Cursor IDE" class="bg-zinc-900">Cursor IDE</option>
            </select>
            <div class="text-xs text-zinc-500 font-mono truncate" id="source-status">Context comes from saved memories and recorded file changes</div>
          </div>

          <!-- Arrow -->
          <div class="md:col-span-1 flex justify-center">
            <div class="w-9 h-9 rounded-full bg-white/[0.05] border border-white/10 flex items-center justify-center text-zinc-300">
              <i data-lucide="arrow-right" class="w-4 h-4"></i>
            </div>
          </div>

          <!-- Step 2: Target AI to Resume In -->
          <div class="md:col-span-5 surface rounded-xl p-4 space-y-2 border-indigo-500/30">
            <div class="flex items-center justify-between text-xs">
              <span class="text-zinc-400 font-medium">2. Prepare context for</span>
              <span class="text-[11px] font-mono px-2 py-0.5 rounded bg-white/5 text-zinc-400 border border-white/10">Handoff target</span>
            </div>
            <select id="target-ai" onchange="buildHandoffCapsule()" class="w-full bg-transparent text-white font-semibold text-base outline-none cursor-pointer">
              <option value="Gemini" class="bg-zinc-900">Google Gemini (App / CLI)</option>
              <option value="OpenAI Codex App" class="bg-zinc-900">OpenAI Codex App</option>
              <option value="Claude Code CLI" class="bg-zinc-900">Claude Code CLI</option>
              <option value="Cursor IDE" class="bg-zinc-900">Cursor IDE</option>
            </select>
            <div class="text-xs text-zinc-500 font-mono truncate" id="target-sync-method">Local capsule and configured MCP memory</div>
          </div>
        </div>

        <!-- Quick Context Input (Log what you were doing right as Claude ran out) -->
        <div class="pt-2 border-t border-white/[0.06]">
          <form onsubmit="saveCheckpoint(event)" class="flex flex-col sm:flex-row gap-2.5">
            <textarea
              id="checkpoint-input"
              rows="2"
              maxlength="4000"
              aria-label="Checkpoint to include in the handoff capsule"
              placeholder="Add the goal, next step, or decision you want the next AI to know..."
              class="flex-1 bg-black/50 border border-white/10 focus:border-white/25 rounded-xl px-4 py-2.5 text-xs text-white placeholder-zinc-500 outline-none transition resize-y"
            ></textarea>
            <button type="submit" class="px-4 py-2.5 rounded-xl bg-white/10 hover:bg-white/15 text-white text-xs font-medium transition whitespace-nowrap">
              Save Checkpoint
            </button>
          </form>
        </div>

        <!-- LIVE HANDOFF CAPSULE PREVIEW -->
        <div class="space-y-3">
          <div class="flex items-center justify-between">
            <div class="flex items-center space-x-2">
              <span class="text-xs font-mono uppercase tracking-wider text-zinc-400">Live Continuity Capsule</span>
              <span class="text-[11px] font-mono text-zinc-500">(Generated locally; copy the capsule into browser chats)</span>
            </div>
            <div class="flex items-center space-x-2">
              <button onclick="copyHandoffCapsule()" class="px-3.5 py-1.5 rounded-lg bg-white text-black hover:bg-zinc-200 text-xs font-semibold flex items-center space-x-1.5 transition shadow-sm active:scale-95">
                <i data-lucide="copy" class="w-3.5 h-3.5"></i>
                <span id="copy-btn-text">Copy Handoff Capsule for Web Chat</span>
              </button>
            </div>
          </div>

          <pre id="capsule-preview" class="surface rounded-xl p-5 text-xs font-mono text-zinc-300 overflow-x-auto leading-relaxed whitespace-pre-wrap select-all"></pre>
        </div>

        <!-- How it works footer inside card -->
        <div class="grid grid-cols-1 md:grid-cols-3 gap-4 pt-2 border-t border-white/[0.06] text-xs text-zinc-400">
          <div class="flex items-start space-x-2.5">
            <i data-lucide="check-circle-2" class="w-4 h-4 text-emerald-400 shrink-0 mt-0.5"></i>
            <div><strong class="text-zinc-200">Configured MCP clients:</strong> They can save and retrieve memories from this workspace when they use the Relay tools.</div>
          </div>
          <div class="flex items-start space-x-2.5">
            <i data-lucide="check-circle-2" class="w-4 h-4 text-emerald-400 shrink-0 mt-0.5"></i>
            <div><strong class="text-zinc-200">Project context:</strong> The capsule contains only the local memories and recorded changes shown here. Check it for gaps before copying.</div>
          </div>
          <div class="flex items-start space-x-2.5">
            <i data-lucide="check-circle-2" class="w-4 h-4 text-emerald-400 shrink-0 mt-0.5"></i>
            <div><strong class="text-zinc-200">Browser chats:</strong> Copy the capsule and paste it into the next chat. Browser chat history is not imported automatically.</div>
          </div>
        </div>

      </div>

      <!-- RECENT SHARED MEMORY TIMELINE -->
      <div class="space-y-3">
        <div class="flex items-center justify-between">
          <h2 class="text-xs font-mono uppercase tracking-wider text-zinc-400">Saved memories</h2>
          <span class="text-xs text-zinc-500 font-mono">Stored in local SQLite WAL</span>
        </div>
        <div id="brain-timeline" class="grid grid-cols-1 md:grid-cols-2 gap-3"></div>
      </div>

    </div>

    <!-- ================= VIEW 2: FILE TIME-MACHINE ================= -->
    <div id="view-timemachine" class="hidden space-y-6">
      <div class="flex items-center justify-between">
        <div>
          <h2 class="text-xl font-semibold text-white tracking-tight">File Time-Machine</h2>
          <p class="text-sm text-zinc-400 mt-0.5">Changes detected in watched workspace files are recorded with diffs. Restore a file to the version captured before a recorded change.</p>
        </div>
      </div>

      <div id="snapshots-container" class="space-y-4"></div>
    </div>

  </main>

  <!-- SUBTLE TOAST -->
  <div id="toast" class="fixed bottom-6 right-6 z-50 transform translate-y-20 opacity-0 transition-all duration-200 surface-elevated px-4 py-3 rounded-xl flex items-center space-x-3">
    <span class="w-2 h-2 rounded-full bg-emerald-400"></span>
    <span id="toast-text" class="text-xs font-medium text-white"></span>
  </div>

  <script>
    let latestState = null;

    function escapeHtml(value) {
      return String(value ?? '').replace(/[&<>"']/g, char => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
      })[char]);
    }

    function notify(msg) {
      const t = document.getElementById('toast');
      document.getElementById('toast-text').textContent = msg;
      t.classList.remove('translate-y-20', 'opacity-0');
      setTimeout(() => t.classList.add('translate-y-20', 'opacity-0'), 3000);
    }

    function switchTab(tab) {
      const vHandoff = document.getElementById('view-handoff');
      const vTm = document.getElementById('view-timemachine');
      const bHandoff = document.getElementById('tab-handoff');
      const bTm = document.getElementById('tab-timemachine');

      if (tab === 'handoff') {
        vHandoff.classList.remove('hidden');
        vTm.classList.add('hidden');
        bHandoff.className = 'px-3 py-1 rounded-md font-medium transition pill-active';
        bTm.className = 'px-3 py-1 rounded-md font-medium text-zinc-400 hover:text-white transition';
      } else {
        vHandoff.classList.add('hidden');
        vTm.classList.remove('hidden');
        bTm.className = 'px-3 py-1 rounded-md font-medium transition pill-active';
        bHandoff.className = 'px-3 py-1 rounded-md font-medium text-zinc-400 hover:text-white transition';
      }
    }

    function buildHandoffCapsule() {
      if (!latestState) return;
      const sourceAi = document.getElementById('source-ai').value;
      const targetAi = document.getElementById('target-ai').value;
      const workspaceName = latestState.workspace.split(/[\\/]/).filter(Boolean).pop() || 'workspace';

      const recentBrain = (latestState.shared_brain || []).slice(0, 5);
      const recentSnaps = (latestState.snapshots || []).filter(s => s.reverted === 0).slice(0, 3);

      let lines = [];
      lines.push(`# RELAY CONTINUITY HANDOFF (${sourceAi} -> ${targetAi})`);
      lines.push(`Workspace: ${workspaceName}`);
      lines.push(`Preparing a handoff from ${sourceAi} to ${targetAi}. This capsule contains only the local project context listed below.\\n`);

      lines.push(`## 1. Active Context & Architectural Decisions`);
      if (recentBrain.length === 0) lines.push(`- No memories have been saved yet.`);
      recentBrain.forEach(b => {
        lines.push(`- [${b.category}] (from ${b.source_app}): ${b.content}`);
      });

      lines.push(`\\n## 2. Recent Files Modified in This Session`);
      if (recentSnaps.length === 0) {
        lines.push(`- No recent file changes are recorded across ${latestState.watched_files_count} watched workspace files.`);
      } else {
        recentSnaps.forEach(s => {
          lines.push(`- ${s.rel_path}: ${s.action_title} (+${s.lines_added} / -${s.lines_removed} lines) by ${s.agent_app}`);
        });
      }

      lines.push(`\\n## 3. Instruction for ${targetAi}`);
      lines.push(`Review the repository state and this capsule, then continue from the next unfinished task.`);

      document.getElementById('capsule-preview').textContent = lines.join('\\n');
    }

    async function copyHandoffCapsule() {
      const text = document.getElementById('capsule-preview').textContent;
      try {
        await navigator.clipboard.writeText(text);
        const btn = document.getElementById('copy-btn-text');
        btn.textContent = 'Copied to Clipboard!';
        notify('Capsule copied. Review it before pasting into another chat.');
        setTimeout(() => { btn.textContent = 'Copy Handoff Capsule for Web Chat'; }, 2500);
      } catch (error) {
        notify('Clipboard access failed. Select and copy the capsule text manually.');
      }
    }

    async function saveCheckpoint(e) {
      e.preventDefault();
      const input = document.getElementById('checkpoint-input');
      const source_app = document.getElementById('source-ai').value;
      const content = input.value.trim();
      if (!content) return;

      try {
        const response = await fetch('/api/remember', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ source_app, category: 'Session Handoff Checkpoint', content })
        });
        if (!response.ok) throw new Error('Save failed');
        input.value = '';
        notify('Checkpoint saved to this workspace.');
        await loadState();
      } catch (error) {
        notify('Could not save the checkpoint. Check that Relay is still running.');
      }
    }

    async function revertSnapshot(snapId) {
      const res = await fetch('/api/rollback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ snap_id: snapId })
      });
      const data = await res.json();
      notify(data.message);
      await loadState();
    }

    async function loadState() {
      const res = await fetch('/api/state');
      latestState = await res.json();
      document.getElementById('workspace-name').textContent = latestState.workspace.split(/[\\/]/).filter(Boolean).pop() || 'workspace';

      const activeSnaps = (latestState.snapshots || []).filter(s => s.reverted === 0).length;
      document.getElementById('snap-badge').textContent = activeSnaps;

      buildHandoffCapsule();

      // Render Shared Brain timeline
      const memories = (latestState.shared_brain || []).slice(0, 6);
      document.getElementById('brain-timeline').innerHTML = memories.length ? memories.map(b => `
        <div class="surface rounded-xl p-4 flex flex-col justify-between space-y-2">
          <div class="flex items-center justify-between text-[11px] font-mono text-zinc-400">
            <span class="text-white font-medium">${escapeHtml(b.source_app)}</span>
            <span>${escapeHtml(b.category)}</span>
          </div>
          <p class="text-xs text-zinc-300 leading-relaxed">${escapeHtml(b.content)}</p>
        </div>
      `).join('') : `
        <div class="surface rounded-xl p-5 text-sm text-zinc-400 md:col-span-2">
          No saved memories yet. Add a checkpoint above, or ask a connected MCP client to save an important decision with <code>aios_remember</code>.
        </div>
      `;

      // Render Time-Machine snapshots
      const snaps = latestState.snapshots || [];
      const container = document.getElementById('snapshots-container');
      if (snaps.length === 0) {
        container.innerHTML = `
          <div class="surface rounded-2xl p-8 text-center text-sm text-zinc-400">
            No file changes have been recorded yet. Make a change to a watched file and it will appear after the next workspace scan.
          </div>
        `;
      } else {
        container.innerHTML = snaps.map(s => {
          const diffHtml = (s.unified_diff || '').split('\\n').slice(0, 12).map(line => {
            const esc = escapeHtml(line);
            if (line.startsWith('+') && !line.startsWith('+++')) return `<div class="diff-add px-2">${esc}</div>`;
            if (line.startsWith('-') && !line.startsWith('---')) return `<div class="diff-del px-2">${esc}</div>`;
            return `<div class="text-zinc-500 px-2">${esc}</div>`;
          }).join('');

          return `
            <div class="surface rounded-2xl p-5 space-y-3 ${s.reverted ? 'opacity-50' : ''}">
              <div class="flex items-center justify-between">
                <div class="flex items-center space-x-2.5 text-xs">
                  <span class="px-2 py-0.5 rounded bg-white/10 text-white font-medium">${escapeHtml(s.agent_app)}</span>
                  <span class="font-mono text-zinc-200 font-semibold">${escapeHtml(s.rel_path)}</span>
                  <span class="font-mono text-emerald-400">+${escapeHtml(s.lines_added)}</span>
                  <span class="font-mono text-rose-400">-${escapeHtml(s.lines_removed)}</span>
                </div>
                ${s.reverted
                  ? `<span class="text-xs font-mono text-zinc-500">Reverted</span>`
                  : `<button onclick="revertSnapshot('${escapeHtml(s.id)}')" class="px-3 py-1.5 rounded-lg bg-white text-black hover:bg-zinc-200 text-xs font-semibold transition">
                       Revert File (${escapeHtml(s.id)})
                     </button>`
                }
              </div>
              <pre class="text-[11px] font-mono bg-black/60 rounded-xl p-3 overflow-x-auto border border-white/[0.05]">${diffHtml}</pre>
            </div>
          `;
        }).join('');
      }

      lucide.createIcons();
    }

    loadState();
    setInterval(loadState, 3000);
  </script>
</body>
</html>
"""


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


class MissionControlHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def _send_json(self, payload: dict, status: int = 200):
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/index.html"):
            raw = HTML_UI.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        elif self.path.startswith("/api/state"):
            self._send_json(engine.get_dashboard_state())
        else:
            self._send_json({"error": "Not found"}, 404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length).decode("utf-8")) if length > 0 else {}

        if self.path == "/api/rollback":
            res = engine.rollback_snapshot(body.get("snap_id", ""))
            self._send_json(res)
        elif self.path == "/api/remember":
            res = engine.add_shared_memory(
                source_app=body.get("source_app", "Claude Desktop"),
                category=body.get("category", "Session Handoff Checkpoint"),
                content=body.get("content", "")
            )
            self._send_json(res)
        elif self.path == "/api/firewall":
            res = engine.inspect_command(
                agent_app=body.get("agent_app", "Codex CLI"),
                command=body.get("command", "")
            )
            self._send_json(res)
        else:
            self._send_json({"error": "Not found"}, 404)


def main():
    ThreadingMixIn.allow_reuse_address = True
    HTTPServer.allow_reuse_address = True
    server = ThreadedHTTPServer(("127.0.0.1", PORT), MissionControlHandler)
    url = f"http://localhost:{PORT}"
    print("==========================================================================")
    print("  ⚡ Relay dashboard — LIVE AT:", url)
    print("  * Project handoff  : saved memories + recorded file changes")
    print("  * Local Shared Context: .aios_shared_context.md (configured clients only)")
    print("==========================================================================")
    if "--no-browser" not in sys.argv:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[*] Relay stopped.")


if __name__ == "__main__":
    main()
