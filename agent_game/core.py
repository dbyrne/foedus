"""Core types and data structures."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TypeAlias

PlayerId: TypeAlias = int
NodeId: TypeAlias = int
UnitId: TypeAlias = int


class NodeType(Enum):
    PLAIN = "plain"
    SUPPLY = "supply"
    HOME = "home"


@dataclass(frozen=True)
class Hold:
    pass


@dataclass(frozen=True)
class Move:
    dest: NodeId


@dataclass(frozen=True)
class SupportHold:
    target: UnitId


@dataclass(frozen=True)
class SupportMove:
    target: UnitId
    target_dest: NodeId


Order: TypeAlias = Hold | Move | SupportHold | SupportMove


@dataclass(frozen=True)
class Unit:
    id: UnitId
    owner: PlayerId
    location: NodeId


@dataclass(frozen=True)
class Map:
    """Static graph + node metadata. Same across an entire game."""
    coords: dict[NodeId, tuple[int, int]]   # node -> (q, r) hex axial
    edges: dict[NodeId, frozenset[NodeId]]  # adjacency
    node_types: dict[NodeId, NodeType]
    home_assignments: dict[NodeId, PlayerId]  # node -> player whose home it is

    @property
    def nodes(self) -> list[NodeId]:
        return sorted(self.coords.keys())

    def neighbors(self, n: NodeId) -> frozenset[NodeId]:
        return self.edges.get(n, frozenset())

    def is_adjacent(self, a: NodeId, b: NodeId) -> bool:
        return b in self.edges.get(a, frozenset())

    def is_supply(self, n: NodeId) -> bool:
        return self.node_types[n] in (NodeType.SUPPLY, NodeType.HOME)


@dataclass
class GameConfig:
    num_players: int = 4
    max_turns: int = 25
    fog_radius: int = 1
    build_period: int = 3  # build phase every N turns
    seed: int | None = None


@dataclass
class GameState:
    """Full (omniscient) game state. Use fog filtering for per-player views."""
    turn: int
    map: Map
    units: dict[UnitId, Unit]
    ownership: dict[NodeId, PlayerId | None]
    scores: dict[PlayerId, float]
    eliminated: set[PlayerId]
    next_unit_id: UnitId
    config: GameConfig
    log: list[str] = field(default_factory=list)

    def units_of(self, player: PlayerId) -> list[Unit]:
        return [u for u in self.units.values() if u.owner == player]

    def unit_at(self, node: NodeId) -> Unit | None:
        for u in self.units.values():
            if u.location == node:
                return u
        return None

    def supply_count(self, player: PlayerId) -> int:
        return sum(
            1
            for n, t in self.map.node_types.items()
            if t in (NodeType.SUPPLY, NodeType.HOME)
            and self.ownership.get(n) == player
        )

    def is_active(self, player: PlayerId) -> bool:
        return player not in self.eliminated

    def is_terminal(self) -> bool:
        if self.turn >= self.config.max_turns:
            return True
        active = [p for p in range(self.config.num_players) if p not in self.eliminated]
        return len(active) <= 1

    @property
    def winner(self) -> PlayerId | None:
        """The single winner, or None if game is non-terminal or scores tie.

        - Last player standing wins regardless of score.
        - Otherwise highest cumulative score wins.
        - Returns None on a tie at the top.
        """
        if not self.is_terminal():
            return None
        active = [p for p in range(self.config.num_players) if p not in self.eliminated]
        if len(active) == 1:
            return active[0]
        if not self.scores:
            return None
        max_score = max(self.scores.values())
        winners = [p for p, s in self.scores.items() if s == max_score]
        return winners[0] if len(winners) == 1 else None

    def final_scores(self) -> list[tuple[PlayerId, float]]:
        """Players paired with their cumulative scores, sorted descending."""
        return sorted(self.scores.items(), key=lambda kv: -kv[1])
