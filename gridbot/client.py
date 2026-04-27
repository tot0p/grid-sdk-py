import json
import logging
import queue
import threading
from typing import Callable, Optional

import websocket

from .direction import Direction
from .strategy import MatchAware, Strategy
from .types import GameState

logger = logging.getLogger(__name__)

SDK_VERSION = "0.2.0"


class Config:
    """Configuration for the bot client."""

    def __init__(
        self,
        server_url: str,
        token: str,
        strategy: Strategy,
        on_log: Optional[Callable[[str], None]] = None,
    ):
        # e.g. "ws://localhost:8083"
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
    - **WebSocket thread** (``run_forever``): receives frames from the server,
      immediately responds to PING with PONG (handled by websocket-client),
      and drops parsed ``game_state`` messages into a one-item queue.
    - **Strategy thread**: reads the latest game state, computes the move, and
      sends the command back on the same WebSocket.

    Why two threads?
    The game server sends PING frames every ~27 s and expects PONG within 30 s.
    If strategy computation ran inside ``on_message``, it would block the
    WebSocket event loop, preventing PONG from being sent → server disconnects.

    Usage::

        client = Client(Config(
            server_url="ws://localhost:8083",
            token="bot-token",
            strategy=MyStrategy(),
        ))
        client.run()   # blocks; auto-reconnects on disconnect
    """

    def __init__(self, config: Config):
        self._config = config
        self._last_direction = Direction.RIGHT
        self._in_match = False
        self._last_turn = 0
        self._stop_event = threading.Event()
        self._version_mismatch = False
        self._ws: Optional[websocket.WebSocketApp] = None
        self._backoff = 5.0
        self._max_backoff = 60.0

        # One-slot queue: only the *latest* game state matters.
        # If the strategy thread is still computing, the stale state is replaced.
        self._state_q: queue.Queue = queue.Queue(maxsize=1)

        # Strategy runs in its own thread so the WebSocket loop is never blocked.
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

            # No ping_interval here: the *server* manages the ping/pong cycle.
            # websocket-client automatically replies to server PING with PONG
            # as long as the event loop is not blocked — which it won't be
            # because strategy computation runs in a separate thread.
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
    # WebSocket callbacks (all lightweight — no blocking work here)
    # ------------------------------------------------------------------

    def _on_open(self, ws) -> None:
        self._backoff = 5.0  # reset on successful connect
        self._version_mismatch = False
        # Send version handshake immediately — server expects this as first message.
        ws.send(json.dumps({"type": "hello", "version": SDK_VERSION}))
        self._log(f"Connected — sent hello v{SDK_VERSION}")

    def _on_close(self, ws, code, msg) -> None:
        self._ws = None

    def _on_error(self, ws, error) -> None:
        self._log(f"WebSocket error: {error}")

    def _on_message(self, ws, raw: str) -> None:
        """Parse the frame and hand off to the strategy thread immediately."""
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

        if msg_type != "game_state" or not data.get("you"):
            return

        state = GameState.from_dict(data)

        # Deliver the latest state.  If the strategy thread is busy, discard
        # the stale state and replace it with the freshest one.
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
                pass  # rare race; next message will succeed

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

            # Detect new match (turn resets to ≤1)
            if state.turn <= 1 and (state.turn < self._last_turn or not self._in_match):
                self._log("New match started!")
                self._last_direction = Direction(state.you.direction)
                self._in_match = True
                if isinstance(self._config.strategy, MatchAware):
                    self._config.strategy.on_match_start(state)

            self._last_turn = state.turn

            if not state.you.alive:
                if isinstance(self._config.strategy, MatchAware):
                    self._config.strategy.on_death(state)
                self._in_match = False
                continue

            # Detect win: bot alive and all opponents dead
            if self._in_match and len(state.bots) > 1:
                all_opponents_dead = all(
                    not bot.alive
                    for bot in state.bots
                    if bot.bot_id != state.you.bot_id
                )
                if all_opponents_dead:
                    if isinstance(self._config.strategy, MatchAware):
                        self._config.strategy.on_win(state)
                    self._in_match = False
                    continue

            direction = self._config.strategy.move(state)

            cmd = json.dumps({"action": "move", "direction": direction.value})
            try:
                ws.send(cmd)
                self._last_direction = direction
            except Exception as exc:
                self._log(f"Failed to send command: {exc}")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _log(self, msg: str) -> None:
        if self._config.on_log:
            self._config.on_log(msg)
        else:
            logger.info(msg)
