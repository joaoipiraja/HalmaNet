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
        self.host = host
        self.port = port

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # Opções de robustez para a conexão
        try:
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except Exception:
            pass

        # Timeout inicial só para a conexão; depois ajustamos para recv
        self.sock.settimeout(10.0)
        self.sock.connect((host, port))
        # Timeout de operação normal (coerente com o servidor)
        self.sock.settimeout(HEARTBEAT_SECONDS * 3)

        self.recv_buf = b""
        self.lock = threading.Lock()        # protege inbox e estado de desconexão
        self.send_lock = threading.Lock()   # serializa envios para evitar interleaving
        self.inbox: List[Dict[str, object]] = []
        self._closed = False
        self._disconnect_posted = False

        threading.Thread(target=self._recv_loop, daemon=True).start()
        threading.Thread(target=self._heartbeat_loop, daemon=True).start()

    # --- API pública ---
    def send(self, obj: Dict[str, object]) -> bool:
        """
        Envia um objeto JSON com newline framing.
        Retorna True se enviou, False se a conexão já caiu/erro ao enviar.
        """
        if self._closed:
            return False
        line = json.dumps(obj, separators=(",", ":")) + "\n"
        data = line.encode("utf-8")
        try:
            with self.send_lock:
                self.sock.sendall(data)
            return True
        except OSError:
            # Marca desconexão e avisa consumidores
            self._mark_disconnected()
            return False

    def poll(self) -> List[Dict[str, object]]:
        """Retorna e limpa a caixa de mensagens recebidas."""
        with self.lock:
            msgs = self.inbox
            self.inbox = []
        return msgs

    def close(self) -> None:
        """Fecha a conexão de forma idempotente."""
        self._mark_disconnected()

    # --- loops internos ---
    def _recv_loop(self) -> None:
        try:
            while not self._closed:
                try:
                    data = self.sock.recv(4096)
                except socket.timeout:
                    # Sem dados nesse intervalo; segue aguardando
                    continue
                except OSError:
                    # Erro de socket (reset, fd inválido, etc.)
                    break

                if not data:
                    # Fechamento limpo pelo servidor
                    break

                self.recv_buf += data
                while b"\n" in self.recv_buf:
                    line, self.recv_buf = self.recv_buf.split(b"\n", 1)
                    if not line:
                        continue
                    try:
                        msg = json.loads(line.decode("utf-8"))
                    except Exception:
                        # Linha inválida: ignora
                        continue
                    with self.lock:
                        self.inbox.append(msg)
        finally:
            self._mark_disconnected()

    def _heartbeat_loop(self) -> None:
        # Envia PING periódico; se falhar, encerra
        while not self._closed:
            time.sleep(HEARTBEAT_SECONDS)
            # Se já caiu, para
            if self._closed:
                break
            ok = self.send({"type": MsgType.PING.value})
            if not ok:
                # send() já marca desconexão; apenas sair
                break

    # --- utilitários internos ---
    def _mark_disconnected(self) -> None:
        """Marca desconexão, posta DISCONNECT uma única vez e fecha o socket com segurança."""
        with self.lock:
            if self._closed:
                return
            self._closed = True

            if not self._disconnect_posted:
                self._disconnect_posted = True
                self.inbox.append({"type": MsgType.DISCONNECT.value})

        # Tenta encerrar o socket sem gerar exceções entre threads
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except Exception:
            pass
        try:
            self.sock.close()
        except Exception:
            pass

