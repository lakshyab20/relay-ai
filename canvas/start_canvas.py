#!/usr/bin/env python3
import http.server
import socketserver
import webbrowser
import os
import sys

PORT = 3000
DIRECTORY = os.path.dirname(os.path.abspath(__file__))

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

    def log_message(self, format, *args):
        # Clean custom logging
        sys.stderr.write(f"[AI-OS Canvas] {args[0]} - {args[1]}\n")

def main():
    os.chdir(DIRECTORY)
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        url = f"http://localhost:{PORT}"
        print("==================================================================")
        print("  AI-OS Generative Intent Canvas (Direction 3 Prototype)          ")
        print("==================================================================")
        print(f"[*] Serving Canvas at: {url}")
        print("[*] Opening in your default web browser...")
        print("[*] Press Ctrl+C in this terminal to stop the server.")
        print("==================================================================")

        # Open in default browser
        webbrowser.open(url)

        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n[AI-OS Canvas] Server stopped cleanly.")

if __name__ == "__main__":
    main()
