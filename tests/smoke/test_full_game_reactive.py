"""Full-game smoke: Cooperator agents using reactive Support and
dependency-aware done. Game runs to completion without exceptions.
"""
from foedus.agents.heuristics.cooperator import Cooperator
from foedus.core import GameConfig
from foedus.loop import play_game


def test_full_game_with_cooperators_terminates():
    cfg = GameConfig(num_players=4, max_turns=10, seed=42)
    agents = {p: Cooperator() for p in range(cfg.num_players)}
    final_state = play_game(agents, config=cfg)
    assert final_state.is_terminal()
    # Sanity: no exceptions, support_lapses populated for at least one turn.
    # (Cooperators will lapse some supports as the engine adapts.)
