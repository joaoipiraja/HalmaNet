from __future__ import annotations

import json
import socket
import threading
import time
from typing import Callable, Dict, List, Optional

from ..config import HEARTBEAT_SECONDS
from ..protocol import MsgType


class NetClient:
    """
    Cliente robusto para o servidor Halma.

    - Envia HELLO imediatamente após conectar (client-talks-first).
    - Thread de heartbeat envia PING inicial e segue com PINGs periódicos.
    - Loop de recepção com framing por newline e caixa de entrada (inbox).
    - Métodos utilitários: poll(), wait_for(), is_connected(), close().
    """

    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        # Opções de robustez/latência
        try:
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        except Exception:
            pass
        try:
            self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except Exception:
            pass

        # Timeout apenas para conectar (evita travar indefinidamente)
        self.sock.settimeout(10.0)
        self.sock.connect((host, port))

        # Timeout normal alinhado com o servidor (para recv)
        self.sock.settimeout(HEARTBEAT_SECONDS * 3)

        self.recv_buf = b""
        self.lock = threading.Lock()        # protege inbox e flags
        self.send_lock = threading.Lock()   # serializa envios
        self.inbox: List[Dict[str, object]] = []
        self._closed = False
        self._disconnect_posted = False

        # === Handshake: cliente fala primeiro ===
        self._send_hello()

        # Dispara threads
        self._rx_thread = threading.Thread(target=self._recv_loop, daemon=True)
        self._hb_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._rx_thread.start()
        self._hb_thread.start()

    # =======================
    # API pública
    # =======================
    def is_connected(self) -> bool:
        with self.lock:
            return not self._closed

    def send(self, obj: Dict[str, object]) -> bool:
        """
        Envia um objeto JSON com newline framing.
        Retorna True se enviou, False em caso de erro/desconexão.
        """
        with self.lock:
            if self._closed:
                return False
        line = json.dumps(obj, separators=(",", ":")) + "\n"
        data = line.encode("utf-8")
        try:
            with self.send_lock:
                self.sock.sendall(data)
            return True
        except OSError:
            self._mark_disconnected()
            return False

    def poll(self) -> List[Dict[str, object]]:
        """Retorna e limpa a caixa de mensagens recebidas."""
        with self.lock:
            msgs = self.inbox
            self.inbox = []
        return msgs

    def wait_for(
        self,
        predicate: Callable[[Dict[str, object]], bool],
        timeout: float = 5.0
    ) -> Optional[Dict[str, object]]:
        """
        Bloqueia (de forma leve) até chegar uma mensagem que satisfaça o predicado.
        Retorna a mensagem encontrada, ou None se expirar/fechar.
        """
        end = time.time() + timeout
        while time.time() < end and self.is_connected():
            batch = self.poll()
            for m in batch:
                if predicate(m):
                    return m
            time.sleep(0.01)
        return None

    def close(self) -> None:
        """Fecha a conexão de forma idempotente."""
        self._mark_disconnected()

    # =======================
    # Loops internos
    # =======================
    def _recv_loop(self) -> None:
        try:
            while True:
                with self.lock:
                    if self._closed:
                        break
                try:
                    data = self.sock.recv(4096)
                except socket.timeout:
                    continue
                except OSError:
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
        """
        Envia PING periódico; se falhar, encerra.
        Manda um PING inicial imediatamente (sem o primeiro sleep),
        reduzindo o tempo até a primeira mensagem (além do HELLO).
        """
        first = True
        while True:
            with self.lock:
                if self._closed:
                    break
            if not first:
                time.sleep(HEARTBEAT_SECONDS)
            else:
                first = False

            if not self.send({"type": MsgType.PING.value}):
                # send() já marca desconexão
                break

    # =======================
    # Utilitários internos
    # =======================
    def _send_hello(self) -> None:
        """
        Mensagem de abertura para compatibilidade com handshake "client-talks-first".
        """
        # Mesmo se falhar, _recv_loop/heartbeat detectarão a queda e fecharão.
        self.send({"type": "HELLO"})

    def _mark_disconnected(self) -> None:
        """Marca desconexão, posta DISCONNECT uma única vez e fecha o socket com segurança."""
        with self.lock:
            if self._closed:
                return
            self._closed = True
            if not self._disconnect_posted:
                self._disconnect_posted = True
                # Garante que consumidores saibam do término
                try:
                    disc_type = MsgType.DISCONNECT.value  # disponível no seu protocolo
                except Exception:
                    disc_type = "DISCONNECT"
                self.inbox.append({"type": disc_type})

        # Força o desbloqueio de recv/send em outras threads
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except Exception:
            pass
        try:
            self.sock.close()
        except Exception:
            pass

