from __future__ import annotations

import json
import socket
import threading
import time
from typing import Dict, List

from ..config import HEARTBEAT_SECONDS
from ..protocol import MsgType


class NetClient:
    def __init__(self, host: str, port: int) -> None:
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((host, port))
        self.recv_buf = b""
        self.lock = threading.Lock()
        self.inbox: List[Dict[str, object]] = []
        threading.Thread(target=self._recv_loop, daemon=True).start()
        threading.Thread(target=self._heartbeat_loop, daemon=True).start()

    def send(self, obj: Dict[str, object]) -> None:
        line = json.dumps(obj, separators=(",", ":")) + "\n"
        try:
            self.sock.sendall(line.encode("utf-8"))
        except Exception:
            pass

    def _recv_loop(self) -> None:
        try:
            while True:
                data = self.sock.recv(4096)
                if not data:
                    break
                self.recv_buf += data
                while b"\n" in self.recv_buf:
                    line, self.recv_buf = self.recv_buf.split(b"\n", 1)
                    if not line:
                        continue
                    try:
                        msg = json.loads(line.decode("utf-8"))
                    except Exception:
                        continue
                    with self.lock:
                        self.inbox.append(msg)
        finally:
            with self.lock:
                self.inbox.append({"type": MsgType.DISCONNECT.value})

    def _heartbeat_loop(self) -> None:
        while True:
            time.sleep(HEARTBEAT_SECONDS)
            try:
                self.send({"type": MsgType.PING.value})
            except Exception:
                break

    def poll(self) -> List[Dict[str, object]]:
        with self.lock:
            msgs = self.inbox
            self.inbox = []
        return msgs