from dataclasses import dataclass
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from .direction import Direction


@dataclass
class Bot:
    bot_id: int
    bot_name: str
    x: int
    y: int
    direction: str
    alive: bool
    score: int
    color: str

    @classmethod
    def from_dict(cls, d: dict) -> "Bot":
        return cls(
            bot_id=d["bot_id"],
            bot_name=d["bot_name"],
            x=d["x"],
            y=d["y"],
            direction=d["direction"],
            alive=d["alive"],
            score=d["score"],
            color=d.get("color", ""),
        )


@dataclass
class GameState:
    type: str
    turn: int
    width: int
    height: int
    you: Optional[Bot]
    bots: List[Bot]
    grid: List[List[int]]

    @classmethod
    def from_dict(cls, d: dict) -> "GameState":
        you = Bot.from_dict(d["you"]) if d.get("you") else None
        bots = [Bot.from_dict(b) for b in d.get("bots", [])]
        return cls(
            type=d["type"],
            turn=d["turn"],
            width=d["width"],
            height=d["height"],
            you=you,
            bots=bots,
            grid=d["grid"],
        )


@dataclass
class Move:
    direction: "Direction"
    x: int
    y: int
    head_on_risk: bool


@dataclass
class MatchResult:
    """Outcome of a completed match, passed to on_match_end."""
    won: bool        # True if you survived; False if you died
    score: int       # your final score (trail length)
    turns: int       # number of turns the match lasted
    state: GameState # final game state


@dataclass
class Position:
    x: int
    y: int
