# grid-sdk-py

Python SDK for [Grid](https://github.com/tot0p/grid) — a Tron-style competitive bot battle platform.

## Installation

```bash
pip install grid-sdk-py==0.3.4
```

## Quick start

```python
import os
from gridbot import Client, Config, StrategyFunc, GameState, Direction
from gridbot.helpers import safe_moves, flood_fill

def my_strategy(state: GameState) -> Direction:
    moves = safe_moves(state)
    if not moves:
        return Direction(state.you.direction)
    # pick the direction with the most open space
    best, best_space = moves[0], -1
    for d in moves:
        nx, ny = d.apply(state.you.x, state.you.y)
        space = flood_fill(nx, ny, state)
        if space > best_space:
            best_space = space
            best = d
    return best

client = Client(Config(
    server_url=os.environ.get("BOT_SERVER", "ws://localhost:8083"),
    token=os.environ["BOT_TOKEN"],
    strategy=StrategyFunc(my_strategy),
))
client.run()
```

```bash
BOT_TOKEN=your-token python bot.py
```

## Architecture

The client uses two threads:

- **WebSocket thread** — receives frames, replies to server PINGs immediately (never blocked).
- **Strategy thread** — reads the latest game state, computes your move, sends the command.

This prevents disconnection when strategy computation takes longer than the server's 30 s pong timeout.

## Key helpers (`gridbot.helpers`)

| Function | Description |
|---|---|
| `safe_moves(state)` | Directions that don't hit a wall or trail |
| `safe_moves_detailed(state)` | Same, with target position + head-on risk |
| `flood_fill(x, y, state)` | Reachable empty cells from (x, y) |
| `voronoi_bfs(mx, my, ox, oy, state)` | Territorial split — (my_cells, opp_cells) |
| `head_on_risk(x, y, state)` | True if an opponent could also move here |
| `find_closest_opponent(state)` | Nearest alive opponent bot |
| `manhattan_distance(x1, y1, x2, y2)` | |
| `wall_count(x, y, state)` | Adjacent non-empty cells (0–4) |

## Strategy interface

```python
from gridbot import Strategy, MatchAware, GameState, Direction, MatchResult

class MyBot(Strategy, MatchAware):
    def on_match_start(self, state: GameState) -> None:
        ...  # called exactly once at the start of every match

    def on_death(self, state: GameState) -> None:
        ...  # called when your bot dies

    def on_win(self, state: GameState) -> None:
        ...  # called when all opponents are eliminated

    def on_match_end(self, result: MatchResult) -> None:
        ...  # called after on_death or on_win, every match

    def move(self, state: GameState) -> Direction:
        ...  # called every turn — must return within 500 ms
```

`on_match_start` is guaranteed to fire exactly once per match — safe to use for per-match state initialization.

## Requirements

- Python 3.10+
- `websocket-client >= 1.7.0`

## Other SDKs

- **Go**: [`grid-sdk-go`](https://github.com/tot0p/grid-sdk-go) — `go get github.com/tot0p/grid-sdk-go@v0.3.0`

## License

MIT
