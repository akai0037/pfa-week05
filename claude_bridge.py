"""claude_bridge for Unreal Engine 5 (script runner for Claude).

Two ways in, both run code on the game thread:
  1. File drop: put <name>.py in <Documents>/UnrealEngine/claude_bridge/inbox.
     Output goes to outbox/<name>.log (first line "status: OK" or "status: ERROR"),
     and the script moves to done/.
  2. TCP port 127.0.0.1:9877, one JSON object per line:
       {"ping": true}                 -> {"ok": true, "output": "pong from Unreal <version>"}
       {"name": "job", "code": "..."} -> {"ok": bool, "output": str, "seconds": float, "name": str}
Each job is one undo transaction, unless its first line contains "# bridge: no-transaction".
outbox/_status.txt is rewritten every ~0.5 s while the editor is open.
Preloaded names: unreal, actors, level, assets, tools, snap(name, w, h), OUTBOX.
"""
import os, sys, io, time, json, socket, threading, traceback, datetime, builtins
import unreal

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(os.path.dirname(HERE), "claude_bridge")
INBOX = os.path.join(ROOT, "inbox")
OUTBOX = os.path.join(ROOT, "outbox")
DONE = os.path.join(ROOT, "done")
POLL_SEC = 0.5
SETTLE_SEC = 0.4
PORT = 9877

_handle = None
_elapsed = 0.0
_namespace = {}
_busy = False          # re-entrancy guard (level loads can pump Slate ticks mid-job)
_last_poll = 0.0       # throttle so stray old callbacks can't double-poll
_server = None
_jobs = []             # port jobs waiting for the game thread
_jobs_lock = threading.Lock()
_version = "?"

# every tick handle ever registered by any version of this module lives here,
# so start() can remove them all after a reload
if not hasattr(builtins, "_claude_bridge_tick_handles"):
    builtins._claude_bridge_tick_handles = []


class _Tee(io.TextIOBase):
    def __init__(self, original, buffer):
        self.original = original
        self.buffer = buffer
        self._in = False

    def write(self, text):
        if self._in:
            return len(text)
        self._in = True
        try:
            self.buffer.write(text)
            try:
                self.original.write(text)
            except Exception:
                pass
        finally:
            self._in = False
        return len(text)

    def flush(self):
        try:
            self.original.flush()
        except Exception:
            pass


def snap(name="snap", width=1280, height=720):
    """Queue a high-res screenshot of the active level viewport to outbox/<name>.png (written a frame later)."""
    path = os.path.join(OUTBOX, name + ".png").replace("\\", "/")
    unreal.AutomationLibrary.take_high_res_screenshot(width, height, path)
    print("[snap] queued " + path)
    return path


def _fresh_namespace():
    ns = {"__name__": "__claude_bridge__", "unreal": unreal, "snap": snap, "OUTBOX": OUTBOX}
    try:
        ns["actors"] = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        ns["level"] = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        ns["assets"] = unreal.EditorAssetLibrary
        ns["tools"] = unreal.AssetToolsHelpers.get_asset_tools()
    except Exception:
        pass
    return ns


def _write_status():
    try:
        try:
            world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
            lvl = world.get_path_name() if world else "(none)"
        except Exception:
            lvl = "(unknown)"
        with open(os.path.join(OUTBOX, "_status.txt"), "w", encoding="utf-8") as f:
            f.write("alive: %s\nengine: %s\nproject: %s\nlevel: %s\nport: %s\n" % (
                datetime.datetime.now().isoformat(timespec="seconds"), _version,
                unreal.Paths.get_project_file_path(), lvl, PORT if _server else "off"))
    except Exception:
        pass


def _execute(name, code):
    """Run code on the game thread. Returns (ok, output, seconds)."""
    buf = io.StringIO()
    old_out, old_err = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = _Tee(old_out, buf), _Tee(old_err, buf)
    ok = True
    start = time.time()
    print("# --- claude_bridge running %s ---" % name)
    try:
        first = code.splitlines()[0] if code else ""
        if "# bridge: no-transaction" in first:
            exec(compile(code, name, "exec"), _namespace)
        else:
            with unreal.ScopedEditorTransaction("claude_" + os.path.splitext(name)[0]):
                exec(compile(code, name, "exec"), _namespace)
    except Exception:
        ok = False
        traceback.print_exc()
    finally:
        sys.stdout, sys.stderr = old_out, old_err
    return ok, buf.getvalue(), time.time() - start


def _run_file(path):
    name = os.path.basename(path)
    stem, ext = os.path.splitext(name)
    with open(path, "r", encoding="utf-8") as f:
        code = f.read()
    # move it out of the inbox first so nothing can pick it up twice
    dest = os.path.join(DONE, name)
    if os.path.exists(dest):
        dest = os.path.join(DONE, "%s_%d%s" % (stem, int(time.time()), ext))
    os.replace(path, dest)
    ok, out, secs = _execute(name, code)
    header = "status: %s\nfile: %s\nseconds: %.2f\n---\n" % ("OK" if ok else "ERROR", name, secs)
    with open(os.path.join(OUTBOX, stem + ".log"), "w", encoding="utf-8") as f:
        f.write(header + out)


