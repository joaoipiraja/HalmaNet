"""
Halma com Chat e Multiplayer via Sockets (Servidor/Cliente em um único arquivo)

Refatorado para legibilidade, organização e robustez, com:
- DESISTIR (resign)
- REINÍCIO POR CONSENSO (ambos os jogadores precisam pedir reset)

Uso:
  # Terminal 1 - iniciar servidor (porta 50007 por padrão)
  python halma_net_refatorado.py --server [--host 0.0.0.0] [--port 50007]

  # Terminal 2 - cliente Jogador 1
  python halma_net_refatorado.py --client --host 127.0.0.1 --port 50007

  # Terminal 3 - cliente Jogador 2
  python halma_net_refatorado.py --client --host 127.0.0.1 --port 50007

Notas:
- Máximo de 2 jogadores + espectadores ilimitados.
- O servidor mantém o estado do jogo e valida os movimentos.
- O chat é distribuído para todos os clientes.
- Protocolo: JSON por linha ("\n"). Eventos: join, state, chat, move, endjump, reset, resign, ping, pong, error.
- Regras de salto: se houver saltos sequenciais possíveis com a MESMA peça, o turno fica
  "travado" (jump-lock) nessa peça até o esgotamento dos saltos ou o cliente enviar ENDJUMP (ESPAÇO).
- Desistir: jogador pressiona D → oponente vence por desistência.
- Reset: tecla R registra voto de reinício; a partida só reinicia quando **os dois jogadores** votarem.

Atalhos:
- D = desistir
- R = solicitar reinício (consenso dos dois)
- Espaço = encerrar cadeia de saltos
- Enter = enviar chat
- Esc = sair
"""
from __future__ import annotations

import argparse
import json
import logging
import socket
import threading
import time
from collections import deque
from dataclasses import dataclass
from enum import Enum, IntEnum
from typing import Deque, Dict, Iterable, List, Optional, Sequence, Set, Tuple

# ==============================
# Configuração comum (constantes de UI e jogo)
# ==============================
TILE: int = 40
N: int = 16
BOARD_W, BOARD_H = N * TILE, N * TILE
CHAT_W = 300
W, H = BOARD_W + CHAT_W, BOARD_H

# Cores
GRID_COLOR = (40, 40, 40)
BG_COLOR = (20, 20, 24)
SEL_COLOR = (255, 215, 0)
VALID_SIMPLE = (120, 200, 255)
VALID_JUMP = (120, 255, 160)
CAMP_A_COLOR = (60, 60, 120)
CAMP_B_COLOR = (120, 60, 60)
TEXT_COLOR = (230, 230, 230)
MUTED_TEXT = (170, 170, 170)
PANEL_BG = (28, 30, 36)
PANEL_ACCENT = (48, 50, 58)
INPUT_BG = (18, 18, 22)
P1_COLOR = (70, 170, 255)
P2_COLOR = (255, 110, 110)

HEARTBEAT_SECONDS: int = 10
MAX_CHAT_HISTORY: int = 200

# ==============================
# Protocolo e entidades
# ==============================
class Cell(IntEnum):
    EMPTY = 0
    P1 = 1
    P2 = 2


class MsgType(str, Enum):
    JOIN = "join"
    STATE = "state"
    CHAT = "chat"
    MOVE = "move"
    ENDJUMP = "endjump"
    RESET = "reset"          # agora exige consenso dos dois jogadores
    RESIGN = "resign"
    PING = "ping"
    PONG = "pong"
    ERROR = "error"
    DISCONNECT = "disconnect"  # uso interno do cliente


DIRS: Tuple[Tuple[int, int], ...] = (
    (-1, 0), (1, 0), (0, -1), (0, 1),
    (-1, -1), (-1, 1), (1, -1), (1, 1),
)


# ==============================
# Utilidades de tabuleiro
# ==============================
def camp_cells_top_left() -> Set[Tuple[int, int]]:
    cells: Set[Tuple[int, int]] = set()
    for r in range(5):
        for c in range(5 - r):
            cells.add((r, c))
    return cells


