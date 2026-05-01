"""Investigate Patron's +15.9 mean-score jump from baseline to post-redesign pool."""
import ast
import json
import statistics
from collections import defaultdict


def load(path):
    out = []
    for line in open(path):
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def parse_list(s):
    return ast.literal_eval(s) if isinstance(s, str) else s


def patron_seat(rec):
    agents = parse_list(rec["agents"])
    for i, a in enumerate(agents):
        if a == "Patron":
            return i
    return None


def analyze(path, label):
    games = load(path)
    print(f"\n=== {label} ({len(games)} games) ===")

    patron_games = []
    for rec in games:
        seat = patron_seat(rec)
        if seat is None:
            continue
        agents = parse_list(rec["agents"])
        scores = parse_list(rec["final_scores"])
        score_per_turn = json.loads(rec["score_per_turn"]) if isinstance(rec["score_per_turn"], str) else rec["score_per_turn"]
        patron_games.append({
            "agents": agents,
            "scores": scores,
            "patron_seat": seat,
            "patron_score": scores[seat],
            "score_per_turn": score_per_turn,
            "total_turns": rec["total_turns"],
            "winners": parse_list(rec["winners"]),
            "aid_spends_count": rec["aid_spends_count"],
            "leverage_bonuses_fired": rec["leverage_bonuses_fired"],
            "alliance_bonuses_fired": rec["alliance_bonuses_fired"],
            "combat_rewards_fired": rec["combat_rewards_fired"],
            "betrayals_observed": rec["betrayals_observed"],
            "betrayal_count_per_player": parse_list(rec["betrayal_count_per_player"]),
        })

    print(f"Patron present in {len(patron_games)} games")

    # 1. Patron mean and win rate
    patron_scores = [g["patron_score"] for g in patron_games]
    print(f"Patron mean: {statistics.mean(patron_scores):.2f}, "
          f"median: {statistics.median(patron_scores):.1f}, "
          f"stdev: {statistics.stdev(patron_scores):.2f}")
    wins = sum(1 for g in patron_games if g["patron_seat"] in g["winners"])
    print(f"Patron win rate: {wins}/{len(patron_games)} = {wins/len(patron_games)*100:.1f}%")

    # 2. Patron's score by which agents are co-occupants
    print("\nPatron mean score when co-occupant present (n>=20 only):")
    co_occupant_scores = defaultdict(list)
    for g in patron_games:
        for i, a in enumerate(g["agents"]):
            if i != g["patron_seat"]:
                co_occupant_scores[a].append(g["patron_score"])
    rows = []
    for opp, scores in co_occupant_scores.items():
        if len(scores) >= 20:
            rows.append((opp, len(scores), statistics.mean(scores)))
    rows.sort(key=lambda r: -r[2])
    for opp, n, mean in rows:
        print(f"  vs {opp:25s} n={n:3d} → patron_mean={mean:.2f}")

    # 3. Patron's score trajectory
    avg_traj = []
    for turn_str in sorted(patron_games[0]["score_per_turn"].keys(), key=int):
        turn_scores = [g["score_per_turn"][turn_str][g["patron_seat"]]
                       for g in patron_games
                       if turn_str in g["score_per_turn"]
                       and len(g["score_per_turn"][turn_str]) > g["patron_seat"]]
        if turn_scores:
            avg_traj.append((int(turn_str), statistics.mean(turn_scores)))
    print("\nPatron mean score trajectory (selected turns):")
    for t, m in avg_traj:
        if t in (1, 5, 10, 15, 20, 25):
            print(f"  turn {t:2d}: {m:.2f}")

    # 4. Per-game stats relative to opponents
    print("\nPer-game leverage_bonuses_fired (when Patron present):")
    lev_fires = [g["leverage_bonuses_fired"] for g in patron_games]
    print(f"  mean: {statistics.mean(lev_fires):.2f}, median: {statistics.median(lev_fires):.1f}")

    print("Aid spends per game (when Patron present):")
    aid = [g["aid_spends_count"] for g in patron_games]
    print(f"  mean: {statistics.mean(aid):.2f}, median: {statistics.median(aid):.1f}")

    print("Alliance bonuses fired per game (when Patron present):")
    al = [g["alliance_bonuses_fired"] for g in patron_games]
    print(f"  mean: {statistics.mean(al):.2f}")

    # 5. Score gap when Patron wins
    win_gaps = []
    for g in patron_games:
        if g["patron_seat"] in g["winners"]:
            other_scores = [s for i, s in enumerate(g["scores"]) if i != g["patron_seat"]]
            win_gaps.append(g["patron_score"] - max(other_scores))
    if win_gaps:
        print(f"\nWin-gap (Patron score - 2nd place) when Patron wins: "
              f"mean={statistics.mean(win_gaps):.2f}, median={statistics.median(win_gaps):.1f}, "
              f"min={min(win_gaps):.1f}")

    return patron_games


baseline_games = analyze("research_runs/2026-04-30-baseline-post-redesign.json",
                         "Baseline (16-agent pool)")
new_games = analyze("research_runs/2026-04-30-v2-heuristics.json",
                    "After new heuristics + v2 (19-agent pool)")
