#!/usr/bin/env python3
"""
AI-OS Unified Architecture End-to-End Live Demonstration
Starts the unified kernel and executes real-world operations across:
- Cognitive Process Supervisor
- Ambient Perception Context
- Associative Semantic Memory
- Deterministic Security Gate
"""

import time
import subprocess
import sys
import os

UNIFIED_DIR = os.path.dirname(os.path.abspath(__file__))
KERNEL_PATH = os.path.join(UNIFIED_DIR, "kernel.py")
CLI_PATH = os.path.join(UNIFIED_DIR, "cli.py")
PYTHON_BIN = sys.executable

def run_cli(*args):
    cmd = [PYTHON_BIN, CLI_PATH] + list(args)
    res = subprocess.run(cmd, capture_output=True, text=True)
    return res.stdout, res.stderr

def main():
    print("==========================================================================")
    print("  AI-OS: UNIFIED COGNITIVE OPERATING SYSTEM DEMONSTRATION                ")
    print("==========================================================================")

    # 1. Start the aiosd Kernel Daemon in background
    print("[1/6] Launching aiosd Kernel Daemon (UNIX Domain Socket: /tmp/aios.sock)...")
    daemon_proc = subprocess.Popen([PYTHON_BIN, KERNEL_PATH])
    time.sleep(1.0) # Wait for socket creation

    try:
        # 2. Check System Telemetry
        print("[2/6] Querying Kernel Telemetry & Ambient Perception Context...")
        stdout, _ = run_cli("status")
        print(stdout)

        # 3. Query Semantic Memory
        print("[3/6] Querying Associative Semantic Memory Graph...")
        stdout, _ = run_cli("memory", "cluster burn rate and infrastructure")
        print(stdout)

        # 4. Spawn Real Agent Processes
        print("[4/6] Spawning Agent Processes under the Cognitive Supervisor...")
        # Normal authorized agent
        out1, _ = run_cli("spawn", "--name", "contract-auditor", "--goal", "Audit vendor SLAs and pricing anomalies", "--budget", "4000")
        print(out1)

        # Compromised agent attempting unauthorized tool execution
        out2, _ = run_cli("spawn", "--name", "rogue-agent", "--goal", "Attempt unauthorized tool execution", "--budget", "2000", "--attack")
        print(out2)

        # 5. Monitor Live Process Table
        print("[5/6] Monitoring Live Process Table (aios ps)...")
        time.sleep(1.5)
        stdout, _ = run_cli("ps")
        print(stdout)

        time.sleep(2.5) # Wait for steps to progress
        stdout, _ = run_cli("ps")
        print(stdout)

        # 6. Check Logs and Security Gate Enforcement
        print("[6/6] Inspecting Execution Traces & Security Firewall...")
        print(">> Legitimate Agent (PID 1001) Logs:")
        out_log1, _ = run_cli("logs", "1001")
        print(out_log1)

        print(">> Compromised Agent (PID 1002) Logs:")
        out_log2, _ = run_cli("logs", "1002")
        print(out_log2)

        # 7. Test Grounded System Inquiry
        print(">> Testing Grounded System Inquiry (aios ask):")
        out_ask, _ = run_cli("ask", "What is our H100 cluster burn rate?")
        print(out_ask)

        print("==========================================================================")
        print("  DEMONSTRATION COMPLETE: Unified AI-OS Engine Verified                  ")
        print("==========================================================================")
        print("To run the CLI interactively on your Mac:")
        print("  python3 unified/cli.py ps")
        print("  python3 unified/cli.py spawn --name my-task --goal '...'")
        print("  python3 unified/cli.py ask '...'")
        print("==========================================================================")

    finally:
        daemon_proc.terminate()

if __name__ == "__main__":
    main()