def camp_cells_bottom_right() -> Set[Tuple[int, int]]:
    tl = camp_cells_top_left()
    return {(N - 1 - r, N - 1 - c) for r, c in tl}


CAMP_A = camp_cells_top_left()
CAMP_B = camp_cells_bottom_right()


class Board:
    def __init__(self) -> None:
        self.grid: List[List[int]] = [[Cell.EMPTY for _ in range(N)] for _ in range(N)]
        for r, c in CAMP_A:
            self.grid[r][c] = Cell.P1
        for r, c in CAMP_B:
            self.grid[r][c] = Cell.P2

    # --- acesso ---
    @staticmethod
    def deserialize(g: List[List[int]]) -> "Board":
        b = Board()
        b.grid = g
        return b

    def serialize(self) -> List[List[int]]:
        return self.grid

    def inside(self, r: int, c: int) -> bool:
        return 0 <= r < N and 0 <= c < N

    def cell(self, r: int, c: int) -> int:
        return self.grid[r][c]

    def set_cell(self, r: int, c: int, v: int) -> None:
        self.grid[r][c] = v

    def is_victory(self, player: int) -> bool:
        target = CAMP_B if player == Cell.P1 else CAMP_A
        return all(self.grid[r][c] == player for (r, c) in target)


# ---------- Movimento ----------
def neighbors(r: int, c: int) -> Iterable[Tuple[int, int]]:
    for dr, dc in DIRS:
        yield r + dr, c + dc


def compute_moves(board: Board, start: Tuple[int, int]) -> Tuple[Set[Tuple[int, int]], Set[Tuple[int, int]]]:
    """Retorna (simples, saltos) a partir de `start`. BFS para saltos múltiplos."""
    r0, c0 = start
    simple: Set[Tuple[int, int]] = set()
    for r1, c1 in neighbors(r0, c0):
        if board.inside(r1, c1) and board.cell(r1, c1) == Cell.EMPTY:
            simple.add((r1, c1))

    jump_dest: Set[Tuple[int, int]] = set()
    q: Deque[Tuple[int, int]] = deque([start])
    visited: Set[Tuple[int, int]] = {start}

    while q:
        r, c = q.popleft()
        for dr, dc in DIRS:
            r_mid, c_mid = r + dr, c + dc
            r2, c2 = r + 2 * dr, c + 2 * dc
            if not board.inside(r2, c2):
                continue
            if board.inside(r_mid, c_mid) and board.cell(r_mid, c_mid) in (Cell.P1, Cell.P2) and board.cell(r2, c2) == Cell.EMPTY:
                if (r2, c2) not in visited:
                    visited.add((r2, c2))
                    jump_dest.add((r2, c2))
                    q.append((r2, c2))

    return simple, jump_dest


