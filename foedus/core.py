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


class Stance(Enum):
    ALLY = "ally"
    NEUTRAL = "neutral"
    HOSTILE = "hostile"


class Phase(Enum):
    NEGOTIATION = "negotiation"
    ORDERS = "orders"


@dataclass(frozen=True)
class Intent:
    """A pre-declaration of what order I will issue for one of my units."""
    unit_id: UnitId
    declared_order: Order


@dataclass(frozen=True)
class Press:
    """One player's structured outbound press for one round.

    `stance` is public; missing entries default to NEUTRAL.
    `intents` is private bilateral; key is the recipient who receives those intents.
    """
    stance: dict[PlayerId, Stance]
    intents: dict[PlayerId, list[Intent]]


@dataclass(frozen=True)
class ChatDraft:
    """What an agent emits when sending chat. Engine fills in turn/sequence/sender."""
    recipients: frozenset[PlayerId] | None  # None = public broadcast
    body: str


@dataclass(frozen=True)
class ChatMessage:
    """Canonical chat record stored in chat_history."""
    turn: int
    sequence: int
    sender: PlayerId
    recipients: frozenset[PlayerId] | None
    body: str


@dataclass(frozen=True)
class BetrayalObservation:
    """End-of-turn signal that someone broke a private intent to me."""
    turn: int
    betrayer: PlayerId
    intent: Intent
    actual_order: Order


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
    peace_threshold: int = 5  # consecutive dislodgement-free turns to trigger
                              # the détente collective-victory; 0 disables.
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
    peace_streak: int = 0  # consecutive turns ending without any dislodgement

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
        active = [p for p in range(self.config.num_players) if p not in self.eliminated]
        if len(active) <= 1:
            return True
        if (self.config.peace_threshold > 0
                and self.peace_streak >= self.config.peace_threshold):
            return True
        if self.turn >= self.config.max_turns:
            return True
        return False

    @property
    def detente_reached(self) -> bool:
        """True iff the game ended via the peaceful collective-victory condition.

        Requires multiple surviving players; a last-standing victory is not détente.
        """
        if self.config.peace_threshold <= 0:
            return False
        if self.peace_streak < self.config.peace_threshold:
            return False
        active = [p for p in range(self.config.num_players) if p not in self.eliminated]
        return len(active) > 1

    @property
    def winner(self) -> PlayerId | None:
        """The single winner, or None if non-terminal, tied, or détente (collective).

        Resolution priority:
        1. Only one active player: last-standing wins.
        2. Détente reached: returns None (use `winners()` for the list).
        3. Otherwise: highest cumulative score; tie at top → None.
        """
        if not self.is_terminal():
            return None
        active = [p for p in range(self.config.num_players) if p not in self.eliminated]
        if len(active) == 1:
            return active[0]
        if self.detente_reached:
            return None
        if not self.scores:
            return None
        max_score = max(self.scores.values())
        top = [p for p, s in self.scores.items() if s == max_score]
        return top[0] if len(top) == 1 else None

    def winners(self) -> list[PlayerId]:
        """All winning players. For solo wins, single element. For détente,
        all surviving players. Empty for non-terminal or full ties.
        """
        if not self.is_terminal():
            return []
        active = sorted(p for p in range(self.config.num_players) if p not in self.eliminated)
        if len(active) == 1:
            return active
        if self.detente_reached:
            return active
        w = self.winner
        return [w] if w is not None else []

    def final_scores(self) -> list[tuple[PlayerId, float]]:
        """Players paired with their cumulative scores, sorted descending."""
        return sorted(self.scores.items(), key=lambda kv: -kv[1])
