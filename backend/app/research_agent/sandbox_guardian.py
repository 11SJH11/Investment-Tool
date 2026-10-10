"""Trusted host watchdog, isolated from generated code and the backend lifetime.

Launched with Python -I, a minimal environment and no credentials. EOF on stdin
means the owning backend exited. Only its exact random container can be removed.
"""
import re
import subprocess
import sys
from threading import Event, Thread


def main():
    name=sys.argv[-2]; seconds=float(sys.argv[-1]); command=sys.argv[1:-2]
    if not re.fullmatch(r'[a-f0-9]{64}',name) or not 0<seconds<=600:
        raise SystemExit(2)
    closed=Event()
    def eof():
        sys.stdin.buffer.read();closed.set()
    Thread(target=eof,daemon=True).start()
    closed.wait(seconds)
    try:subprocess.run([*command,'rm','-f',name],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=20)
    except (OSError,subprocess.TimeoutExpired):pass  # Backend restart recovery verifies/removes survivors.


if __name__=='__main__':main()