# ==============================
# Servidor
# ==============================
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

    # ----- ciclo de vida -----
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
            self.reset_votes: Set[int] = set()  # votos de reset pendentes (1 e/ou 2)

    # ----- rede -----
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
                # votos atuais de reset (para UI do cliente)
                "reset_votes": {"p1": Cell.P1 in self.reset_votes, "p2": Cell.P2 in self.reset_votes},
            }
        self._broadcast(state)

    # ----- jogadores -----
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
            # se alguém saiu, limpar voto de reset desse jogador
            self.reset_votes = {p for p in self.reset_votes if self.player_slots.get(p) is not None}

    # ----- regras -----
    def _apply_move(self, pid: int, src: Tuple[int, int], dst: Tuple[int, int]) -> bool:
        """Aplica movimento já validado. Retorna se o turno foi finalizado."""
        r0, c0 = src
        self.board.set_cell(r0, c0, Cell.EMPTY)
        self.board.set_cell(dst[0], dst[1], pid)

        # Vitória?
        if self.board.is_victory(pid):
            self.winner = pid
            self.jump_lock = None
            return True

        # Saltos seguintes?
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

            # jump-lock: só pode saltar com a mesma peça
            if self.jump_lock and self.jump_lock.player == pid:
                if src != tuple(self.jump_lock.pos):
                    return False, "Você deve continuar a cadeia de saltos com a mesma peça"
                if dst not in jumps:
                    return False, "Apenas saltos são permitidos durante a cadeia"
                self._apply_move(pid, src, dst)
                return True, None

            # fluxo normal
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
            # ao finalizar por desistência, votos de reset não fazem sentido
            self.reset_votes.clear()
            return True, None

    def _request_reset(self, pid: int) -> Tuple[bool, Optional[str], bool]:
        """
        Registra o voto de reset do jogador `pid`.
        Retorna (ok, err, should_reset_now).
        """
        with self.state_lock:
            if pid not in (Cell.P1, Cell.P2):
                return False, "Apenas jogadores podem solicitar reinício", False

            # registra voto
            if pid in self.reset_votes:
                # já tinha votado; não duplicar mensagens
                return True, None, False

            self.reset_votes.add(pid)
            self.chat_log.append({"player": 0, "text": f"Jogador {1 if pid == Cell.P1 else 2} solicitou reinício."})

            # se os dois votaram, reinicia
            if Cell.P1 in self.reset_votes and Cell.P2 in self.reset_votes:
                self.chat_log.append({"player": 0, "text": "Partida será reiniciada por consenso dos dois jogadores."})
                return True, None, True

            return True, None, False

    # ----- loop do cliente -----
    def _client_thread(self, conn: socket.socket, addr: Tuple[str, int]) -> None:
        buf = b""
        with self.clients_lock:
            pid = self._assign_player(conn)
            self.clients.append((conn, addr, pid))
        # boas-vindas
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
                        # qualquer movimento cancela votos de reset (situação mudou)
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
                            # efetiva o reset por consenso
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


# ==============================
# Cliente (Pygame)
# ==============================
# Import lazy: só importar pygame quando em modo cliente
import pygame  # type: ignore


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


