import json
import logging
import queue
import threading
from typing import Callable, Optional

import websocket

from .direction import Direction
from .strategy import MatchAware, Strategy
from .types import GameState, MatchResult

logger = logging.getLogger(__name__)

SDK_VERSION = "0.3.0"


class Config:
    """Configuration for the bot client."""

    def __init__(
        self,
        server_url: str,
        token: str,
        strategy: Strategy,
        on_log: Optional[Callable[[str], None]] = None,
    ):
        self.server_url = server_url.rstrip("/")
        self.token = token
        self.strategy = strategy
        self.on_log = on_log


class Client:
    """
    Manages the WebSocket connection to the game server.

    Architecture
    ------------
    Two threads:
    - **WebSocket thread** (``run_forever``): receives frames, immediately
      responds to PING with PONG, dispatches lifecycle events (match_start /
      match_end) inline, and drops game_state messages into a one-item queue.
    - **Strategy thread**: reads the latest game_state, computes the move,
      sends the command back.

    Lifecycle callbacks (on_match_start, on_death, on_win, on_match_end) are
    called from the WebSocket thread and should be fast (logging / counters).
    Move computation (on_move) runs in the strategy thread and may take up
    to ~480 ms without triggering a disconnect.
    """

    def __init__(self, config: Config):
        self._config = config
        self._last_direction = Direction.RIGHT
        self._in_match = False
        self._match_start_turn = 0
        self._last_state: Optional[GameState] = None
        self._stop_event = threading.Event()
        self._version_mismatch = False
        self._ws: Optional[websocket.WebSocketApp] = None
        self._backoff = 5.0
        self._max_backoff = 60.0

        # One-slot queue for game_state messages only.
        # The strategy thread always processes the freshest state.
        self._state_q: queue.Queue = queue.Queue(maxsize=1)

        self._strategy_thread = threading.Thread(
            target=self._strategy_loop,
            daemon=True,
            name="gridbot-strategy",
        )
        self._strategy_thread.start()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Connect to the server and run the game loop.  Blocks until stop()."""
        while not self._stop_event.is_set():
            url = f"{self._config.server_url}/ws/bot?token={self._config.token}"
            self._log(f"Connecting to {self._config.server_url}…")

            ws = websocket.WebSocketApp(
                url,
                on_open=self._on_open,
                on_message=self._on_message,
                on_error=self._on_error,
                on_close=self._on_close,
            )
            self._ws = ws
            ws.run_forever()

            if self._stop_event.is_set():
                break

            self._log(f"Disconnected — reconnecting in {self._backoff:.0f}s")
            self._stop_event.wait(timeout=self._backoff)
            self._backoff = min(self._backoff * 2, self._max_backoff)

        self._log("Client stopped")

    def stop(self) -> None:
        """Stop the client and close the WebSocket connection."""
        self._stop_event.set()
        if self._ws is not None:
            self._ws.close()

    # ------------------------------------------------------------------
    # WebSocket callbacks
    # ------------------------------------------------------------------

    def _on_open(self, ws) -> None:
        self._backoff = 5.0
        self._version_mismatch = False
        ws.send(json.dumps({"type": "hello", "version": SDK_VERSION}))
        self._log(f"Connected — sent hello v{SDK_VERSION}")

    def _on_close(self, ws, code, msg) -> None:
        self._ws = None

    def _on_error(self, ws, error) -> None:
        self._log(f"WebSocket error: {error}")

    def _on_message(self, ws, raw: str) -> None:
        """Dispatch incoming frames.

        Lifecycle events (match_start, match_end) are handled immediately in
        this thread. game_state messages are forwarded to the strategy thread.
        """
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return

        msg_type = data.get("type")

        if msg_type == "hello":
            self._log(f"Handshake OK (server v{data.get('version', '?')})")
            return

        if msg_type == "error":
            code = data.get("code", "")
            self._log(f"Server error [{code}]: {data.get('message', 'unknown')}")
            if code == "version_mismatch":
                self._version_mismatch = True
                self.stop()
            return

        if msg_type == "match_start":
            self._handle_match_start(ws, data)
            return

        if msg_type == "match_end":
            self._handle_match_end(data)
            return

        if msg_type != "game_state" or not data.get("you"):
            return

        state = GameState.from_dict(data)
        self._last_state = state

        # Deliver the latest state to the strategy thread.
        try:
            self._state_q.put_nowait((ws, state))
        except queue.Full:
            try:
                self._state_q.get_nowait()
            except queue.Empty:
                pass
            try:
                self._state_q.put_nowait((ws, state))
            except queue.Full:
                pass

    # ------------------------------------------------------------------
    # Lifecycle handlers (called from WebSocket thread)
    # ------------------------------------------------------------------

    def _handle_match_start(self, ws, data: dict) -> None:
        match_id = data.get("match_id", 0)
        w = data.get("field_width", 0)
        h = data.get("field_height", 0)
        nb = len(data.get("bots", []))
        self._log(f"Match {match_id} starting ({w}×{h}, {nb} bots)")
        self._in_match = True
        self._match_start_turn = 0
        self._last_state = None

    def _handle_match_end(self, data: dict) -> None:
        match_id = data.get("match_id", 0)
        won = data.get("won", False)
        score = data.get("score", 0)
        turns = data.get("turns", 0)
        reason = data.get("reason", "")

        result = MatchResult(
            won=won,
            score=score,
            turns=turns,
            state=self._last_state,
        )

        if won:
            self._log(f"Match {match_id} WON — score {score} in {turns} turns")
            if isinstance(self._config.strategy, MatchAware):
                self._config.strategy.on_win(self._last_state)
        else:
            self._log(f"Match {match_id} LOST — score {score} in {turns} turns (reason: {reason})")
            if isinstance(self._config.strategy, MatchAware):
                self._config.strategy.on_death(self._last_state)

        if isinstance(self._config.strategy, MatchAware):
            self._config.strategy.on_match_end(result)

        self._in_match = False

    # ------------------------------------------------------------------
    # Strategy thread
    # ------------------------------------------------------------------

    def _strategy_loop(self) -> None:
        """Compute moves in a dedicated thread — never blocks the WS loop."""
        while not self._stop_event.is_set():
            try:
                ws, state = self._state_q.get(timeout=1.0)
            except queue.Empty:
                continue

            # Safety net: detect match start from game_state if match_start
            # message was missed (e.g. older server, lost frame).
            if not self._in_match or (state.turn <= 1 and state.turn < self._last_turn_seen()):
                self._log("New match detected from game_state")
                self._last_direction = Direction(state.you.direction)
                self._in_match = True
                self._match_start_turn = state.turn
                if isinstance(self._config.strategy, MatchAware):
                    self._config.strategy.on_match_start(state)
            elif self._in_match and self._match_start_turn == 0:
                # First game_state after a match_start message
                self._match_start_turn = state.turn
                self._last_direction = Direction(state.you.direction)
                if isinstance(self._config.strategy, MatchAware):
                    self._config.strategy.on_match_start(state)

            self._last_state_turn = state.turn

            # If the bot is dead, wait for the match_end message
            if not state.you.alive:
                continue

            direction = self._config.strategy.move(state)

            cmd = json.dumps({"action": "move", "direction": direction.value})
            try:
                ws.send(cmd)
                self._last_direction = direction
            except Exception as exc:
                self._log(f"Failed to send command: {exc}")

    def _last_turn_seen(self) -> int:
        return getattr(self, "_last_state_turn", 0)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _log(self, msg: str) -> None:
        if self._config.on_log:
            self._config.on_log(msg)
        else:
            logger.info(msg)
