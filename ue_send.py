"""Send Python to the open Unreal Editor through claude_bridge (port 9877) and print the result.

    python ue_send.py --ping                 # is the editor listening?
    python ue_send.py jobs/make_room.py      # run a script file
    python ue_send.py -c "print(len(actors.get_all_level_actors()))"

Exit code 0 = the script ran OK, 1 = it raised an error, 2 = could not reach the editor.
Only uses the Python standard library.
"""
import argparse, json, os, socket, sys

HOST, PORT = "127.0.0.1", 9877


def send(payload, timeout=620):
    with socket.create_connection((HOST, PORT), timeout=5) as s:
        s.settimeout(timeout)
        s.sendall((json.dumps(payload) + "\n").encode("utf-8"))
        data = b""
        while not data.endswith(b"\n"):
            chunk = s.recv(65536)
            if not chunk:
                break
            data += chunk
    return json.loads(data.decode("utf-8"))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("file", nargs="?", help="a .py file to run inside Unreal")
    p.add_argument("-c", "--code", help="run this code string instead of a file")
    p.add_argument("-n", "--name", help="job name (used for the log file); defaults to the file name")
    p.add_argument("--ping", action="store_true", help="just check the bridge is up")
    a = p.parse_args()

    if a.ping:
        payload = {"ping": True}
    elif a.code is not None:
        payload = {"name": a.name or "inline", "code": a.code}
    elif a.file:
        with open(a.file, "r", encoding="utf-8") as f:
            payload = {"name": a.name or os.path.splitext(os.path.basename(a.file))[0], "code": f.read()}
    else:
        p.error("give a file, -c CODE, or --ping")

    try:
        reply = send(payload)
    except OSError as e:
        print("Could not reach Unreal on %s:%d (%s).\nIs the editor open with the bridge installed?" % (HOST, PORT, e))
        sys.exit(2)

    if reply.get("output"):
        print(reply["output"].rstrip())
    status = "OK" if reply.get("ok") else "ERROR"
    extra = (" in %ss" % reply["seconds"]) if "seconds" in reply else ""
    print("[ue_send] %s%s" % (status, extra), file=sys.stderr)
    sys.exit(0 if reply.get("ok") else 1)


if __name__ == "__main__":
    main()