class GameClient:
    def __init__(self, host: str = "127.0.0.1", port: int = 50007) -> None:
        pygame.init()
        pygame.display.set_caption("Halma Online - Cliente")
        self.screen = pygame.display.set_mode((W, H))
        self.font = pygame.font.SysFont("arial", 16)
        self.font_small = pygame.font.SysFont("arial", 14)
        self.big_font = pygame.font.SysFont("arial", 20, bold=True)
        self.clock = pygame.time.Clock()
        self.client = NetClient(host, port)

        # Estado de jogo
        self.player_id: Optional[int] = None
        self.board = Board()
        self.turn: int = Cell.P1
        self.winner: Optional[int] = None
        self.chat_messages: List[Dict[str, object]] = []
        self.players_present: Dict[str, bool] = {"p1": False, "p2": False}
        self.jump_lock: Optional[Dict[str, object]] = None
        self.reset_votes: Dict[str, bool] = {"p1": False, "p2": False}

        # UI
        self.selected: Optional[Tuple[int, int]] = None
        self.valid_simple: Set[Tuple[int, int]] = set()
        self.valid_jump: Set[Tuple[int, int]] = set()
        self.current_input: str = ""
        self.chat_scroll: int = 0
        self.status_msg: str = "Conectando..."

    # ---------- Conversões ----------
    def board_to_screen(self, r: int, c: int) -> Tuple[int, int]:
        return c * TILE + TILE // 2, r * TILE + TILE // 2

    def screen_to_board(self, x: int, y: int) -> Optional[Tuple[int, int]]:
        if x >= BOARD_W or y >= BOARD_H:
            return None
        r, c = y // TILE, x // TILE
        return int(r), int(c)

    def wrap_text(self, text: str, max_width: int, font: pygame.font.Font) -> List[str]:
        words = text.split(" ")
        lines: List[str] = []
        cur = ""
        for w in words:
            piece = (cur + (" " if cur else "") + w)
            width, _ = font.size(piece)
            if width <= max_width:
                cur = piece
            else:
                if cur:
                    lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        return lines

    # ---------- Desenho ----------
    def draw_sidebar(self) -> None:
        x0 = BOARD_W
        pygame.draw.rect(self.screen, PANEL_BG, (x0, 0, CHAT_W, H))
        header_h = 56
        pygame.draw.rect(self.screen, PANEL_ACCENT, (x0, 0, CHAT_W, header_h))

        pid_name = {Cell.P1: "Jogador 1", Cell.P2: "Jogador 2", None: "Espectador"}[self.player_id]
        name_color = P1_COLOR if self.player_id == Cell.P1 else (P2_COLOR if self.player_id == Cell.P2 else TEXT_COLOR)
        hdr = self.big_font.render(f"Você: {pid_name}", True, name_color)
        self.screen.blit(hdr, (x0 + 12, 8))

        turn_text = "Vez: J1" if self.turn == Cell.P1 else "Vez: J2"
        tcolor = P1_COLOR if self.turn == Cell.P1 else P2_COLOR
        self.screen.blit(self.font.render(turn_text, True, tcolor), (x0 + 12, 30))

        p1s = "online" if self.players_present.get("p1") else "aguardando"
        p2s = "online" if self.players_present.get("p2") else "aguardando"
        self.screen.blit(self.font_small.render(f"J1: {p1s}", True, MUTED_TEXT), (x0 + 180, 10))
        self.screen.blit(self.font_small.render(f"J2: {p2s}", True, MUTED_TEXT), (x0 + 180, 26))

        y_hint = 40
        if self.jump_lock and self.jump_lock.get("player") == self.player_id:
            self.screen.blit(self.font_small.render("Cadeia de saltos ativa: ESPAÇO encerra", True, MUTED_TEXT), (x0 + 12, y_hint))
            y_hint += 14

        # Mostrar status do reset por consenso
        rv_p1, rv_p2 = self.reset_votes.get("p1", False), self.reset_votes.get("p2", False)
        if rv_p1 or rv_p2:
            s = "Pedidos de reset: "
            s += ("J1✓ " if rv_p1 else "J1… ") + ("J2✓" if rv_p2 else "J2…")
            self.screen.blit(self.font_small.render(s, True, MUTED_TEXT), (x0 + 12, y_hint))
            y_hint += 14

        self.screen.blit(self.font_small.render("D: desistir  •  R: solicitar reinício", True, MUTED_TEXT), (x0 + 12, y_hint))

        input_h = 36
        pad = 10
        chat_top = header_h + 26
        chat_h = H - chat_top - input_h - pad * 2
        messages_rect = pygame.Rect(x0 + pad, chat_top, CHAT_W - pad * 2, chat_h)
        pygame.draw.rect(self.screen, (32, 34, 40), messages_rect, border_radius=8)

        lines: List[Tuple[str, str, Optional[int]]] = []
        for m in self.chat_messages[-300:]:
            player = m.get("player")
            name = "Jogador 1" if player == Cell.P1 else ("Jogador 2" if player == Cell.P2 else "Sistema")
            label = f"{name}: "
            label_w, _ = self.font_small.size(label)
            max_text_w = messages_rect.width - 8 - label_w
            wrapped = self.wrap_text(str(m.get("text", "")), max_text_w, self.font_small)
            if wrapped:
                lines.append((label, wrapped[0], int(player) if isinstance(player, int) else None))
                for cont in wrapped[1:]:
                    lines.append(("", cont, int(player) if isinstance(player, int) else None))
            else:
                lines.append((label, "", int(player) if isinstance(player, int) else None))

        line_h = 18
        total_h = len(lines) * line_h
        max_scroll = max(0, total_h - (chat_h - 8))
        self.chat_scroll = max(0, min(self.chat_scroll, max_scroll))

        clip_prev = self.screen.get_clip()
        self.screen.set_clip(messages_rect)
        y = chat_top + 4 - self.chat_scroll
        for label, text, player in lines:
            color = P1_COLOR if player == Cell.P1 else (P2_COLOR if player == Cell.P2 else MUTED_TEXT)
            if label:
                lbl = self.font_small.render(label, True, color)
                self.screen.blit(lbl, (x0 + pad + 6, y))
                label_w, _ = self.font_small.size(label)
                txt = self.font_small.render(text, True, TEXT_COLOR)
                self.screen.blit(txt, (x0 + pad + 6 + label_w, y))
            else:
                txt = self.font_small.render(text, True, TEXT_COLOR)
                self.screen.blit(txt, (x0 + pad + 6, y))
            y += line_h
        self.screen.set_clip(clip_prev)

        input_rect = pygame.Rect(x0 + pad, H - pad - input_h, CHAT_W - pad * 2, input_h)
        pygame.draw.rect(self.screen, INPUT_BG, input_rect, border_radius=8)
        pygame.draw.rect(self.screen, PANEL_ACCENT, input_rect, 1, border_radius=8)
        prefix = "> "
        prefix_surf = self.font.render(prefix, True, MUTED_TEXT)
        self.screen.blit(prefix_surf, (input_rect.x + 8, input_rect.y + 8))
        txt = self.font.render(self.current_input, True, TEXT_COLOR)
        self.screen.blit(txt, (input_rect.x + 8 + prefix_surf.get_width(), input_rect.y + 8))

        if self.status_msg:
            self.screen.blit(self.font_small.render(self.status_msg, True, MUTED_TEXT), (x0 + 12, H - input_h - pad - 18))

    def draw_winner_overlay(self) -> None:
        if not self.winner:
            return
        overlay = pygame.Surface((BOARD_W, BOARD_H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 140))
        self.screen.blit(overlay, (0, 0))

        winner_num = 1 if self.winner == Cell.P1 else 2

        # Detecta vitória por desistência via última mensagem de sistema
        last_text = (self.chat_messages[-1].get("text") if self.chat_messages else "") or ""
        by_resign = isinstance(last_text, str) and "desistiu" in last_text.lower()

        title_text = f"Vitória do Jogador {winner_num}!" + (" (por desistência)" if by_resign else "")
        title = self.big_font.render(title_text, True, (255, 255, 255))
        tip = self.font.render("Pressione R para solicitar reinício (ambos devem aceitar)", True, (230, 230, 230))

        box_w = max(title.get_width(), tip.get_width()) + 40
        box_h = title.get_height() + tip.get_height() + 28
        box_x = (BOARD_W - box_w) // 2
        box_y = (BOARD_H - box_h) // 2
        pygame.draw.rect(self.screen, (28, 30, 36), (box_x, box_y, box_w, box_h), border_radius=12)
        pygame.draw.rect(self.screen, (48, 50, 58), (box_x, box_y, box_w, box_h), 2, border_radius=12)

        accent = P1_COLOR if self.winner == Cell.P1 else P2_COLOR
        pygame.draw.rect(self.screen, accent, (box_x, box_y, box_w, 6), border_radius=12)

        self.screen.blit(title, (box_x + (box_w - title.get_width()) // 2, box_y + 10))
        self.screen.blit(tip, (box_x + (box_w - tip.get_width()) // 2, box_y + 14 + title.get_height()))

    def draw_board(self) -> None:
        self.screen.fill(BG_COLOR)
        for r, c in CAMP_A:
            pygame.draw.rect(self.screen, CAMP_A_COLOR, (c * TILE, r * TILE, TILE, TILE))
        for r, c in CAMP_B:
            pygame.draw.rect(self.screen, CAMP_B_COLOR, (c * TILE, r * TILE, TILE, TILE))

        for i in range(N + 1):
            pygame.draw.line(self.screen, GRID_COLOR, (0, i * TILE), (BOARD_W, i * TILE), 1)
        for i in range(N + 1):
            pygame.draw.line(self.screen, GRID_COLOR, (i * TILE, 0), (i * TILE, BOARD_H), 1)

        for r, c in self.valid_simple:
            pygame.draw.rect(self.screen, VALID_SIMPLE, (c * TILE + 8, r * TILE + 8, TILE - 16, TILE - 16), border_radius=6)
        for r, c in self.valid_jump:
            pygame.draw.rect(self.screen, VALID_JUMP, (c * TILE + 4, r * TILE + 4, TILE - 8, TILE - 8), 2, border_radius=8)

        for r in range(N):
            for c in range(N):
                v = self.board.cell(r, c)
                if v != Cell.EMPTY:
                    color = P1_COLOR if v == Cell.P1 else P2_COLOR
                    x, y = self.board_to_screen(r, c)
                    pygame.draw.circle(self.screen, color, (x, y), TILE // 2 - 4)

        if self.selected:
            r, c = self.selected
            pygame.draw.rect(self.screen, SEL_COLOR, (c * TILE + 2, r * TILE + 2, TILE - 4, TILE - 4), 3, border_radius=8)

        # Overlay de vitória no tabuleiro
        self.draw_winner_overlay()

        # Sidebar
        self.draw_sidebar()

    # ---------- Entrada local ----------
    def try_select_or_move(self, pos: Tuple[int, int]) -> None:
        if self.winner:
            return
        if self.player_id is None:
            self.status_msg = "Você é espectador. Aguarde vaga."
            return
        if self.turn != self.player_id:
            self.status_msg = "Aguarde sua vez."
            return

        cell = self.screen_to_board(*pos)
        if cell is None:
            return
        r, c = cell

        # jump-lock
        if self.jump_lock and self.jump_lock.get("player") == self.player_id:
            lock_pos = tuple(self.jump_lock.get("pos", []))
            if self.selected is None:
                if (r, c) == lock_pos:
                    self.selected = lock_pos
                    _, self.valid_jump = compute_moves(self.board, self.selected)
                    self.valid_simple = set()
                else:
                    self.status_msg = "Continue a cadeia com a peça destacada ou ESPAÇO para encerrar."
            else:
                dest = (r, c)
                if dest in self.valid_jump:
                    self.client.send({"type": MsgType.MOVE.value, "src": list(self.selected), "dst": list(dest)})
                elif dest == self.selected:
                    self.selected = None
                    self.valid_jump = set()
                else:
                    self.status_msg = "Apenas saltos são permitidos."
            return

        # fluxo normal
        if self.selected is None:
            if self.board.cell(r, c) == self.player_id:
                self.selected = (r, c)
                self.valid_simple, self.valid_jump = compute_moves(self.board, self.selected)
            else:
                return
        else:
            dest = (r, c)
            if dest == self.selected:
                self.selected = None
                self.valid_simple, self.valid_jump = set(), set()
                return
            if dest in self.valid_simple or dest in self.valid_jump:
                self.client.send({"type": MsgType.MOVE.value, "src": list(self.selected), "dst": list(dest)})
            else:
                if self.board.cell(r, c) == self.player_id:
                    self.selected = (r, c)
                    self.valid_simple, self.valid_jump = compute_moves(self.board, self.selected)

    def post_chat(self) -> None:
        text = self.current_input.strip()
        if text:
            self.client.send({"type": MsgType.CHAT.value, "text": text})
            self.current_input = ""

    def handle_key(self, event: pygame.event.Event) -> None:
        if event.key == pygame.K_RETURN:
            self.post_chat()
        elif event.key == pygame.K_BACKSPACE:
            self.current_input = self.current_input[:-1]
        elif event.key == pygame.K_r:
            # Solicita reinício (voto). Status será atualizado quando o STATE vier.
            if self.player_id in (Cell.P1, Cell.P2):
                self.client.send({"type": MsgType.RESET.value})
            else:
                self.status_msg = "Somente jogadores podem solicitar reinício."
        elif event.key == pygame.K_SPACE:
            if self.jump_lock and self.jump_lock.get("player") == self.player_id:
                self.client.send({"type": MsgType.ENDJUMP.value})
        elif event.key == pygame.K_d:  # desistir
            if self.player_id in (Cell.P1, Cell.P2) and not self.winner:
                self.client.send({"type": MsgType.RESIGN.value})
        else:
            if event.unicode and event.unicode.isprintable():
                self.current_input += event.unicode

    def handle_mouse_wheel(self, event: pygame.event.Event) -> None:
        mx, _ = pygame.mouse.get_pos()
        if mx >= BOARD_W:
            self.chat_scroll = max(0, self.chat_scroll - event.y * 24)

    # ---------- Rede -> UI ----------
    def on_message(self, msg: Dict[str, object]) -> None:
        t = msg.get("type")
        if t == MsgType.JOIN.value:
            self.player_id = msg.get("player")  # type: ignore[assignment]
            self.status_msg = (
                "Conectado. Aguarde outro jogador." if self.player_id in (Cell.P1, Cell.P2) else "Sala cheia (espectador)."
            )
        elif t == MsgType.STATE.value:
            self.board = Board.deserialize(msg.get("board"))  # type: ignore[arg-type]
            self.turn = int(msg.get("turn"))
            self.winner = msg.get("winner")  # type: ignore[assignment]
            self.chat_messages = msg.get("chat", [])  # type: ignore[assignment]
            self.players_present = msg.get("players", self.players_present)  # type: ignore[assignment]
            self.jump_lock = msg.get("jump_lock")  # type: ignore[assignment]
            self.reset_votes = msg.get("reset_votes", self.reset_votes)  # type: ignore[assignment]

            # status de reset por consenso (mensagem amigável)
            if self.player_id in (Cell.P1, Cell.P2):
                mine = "p1" if self.player_id == Cell.P1 else "p2"
                other = "p2" if mine == "p1" else "p1"
                if self.reset_votes.get(mine) and not self.reset_votes.get(other):
                    self.status_msg = "Pedido de reinício enviado. Aguardando o outro jogador…"
                elif self.reset_votes.get(mine) and self.reset_votes.get(other):
                    self.status_msg = "Partida reiniciada (consenso)."
                else:
                    # só atualiza em vazio para não apagar outros avisos úteis
                    if not self.winner:
                        self.status_msg = ""

            if self.jump_lock and self.jump_lock.get("player") == self.player_id:
                lock_pos = tuple(self.jump_lock.get("pos", []))
                self.selected = lock_pos
                _, self.valid_jump = compute_moves(self.board, self.selected)
                self.valid_simple = set()
                self.status_msg = "Cadeia de saltos ativa. Use ESPAÇO para encerrar."
            else:
                if self.selected:
                    if self.board.cell(self.selected[0], self.selected[1]) != (self.player_id or 0):
                        self.selected = None
                        self.valid_simple, self.valid_jump = set(), set()
                    else:
                        self.valid_simple, self.valid_jump = compute_moves(self.board, self.selected)
                if self.winner:
                    self.status_msg = f"Vitória do Jogador {1 if self.winner == Cell.P1 else 2}"

        elif t == MsgType.CHAT.value:
            self.chat_messages.append({"player": msg.get("player"), "text": msg.get("text", "")})
        elif t == MsgType.ERROR.value:
            self.status_msg = f"Erro: {msg.get('message')}"
        elif t == MsgType.DISCONNECT.value:
            self.status_msg = "Desconectado do servidor"
        elif t == MsgType.PONG.value:
            pass

    def run(self) -> None:
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                    else:
                        self.handle_key(event)
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    self.try_select_or_move(event.pos)  # type: ignore[arg-type]
                elif event.type == pygame.MOUSEWHEEL:
                    self.handle_mouse_wheel(event)

            for msg in self.client.poll():
                self.on_message(msg)

            self.draw_board()
            pygame.display.flip()
            self.clock.tick(60)
        pygame.quit()


# ==============================
# Main
# ==============================
def main() -> None:
    parser = argparse.ArgumentParser(description="Halma com sockets")
    parser.add_argument("--server", action="store_true", help="Executar como servidor")
    parser.add_argument("--client", action="store_true", help="Executar como cliente")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=50007)
    args = parser.parse_args()

    if args.server == args.client:
        print("Escolha exatamente um modo: --server ou --client")
        raise SystemExit(1)

    if args.server:
        logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s")
        HalmaServer(args.host, args.port).start()
    else:
        GameClient(args.host, args.port).run()


if __name__ == "__main__":
    main()
