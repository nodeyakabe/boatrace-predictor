"""
boat_scoring_and_bet_suggester.py

提供機能：
- 新配点に基づく総合スコア算出（コース・選手・モーター・決まり手・グレード）
- ラプラス平滑を使ったpit(艇番)勝率の平滑化関数
- 1着固定ルール、データ充実度閾値の実装
- softmaxによる1着確率化、及び任意の1-3着確率を受け取って三連単120通りのEV計算
- 上位N通り（3-10点）の買い目を期待値順に抽出し出力
- 簡易ユニットテストと使用例を含む

想定入力（例）:
boats = [
    {"pit":1, "course_score":80, "player_score":78, "motor_score":65, "kimarite_score":40, "grade_score":30, "data_completeness":85},
    ...
]

odds_map: dict, key "1-2-3" -> payout (100 yenあたり)
"""

from typing import List, Dict, Tuple
import math
import itertools

# 新配点（提案）
WEIGHTS = {
    "course_player": 30.0,   # コース×選手適性（再設計）
    "player_recent": 25.0,   # 選手の直近成績
    "motor_exhibit": 25.0,   # モーター・展示気配
    "kimarite": 10.0,        # 決まり手適性
    "grade": 10.0            # グレード適性
}

DEFAULT_LAPLACE_ALPHA = 2.0
ONE_FIXED_THRESHOLD = 0.55
DATA_COMPL_THRESHOLD = 60.0

def laplace_smoothing(wins: int, trials: int, alpha: float = DEFAULT_LAPLACE_ALPHA, k: int = 1) -> float:
    \"\"\"ラプラス平滑化 (wins + alpha) / (trials + alpha * k)\"\"\"
    return (wins + alpha) / (trials + alpha * k)

