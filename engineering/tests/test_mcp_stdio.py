"""End-to-end tests for the MCP server over stdio (Phase 4 M4).

Spawns ``mcp_server.py`` as a subprocess and speaks JSON-RPC 2.0 over
stdio as newline-delimited JSON (one JSON object per line), which is
the framing the MCP Python SDK (2.x) stdio transport uses.  Calls
three tools (scan_ghosts, redlight_compare, export_cad_zmx) plus a
failure case (missing .rez file must produce a tool error, not a
crash).  Fox-Li and Monte Carlo are not exercised here -- they are
slow and already covered by their own test files.
"""

import json
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINEERING = os.path.dirname(HERE)
USER_REZ = "/home/hatch/workspace/user/files/upload.rez"
ENG = os.path.join(HERE, "data", "example-phase4.eng.json")
TIMEOUT_S = 120


class StdioClient:
    """Minimal JSON-RPC client for MCP over stdio (NDJSON framing)."""

    def __init__(self, proc):
        self.proc = proc
        self._next_id = 0

    def _send(self, payload):
        line = (json.dumps(payload) + "\n").encode("utf-8")
        self.proc.stdin.write(line)
        self.proc.stdin.flush()

    def _recv(self):
        line = self.proc.stdout.readline()
        if not line:
            raise EOFError("server closed stdout")
        return json.loads(line.decode("utf-8"))

    def request(self, method, params=None):
        self._next_id += 1
        self._send({"jsonrpc": "2.0", "id": self._next_id,
                    "method": method, "params": params or {}})
        while True:
            msg = self._recv()
            if msg.get("id") == self._next_id:
                return msg

    def notify(self, method, params=None):
        self._send({"jsonrpc": "2.0", "method": method,
                    "params": params or {}})


def _tool_text(result):
    """Extract the text payload of a tools/call result."""
    content = result.get("result", {}).get("content", [])
    texts = [c.get("text", "") for c in content if c.get("type") == "text"]
    return "\n".join(texts)


class TestMcpStdio(unittest.TestCase):
    def setUp(self):
        self.proc = subprocess.Popen(
            [sys.executable, os.path.join(ENGINEERING, "mcp_server.py")],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL)  # server logs go nowhere: the
        # test never reads stderr, and an unread PIPE could fill up
        # (64 KB) and deadlock the server on a crash traceback.
        self.client = StdioClient(self.proc)
        init = self.client.request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "0.1"},
        })
        self.assertIn("result", init)
        self.client.notify("notifications/initialized")

    def tearDown(self):
        try:
            self.proc.stdin.close()
        except BrokenPipeError:
            pass
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(timeout=10)
        self.proc.stdout.close()

    def _call(self, name, arguments):
        msg = self.client.request("tools/call", {
            "name": name, "arguments": arguments})
        self.assertNotIn("error", msg, msg)
        result = msg.get("result", {})
        self.assertFalse(result.get("isError"), result)
        return json.loads(_tool_text(msg))

    def test_tools_list_has_seven_tools(self):
        msg = self.client.request("tools/list")
        self.assertNotIn("error", msg, msg)
        names = [t["name"] for t in msg["result"]["tools"]]
        self.assertEqual(names, [
            "run_foxli", "analyze_thermal_fracture", "scan_ghosts",
            "redlight_compare", "export_cad_zmx", "run_montecarlo",
            "generate_odr_report"])

    def test_scan_ghosts(self):
        rep = self._call("scan_ghosts", {"rez_path": USER_REZ,
                                         "eng_path": ENG})
        self.assertEqual(rep["summary"]["ok"], 6)
        self.assertEqual(rep["summary"]["warn"], 1)
        self.assertEqual(rep["summary"]["fail"], 0)
        self.assertEqual(len(rep["etalons"]), 1)

    def test_redlight_compare(self):
        rep = self._call("redlight_compare",
                         {"rez_path": USER_REZ, "eng_path": ENG})
        self.assertEqual(rep["path"], "fallback")
        m1 = [r for r in rep["table"] if r["element"] == "M1"][0]
        self.assertAlmostEqual(m1["w_633_T_mm"], 0.1040, places=3)

    def test_export_cad_zmx(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            rep = self._call("export_cad_zmx",
                             {"rez_path": USER_REZ, "eng_path": ENG,
                              "out_dir": tmp})
            self.assertTrue(os.path.exists(rep["files"]["zmx"]))
            self.assertTrue(os.path.exists(rep["files"]["dxf"]))
            self.assertTrue(os.path.exists(rep["files"]["coating_txt"]))
            self.assertTrue(rep["zmx_validation"]["ok"])
            self.assertTrue(rep["dxf_validation"]["ok"])
            self.assertEqual(rep["coating_rows"], 14)

    def test_missing_rez_is_tool_error_not_crash(self):
        msg = self.client.request("tools/call", {
            "name": "scan_ghosts",
            "arguments": {"rez_path": "/tmp/no-such-cavity.rez"}})
        self.assertNotIn("error", msg, msg)
        self.assertTrue(msg.get("result", {}).get("isError"))
        self.assertIn("no such .rez file", _tool_text(msg))

    def test_server_still_alive_after_error(self):
        self.test_missing_rez_is_tool_error_not_crash()
        rep = self._call("redlight_compare",
                         {"rez_path": USER_REZ, "eng_path": ENG})
        self.assertEqual(rep["path"], "fallback")


if __name__ == "__main__":
    unittest.main()
