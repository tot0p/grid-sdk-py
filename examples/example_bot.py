#!/usr/bin/env python3
"""
Example Grid bot using grid-sdk-py.

Usage:
    BOT_TOKEN=<your-token> python example_bot.py

Or with a custom server:
    BOT_TOKEN=<token> GAME_SERVER=ws://localhost:8083 python example_bot.py

Install the SDK first:
    pip install ../           # from this examples/ directory
    # or
    pip install grid-sdk-py   # from PyPI (when published)
"""
import os

from gridbot import (
    Client,
    Config,
    Direction,
    GameState,
    MatchAware,
    Strategy,
)
from gridbot.helpers import (
    find_closest_opponent,
    flood_fill,
    safe_moves_detailed,
    voronoi_bfs,
    wall_count,
)


class VoronoiBot(Strategy, MatchAware):
    """
    A balanced bot that maximises Voronoi territory while avoiding
    head-on collisions.  Good general-purpose starter strategy.
    """

    def on_match_start(self, state: GameState) -> None:
        print(f"[VoronoiBot] Match started on {state.width}x{state.height} grid")

    def on_death(self, state: GameState) -> None:
        print(f"[VoronoiBot] Died on turn {state.turn} with score {state.you.score}")

    def move(self, state: GameState) -> Direction:
        moves = safe_moves_detailed(state)
        if not moves:
            return Direction(state.you.direction)

        opp = find_closest_opponent(state)
        last_dir = Direction(state.you.direction)

        best = None
        best_score = float("-inf")

        for m in moves:
            if opp:
                my_t, opp_t = voronoi_bfs(m.x, m.y, opp.x, opp.y, state)
            else:
                my_t = flood_fill(m.x, m.y, state)
                opp_t = 0

            walls = wall_count(m.x, m.y, state)
            score = my_t * 2 + (my_t - opp_t)

            if m.head_on_risk:
                score -= 10_000

            # Tiebreak: prefer more walls, then keep current direction
            tiebreak = (walls, m.direction == last_dir)

            if best is None or (score, tiebreak) > (best_score, (0, False)):
                best = m
                best_score = score

        return best.direction


if __name__ == "__main__":
    token = os.environ.get("BOT_TOKEN", "")
    server = os.environ.get("GAME_SERVER", "ws://localhost:8083")

    if not token:
        print("Error: BOT_TOKEN environment variable is required.")
        print("Create a bot at http://localhost:8080 and set BOT_TOKEN=<token>")
        raise SystemExit(1)

    client = Client(Config(
        server_url=server,
        token=token,
        strategy=VoronoiBot(),
    ))

    print(f"Connecting to {server}…")
    client.run()