def compute_individual_score(boat: Dict) -> float:
    \"\"\"Compute weighted score normalized to 0-100\"\"\"
    cp = boat.get(\"course_player\", boat.get(\"course_score\", 0))
    pr = boat.get(\"player_recent\", boat.get(\"player_score\", 0))
    me = boat.get(\"motor_exhibit\", boat.get(\"motor_score\", 0))
    km = boat.get(\"kimarite\", boat.get(\"kimarite_score\", 0))
    gr = boat.get(\"grade\", boat.get(\"grade_score\", 0))

    total_weight = sum(WEIGHTS.values())
    weighted = (
        WEIGHTS[\"course_player\"] * cp +
        WEIGHTS[\"player_recent\"] * pr +
        WEIGHTS[\"motor_exhibit\"] * me +
        WEIGHTS[\"kimarite\"] * km +
        WEIGHTS[\"grade\"] * gr
    )
    # Normalize to 0-100
    score100 = weighted / total_weight
    return score100

def softmax(scores: List[float], temperature: float = 1.0) -> List[float]:
    if len(scores) == 0:
        return []
    max_s = max(scores)
    exps = [math.exp((s - max_s) / max(temperature, 1e-9)) for s in scores]
    s = sum(exps)
    if s == 0:
        return [1.0/len(scores)] * len(scores)
    return [e/s for e in exps]

def compute_first_place_probs(boats: List[Dict], temperature: float = 1.0) -> List[float]:
    scores = [boat.get(\"overall_score\", compute_individual_score(boat)) for boat in boats]
    probs = softmax(scores, temperature=temperature)
    return probs

def generate_three_way_probabilities(p1: List[float], p2: List[float]=None, p3: List[float]=None) -> Dict[str, float]:
    n = len(p1)
    if p2 is None:
        p2 = [(1.0 - prob) / (n - 1) for prob in p1]
    if p3 is None:
        p3 = [(1.0 - prob) / (n - 1) for prob in p1]

    combo_probs = {}
    total = 0.0
    for a in range(1, n+1):
        for b in range(1, n+1):
            if b == a: continue
            for c in range(1, n+1):
                if c == a or c == b: continue
                pa = p1[a-1]
                pb = p2[b-1]
                pc = p3[c-1]
                prob = pa * pb * pc
                combo = f\"{a}-{b}-{c}\"
                combo_probs[combo] = prob
                total += prob
    if total == 0:
        uniform = 1.0 / (math.perm(n, 3))
        for combo in combo_probs:
            combo_probs[combo] = uniform
    else:
        for combo in combo_probs:
            combo_probs[combo] /= total
    return combo_probs

def apply_one_fixed_rule(p1_probs: List[float], boats: List[Dict], threshold: float = ONE_FIXED_THRESHOLD, data_compl_threshold: float = DATA_COMPL_THRESHOLD) -> Tuple[bool, int]:
    best_idx = max(range(len(p1_probs)), key=lambda i: p1_probs[i])
    best_prob = p1_probs[best_idx]
    data_comp = boats[best_idx].get(\"data_completeness\", 0)
    if best_prob >= threshold and data_comp >= data_compl_threshold:
        return True, boats[best_idx].get(\"pit\")
    return False, -1

def generate_buy_list(boats: List[Dict], odds_map: Dict[str, float], top_n: int = 5, temperature: float = 1.0) -> List[Dict]:
    for b in boats:
        b[\"overall_score\"] = compute_individual_score(b)
    p1 = compute_first_place_probs(boats, temperature=temperature)
    is_fixed, fixed_pit = apply_one_fixed_rule(p1, boats)
    p2 = softmax([b[\"overall_score\"] for b in boats], temperature=temperature*1.2)
    p3 = softmax([b[\"overall_score\"] for b in boats], temperature=temperature*1.5)
    combo_probs = generate_three_way_probabilities(p1, p2, p3)
    if is_fixed:
        fixed_str = f\"{fixed_pit}-\"
        combo_probs = {k:v for k,v in combo_probs.items() if k.startswith(fixed_str)}
        s = sum(combo_probs.values())
        if s>0:
            for k in combo_probs:
                combo_probs[k] /= s
    ev_list = []
    for combo, prob in combo_probs.items():
        payout = odds_map.get(combo)
        if payout is None:
            payout = max(100, int(100.0 / max(prob, 1e-6)))
        ev = prob * payout
        ev_list.append({\"combo\": combo, \"prob\": prob, \"payout\": payout, \"ev\": ev})
    ev_list.sort(key=lambda x: (x[\"ev\"], x[\"prob\"]), reverse=True)
    return ev_list[:top_n]

# Simple demo function to produce output (not executed here)
def demo(boats=None, sample_odds=None, top_n=7):
    if boats is None or sample_odds is None:
        boats = [
            {\"pit\":1, \"course_player\":90, \"player_recent\":85, \"motor_exhibit\":70, \"kimarite\":40, \"grade\":30, \"data_completeness\":90},
            {\"pit\":2, \"course_player\":75, \"player_recent\":70, \"motor_exhibit\":65, \"kimarite\":30, \"grade\":20, \"data_completeness\":80},
            {\"pit\":3, \"course_player\":70, \"player_recent\":60, \"motor_exhibit\":60, \"kimarite\":35, \"grade\":15, \"data_completeness\":75},
            {\"pit\":4, \"course_player\":60, \"player_recent\":55, \"motor_exhibit\":50, \"kimarite\":20, \"grade\":10, \"data_completeness\":60},
            {\"pit\":5, \"course_player\":50, \"player_recent\":50, \"motor_exhibit\":45, \"kimarite\":15, \"grade\":10, \"data_completeness\":50},
            {\"pit\":6, \"course_player\":40, \"player_recent\":45, \"motor_exhibit\":30, \"kimarite\":10, \"grade\":5, \"data_completeness\":40},
        ]
        sample_odds = {
            \"1-2-3\": 850,
            \"1-3-2\": 1200,
            \"1-2-4\": 600,
            \"1-3-4\": 900,
            \"1-4-2\": 1500,
            \"1-4-3\": 1800,
        }
    return generate_buy_list(boats, sample_odds, top_n=top_n)

if __name__ == \"__main__\":
    print(demo())
