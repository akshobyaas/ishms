import subprocess, sys, os, time, signal, argparse

BASE = os.path.dirname(os.path.abspath(__file__))
CMD  = [sys.executable, os.path.join(BASE, "manage.py")]

parser = argparse.ArgumentParser(description="Start TelemetryOS")
parser.add_argument("--interval", type=float, default=2.0)
args = parser.parse_args()

procs = []


def start(cmd):
    p = subprocess.Popen(cmd, cwd=BASE)
    procs.append(p)
    return p


def shutdown(*_):
    print("\nShutting down...")
    for p in procs:
        p.terminate()
        try:
            p.wait(3)
        except subprocess.TimeoutExpired:
            p.kill()
    sys.exit(0)


signal.signal(signal.SIGINT, shutdown)
signal.signal(signal.SIGTERM, shutdown)

print("Starting TelemetryOS...\n" + "-"*40)

collector = start(CMD + ["collect_telemetry", f"--interval={args.interval}"])
print(f"Collector → PID {collector.pid}")

server = start(CMD + ["runserver", "--noreload"])
print(f"Server    → PID {server.pid}")

print("-"*40)
print("Dashboard → http://127.0.0.1:8000")
print("Ctrl+C to stop\n" + "-"*40)

while True:
    time.sleep(2)
    if any(p.poll() is not None for p in procs):
        print("\nA process exited. Shutting down.")
        shutdown()