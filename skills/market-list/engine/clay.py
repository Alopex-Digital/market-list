"""Talk to Clay's MCP server from the engine (results go to disk, not into Claude's context).

Uses the same login as Claude Code when Clay was connected with the mcp-remote bridge
(`claude mcp add clay -- npx -y mcp-remote@0.1.37 https://api.clay.com/v3/mcp`): the bridge keeps
its login in ~/.mcp-auth, so no second login is needed. Needs Node.js (npx).
"""
import json, subprocess, threading, queue, time, shutil

CLAY_URL = "https://api.clay.com/v3/mcp"
BRIDGE = ["npx", "-y", "mcp-remote@0.1.37", CLAY_URL]


class Clay:
    def __init__(self, timeout=240):
        if not shutil.which("npx"):
            raise RuntimeError("Node.js (npx) is needed for the Clay bridge")
        self.p = subprocess.Popen(BRIDGE, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL, text=True, bufsize=1)
        self.q = queue.Queue()
        self.timeout = timeout
        self.n = 0
        threading.Thread(target=self._read, daemon=True).start()
        self._rpc("initialize", {"protocolVersion": "2024-11-05", "capabilities": {},
                                 "clientInfo": {"name": "market-list", "version": "0.1"}})
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def _read(self):
        for line in self.p.stdout:
            line = line.strip()
            if line.startswith("{"):
                try:
                    self.q.put(json.loads(line))
                except ValueError:
                    pass

    def _send(self, msg):
        self.p.stdin.write(json.dumps(msg) + "\n")
        self.p.stdin.flush()

    def _rpc(self, method, params):
        self.n += 1
        rid = self.n
        self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        end = time.time() + self.timeout
        while time.time() < end:
            try:
                m = self.q.get(timeout=max(0.1, end - time.time()))
            except queue.Empty:
                break
            if m.get("id") == rid:
                if "error" in m:
                    raise RuntimeError(str(m["error"])[:300])
                return m.get("result")
        raise TimeoutError(f"Clay did not answer {method} in {self.timeout}s")

    def call(self, tool, args, retries=2):
        for attempt in range(retries + 1):
            try:
                res = self._rpc("tools/call", {"name": tool, "arguments": args})
                text = "".join(c.get("text", "") for c in (res or {}).get("content", []) if c.get("type") == "text")
                try:
                    return json.loads(text)
                except ValueError:
                    if "concurrent" in text.lower() and attempt < retries:
                        time.sleep(5)
                        continue
                    return {"raw": text}
            except (RuntimeError, TimeoutError):
                if attempt >= retries:
                    raise
                time.sleep(5)

    def close(self):
        try:
            self.p.terminate()
        except Exception:
            pass


DECISION_MAKERS = ('select from people where experiences.any(is_current = true) limit 4 by clay_company_id')


def people_for_domains(clay, domains):
    """Free people search at up to 10 company domains. Returns list of dicts."""
    r = clay.call("search-contacts", {"companyIdentifiers": domains[:10], "dslQuery": DECISION_MAKERS})
    out = []
    for c in (r or {}).get("contacts", []) or []:
        out.append({"domain": c.get("domain") or c.get("companyIdentifier"), "name": c.get("name"),
                    "role": c.get("latest_experience_title", ""), "linkedin": c.get("url", ""),
                    "clay_entity": c.get("entityId"), "clay_task": r.get("taskId")})
    return out, r.get("taskId") if isinstance(r, dict) else None
