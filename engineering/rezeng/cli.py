"""Wrapper for the ``rezonator --headless`` batch evaluation CLI.

Protocol: see ``rezonator2-phase1-protocol.md``. The request is sent as
UTF-8 bytes on stdin; stdout is read as bytes and decoded as UTF-8
before ``json.loads`` -- never decode with the locale encoding, or
Chinese labels break on Windows (GBK).
"""

import json
import os
import subprocess

from .rez import load_rez

#: Default location of the locally built binary, resolved relative to
#: this package: engineering/rezeng/cli.py -> rezonator2/ -> bin/rezonator.
DEFAULT_BINARY = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "bin", "rezonator"))


class HeadlessError(RuntimeError):
    """Raised when the CLI itself fails (bad request, unloadable schema).

    Per-mutation failures are *not* raised: they are reported inside the
    returned JSON as ``{"ok": false, "error": ...}``.
    """


def run_headless(request, binary=DEFAULT_BINARY, timeout=None):
    """Run one batch evaluation. ``request`` is the protocol dict
    (``{"base_schema": {...}, "mutations": [...]}``).

    Returns the parsed response dict. Raises :class:`HeadlessError`
    when the process exits non-zero (stderr is included in the message)
    or the binary cannot be started.
    """
    env = dict(os.environ)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    # Silence the harmless "XDG_RUNTIME_DIR not set" Qt warning on stderr.
    env.setdefault("XDG_RUNTIME_DIR", "/tmp/runtime-root")
    payload = json.dumps(request, ensure_ascii=False).encode("utf-8")
    try:
        proc = subprocess.run(
            [binary, "--headless"], input=payload,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=timeout, env=env)
    except FileNotFoundError:
        raise HeadlessError("headless binary not found: %s" % binary)
    if proc.returncode != 0:
        raise HeadlessError(
            "headless CLI failed (exit %d): %s"
            % (proc.returncode, proc.stderr.decode("utf-8", "replace").strip()))
    try:
        return json.loads(proc.stdout.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as e:
        raise HeadlessError(
            "headless CLI returned unparsable stdout: %s" % (e,))


def run_headless_file(rez_path, mutations=None, binary=DEFAULT_BINARY,
                      timeout=None):
    """Convenience: load ``rez_path`` and evaluate ``mutations`` (or just
    the base schema when ``mutations`` is empty/None)."""
    data = load_rez(rez_path)
    request = {"base_schema": data}
    if mutations:
        request["mutations"] = mutations
    return run_headless(request, binary=binary, timeout=timeout)