def _run_port_jobs():
    while True:
        with _jobs_lock:
            if not _jobs:
                return
            job = _jobs.pop(0)
        try:
            ok, out, secs = _execute(job["name"], job["code"])
            job["result"] = {"ok": ok, "output": out, "seconds": round(secs, 3), "name": job["name"]}
        except Exception as e:
            job["result"] = {"ok": False, "output": "bridge error: %s" % e, "name": job["name"]}
        job["event"].set()


def _poll():
    global _busy, _last_poll
    now = time.time()
    if _busy or now - _last_poll < POLL_SEC * 0.8:
        return
    _busy = True
    _last_poll = now
    try:
        _run_port_jobs()
        files = sorted(os.path.join(INBOX, n) for n in os.listdir(INBOX)
                       if n.lower().endswith(".py") and not n.startswith("_"))
        for path in files:
            if not os.path.exists(path) or now - os.path.getmtime(path) < SETTLE_SEC:
                continue
            try:
                _run_file(path)
            except Exception:
                traceback.print_exc()
        _write_status()
    finally:
        _busy = False


def _tick(delta):
    global _elapsed
    _elapsed += delta
    if _elapsed < POLL_SEC:
        return
    _elapsed = 0.0
    try:
        _poll()
    except Exception:
        traceback.print_exc()


# ---------------- TCP port (background thread; never touches the Unreal API) ----------------
def _handle_conn(conn):
    try:
        conn.settimeout(10)
        data = b""
        while not data.endswith(b"\n"):
            chunk = conn.recv(65536)
            if not chunk:
                break
            data += chunk
        try:
            msg = json.loads(data.decode("utf-8") or "{}")
        except Exception as e:
            msg = None
            reply = {"ok": False, "output": "bad json: %s" % e}
        if msg is not None:
            if msg.get("ping"):
                reply = {"ok": True, "output": "pong from Unreal %s" % _version}
            elif "code" in msg:
                job = {"name": msg.get("name") or "port_job", "code": msg["code"], "event": threading.Event()}
                with _jobs_lock:
                    _jobs.append(job)
                if job["event"].wait(float(msg.get("timeout", 600))):
                    reply = job["result"]
                else:
                    reply = {"ok": False, "output": "timed out waiting for the game thread", "name": job["name"]}
            else:
                reply = {"ok": False, "output": "expected {\"ping\": true} or {\"name\", \"code\"}"}
        conn.sendall((json.dumps(reply) + "\n").encode("utf-8"))
    except Exception:
        pass
    finally:
        try:
            conn.close()
        except Exception:
            pass


class _Server(object):
    def __init__(self, port):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", port))
        self.sock.listen(8)
        self.sock.settimeout(0.5)
        self.running = True
        self.thread = threading.Thread(target=self._loop, name="claude_bridge_port", daemon=True)
        self.thread.start()

    def _loop(self):
        while self.running:
            try:
                conn, _ = self.sock.accept()
            except socket.timeout:
                continue
            except Exception:
                break
            threading.Thread(target=_handle_conn, args=(conn,), daemon=True).start()

    def shutdown(self):
        self.running = False
        try:
            self.sock.close()
        except Exception:
            pass


def _close_any_server(srv):
    for attr in ("shutdown", "server_close", "close"):
        fn = getattr(srv, attr, None)
        if callable(fn):
            try:
                fn()
            except Exception:
                pass


def start():
    global _handle, _server, _version
    for d in (INBOX, OUTBOX, DONE):
        os.makedirs(d, exist_ok=True)
    stop()
    _version = unreal.SystemLibrary.get_engine_version()
    _namespace.clear()
    _namespace.update(_fresh_namespace())
    for h in list(builtins._claude_bridge_tick_handles):
        try:
            unreal.unregister_slate_post_tick_callback(h)
        except Exception:
            pass
    builtins._claude_bridge_tick_handles[:] = []
    _handle = unreal.register_slate_post_tick_callback(_tick)
    builtins._claude_bridge_tick_handles.append(_handle)
    for attempt in range(6):
        try:
            _server = _Server(PORT)
            break
        except OSError:
            time.sleep(0.3)
    if _server is None:
        unreal.log_warning("[claude_bridge] port %d busy; file drop still works" % PORT)
    _write_status()
    unreal.log("[claude_bridge] watching %s and 127.0.0.1:%d" % (INBOX, PORT))


def stop():
    global _handle, _server
    if _handle is not None:
        try:
            unreal.unregister_slate_post_tick_callback(_handle)
        except Exception:
            pass
        _handle = None
    if _server is not None:
        _close_any_server(_server)
        _server = None
        unreal.log("[claude_bridge] stopped")
