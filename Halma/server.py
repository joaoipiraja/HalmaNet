from __future__ import annotations

import json
import logging
import socket
import threading
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Set, Tuple

from .board import Board, compute_moves
from .protocol import Cell, MsgType
from .config import HEARTBEAT_SECONDS, MAX_CHAT_HISTORY


@dataclass
class JumpLock:
    player: int
    pos: List[int]  # [r, c]


class HalmaServer:
    def __init__(self, host: str = "0.0.0.0", port: int = 50007) -> None:
        self.host = host
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.clients: List[Tuple[socket.socket, Tuple[str, int], Optional[int]]] = []  # (conn, addr, player_id)
        self.clients_lock = threading.Lock()
        self.state_lock = threading.Lock()
        self.logger = logging.getLogger("halma.server")
        self.reset()

    def start(self) -> None:
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((self.host, self.port))
        self.sock.listen(5)
        self.logger.info("Servidor ouvindo em %s:%s", self.host, self.port)
        threading.Thread(target=self._accept_loop, daemon=True).start()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            self.logger.info("Encerrando servidor...")
        finally:
            with self.clients_lock:
                for c, *_ in self.clients:
                    try:
                        c.close()
                    except Exception:
                        pass
            self.sock.close()

    def reset(self) -> None:
        with self.state_lock:
            self.board = Board()
            self.turn: int = Cell.P1
            self.winner: Optional[int] = None
            self.chat_log: List[Dict[str, object]] = []  # {player, text}
            self.player_slots: Dict[int, Optional[socket.socket]] = {Cell.P1: None, Cell.P2: None}
            self.jump_lock: Optional[JumpLock] = None
            self.reset_votes: Set[int] = set()

    # --- rede ---
    def _accept_loop(self) -> None:
        while True:
            conn, addr = self.sock.accept()
            self.logger.info("Conectado: %s", addr)
            threading.Thread(target=self._client_thread, args=(conn, addr), daemon=True).start()

    def _safe_send(self, conn: socket.socket, obj: Dict[str, object]) -> bool:
        line = json.dumps(obj, separators=(",", ":")) + "\n"
        try:
            conn.sendall(line.encode("utf-8"))
            return True
        except Exception:
            return False

    def _broadcast(self, obj: Dict[str, object]) -> None:
        dead: List[socket.socket] = []
        with self.clients_lock:
            for (c, _, _) in self.clients:
                if not self._safe_send(c, obj):
                    dead.append(c)
            if dead:
                self.clients = [(c, a, p) for (c, a, p) in self.clients if c not in dead]
                for d in dead:
                    self._release_player(d)

    def _push_state(self) -> None:
        with self.state_lock:
            state = {
                "type": MsgType.STATE.value,
                "board": self.board.serialize(),
                "turn": int(self.turn),
                "winner": int(self.winner) if self.winner is not None else None,
                "chat": self.chat_log[-MAX_CHAT_HISTORY:],
                "players": {"p1": self.player_slots[Cell.P1] is not None, "p2": self.player_slots[Cell.P2] is not None},
                "jump_lock": None if not self.jump_lock else {"player": int(self.jump_lock.player), "pos": self.jump_lock.pos},
                "reset_votes": {"p1": Cell.P1 in self.reset_votes, "p2": Cell.P2 in self.reset_votes},
            }
        self._broadcast(state)

    # --- jogadores ---
    def _assign_player(self, conn: socket.socket) -> Optional[int]:
        with self.state_lock:
            pid: Optional[int] = None
            if self.player_slots[Cell.P1] is None:
                self.player_slots[Cell.P1] = conn
                pid = Cell.P1
            elif self.player_slots[Cell.P2] is None:
                self.player_slots[Cell.P2] = conn
                pid = Cell.P2
            return pid

    def _release_player(self, conn: socket.socket) -> None:
        with self.state_lock:
            for p in (Cell.P1, Cell.P2):
                if self.player_slots[p] is conn:
                    self.player_slots[p] = None
            if self.jump_lock and self.player_slots.get(self.jump_lock.player) is None:
                self.jump_lock = None
            self.reset_votes = {p for p in self.reset_votes if self.player_slots.get(p) is not None}

    # --- regras ---
    def _apply_move(self, pid: int, src: Tuple[int, int], dst: Tuple[int, int]) -> bool:
        r0, c0 = src
        self.board.set_cell(r0, c0, Cell.EMPTY)
        self.board.set_cell(dst[0], dst[1], pid)

        if self.board.is_victory(pid):
            self.winner = pid
            self.jump_lock = None
            return True

        _, next_jumps = compute_moves(self.board, dst)
        if dst in next_jumps:
            next_jumps.remove(dst)
        if next_jumps:
            self.jump_lock = JumpLock(player=pid, pos=[dst[0], dst[1]])
            return False
        else:
            self.jump_lock = None
            self.turn = Cell.P2 if self.turn == Cell.P1 else Cell.P1
            return True

    def _validate_and_apply_move(self, pid: int, move: Dict[str, object]) -> Tuple[bool, Optional[str]]:
        with self.state_lock:
            if self.winner:
                return False, "Partida encerrada"
            if pid != self.turn:
                return False, "Não é a sua vez"

            src_list = move.get("src", [])
            dst_list = move.get("dst", [])
            try:
                src: Tuple[int, int] = (int(src_list[0]), int(src_list[1]))  # type: ignore[index]
                dst: Tuple[int, int] = (int(dst_list[0]), int(dst_list[1]))  # type: ignore[index]
            except Exception:
                return False, "Movimento inválido"

            r0, c0 = src
            if not self.board.inside(r0, c0) or self.board.cell(r0, c0) != pid:
                return False, "Origem inválida"

            simple, jumps = compute_moves(self.board, src)

            if self.jump_lock and self.jump_lock.player == pid:
                if src != tuple(self.jump_lock.pos):
                    return False, "Você deve continuar a cadeia de saltos com a mesma peça"
                if dst not in jumps:
                    return False, "Apenas saltos são permitidos durante a cadeia"
                self._apply_move(pid, src, dst)
                return True, None

            if dst in simple:
                self.board.set_cell(r0, c0, Cell.EMPTY)
                self.board.set_cell(dst[0], dst[1], pid)
                if self.board.is_victory(pid):
                    self.winner = pid
                else:
                    self.turn = Cell.P2 if self.turn == Cell.P1 else Cell.P1
                self.jump_lock = None
                return True, None
            elif dst in jumps:
                self._apply_move(pid, src, dst)
                return True, None
            else:
                return False, "Destino não é válido"

    def _end_jump_chain(self, pid: int) -> Tuple[bool, Optional[str]]:
        with self.state_lock:
            if not self.jump_lock or self.jump_lock.player != pid:
                return False, "Nenhuma cadeia de saltos ativa"
            self.jump_lock = None
            if not self.winner:
                self.turn = Cell.P2 if self.turn == Cell.P1 else Cell.P1
            return True, None

    def _resign(self, pid: int) -> Tuple[bool, Optional[str]]:
        with self.state_lock:
            if self.winner is not None:
                return False, "Partida já encerrada"
            if pid not in (Cell.P1, Cell.P2):
                return False, "Apenas jogadores podem desistir"
            self.winner = Cell.P2 if pid == Cell.P1 else Cell.P1
            self.jump_lock = None
            self.chat_log.append({"player": 0, "text": f"Jogador {1 if pid == Cell.P1 else 2} desistiu."})
            self.reset_votes.clear()
            return True, None

    def _request_reset(self, pid: int) -> Tuple[bool, Optional[str], bool]:
        with self.state_lock:
            if pid not in (Cell.P1, Cell.P2):
                return False, "Apenas jogadores podem solicitar reinício", False
            if pid in self.reset_votes:
                return True, None, False
            self.reset_votes.add(pid)
            self.chat_log.append({"player": 0, "text": f"Jogador {1 if pid == Cell.P1 else 2} solicitou reinício."})
            if Cell.P1 in self.reset_votes and Cell.P2 in self.reset_votes:
                self.chat_log.append({"player": 0, "text": "Partida será reiniciada por consenso dos dois jogadores."})
                return True, None, True
            return True, None, False

    # --- loop do cliente ---
    def _client_thread(self, conn: socket.socket, addr: Tuple[str, int]) -> None:
        buf = b""
        with self.clients_lock:
            pid = self._assign_player(conn)
            self.clients.append((conn, addr, pid))
        self._safe_send(conn, {"type": MsgType.JOIN.value, "player": int(pid) if pid is not None else None})
        self._push_state()

        try:
            conn.settimeout(HEARTBEAT_SECONDS * 3)
            while True:
                data = conn.recv(4096)
                if not data:
                    break
                buf += data
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    if not line:
                        continue
                    try:
                        msg = json.loads(line.decode("utf-8"))
                    except Exception:
                        self._safe_send(conn, {"type": MsgType.ERROR.value, "message": "JSON inválido"})
                        continue

                    mtype = msg.get("type")
                    if mtype == MsgType.CHAT.value:
                        text = str(msg.get("text", ""))[:500]
                        with self.state_lock:
                            self.chat_log.append({"player": int(pid) if pid else 0, "text": text})
                        self._broadcast({"type": MsgType.CHAT.value, "player": int(pid) if pid else None, "text": text})

                    elif mtype == MsgType.MOVE.value:
                        ok, err = self._validate_and_apply_move(int(pid) if pid else 0, msg)
                        if not ok:
                            self._safe_send(conn, {"type": MsgType.ERROR.value, "message": err})
                        with self.state_lock:
                            if self.reset_votes:
                                self.reset_votes.clear()
                                self.chat_log.append({"player": 0, "text": "Votos de reinício foram limpos após novo lance."})
                        self._push_state()

                    elif mtype == MsgType.ENDJUMP.value:
                        ok, err = self._end_jump_chain(int(pid) if pid else 0)
                        if not ok:
                            self._safe_send(conn, {"type": MsgType.ERROR.value, "message": err})
                        self._push_state()

                    elif mtype == MsgType.RESET.value:
                        ok, err, should_reset = self._request_reset(int(pid) if pid else 0)
                        if not ok:
                            self._safe_send(conn, {"type": MsgType.ERROR.value, "message": err})
                            self._push_state()
                            continue
                        if should_reset:
                            self.reset()
                            self.chat_log.append({"player": 0, "text": "Partida reiniciada."})
                        self._push_state()

                    elif mtype == MsgType.RESIGN.value:
                        ok, err = self._resign(int(pid) if pid else 0)
                        if not ok:
                            self._safe_send(conn, {"type": MsgType.ERROR.value, "message": err})
                        self._push_state()

                    elif mtype == MsgType.PING.value:
                        self._safe_send(conn, {"type": MsgType.PONG.value})

                    else:
                        self._safe_send(conn, {"type": MsgType.ERROR.value, "message": "Comando desconhecido"})

        except socket.timeout:
            pass
        except Exception as e:
            self.logger.exception("Erro no cliente %s: %s", addr, e)
        finally:
            self.logger.info("Desconectado: %s", addr)
            with self.clients_lock:
                self._release_player(conn)
                self.clients = [(c, a, p) for (c, a, p) in self.clients if c is not conn]
            try:
                conn.close()
            except Exception:
                pass
            self._push_state()