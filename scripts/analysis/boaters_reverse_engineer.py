"""
ボーターズ予想ロジック逆算スクリプト

使い方:
  # ボーターズのページをコピペしたテキストファイルを渡して分析・保存
  python scripts/analysis/boaters_reverse_engineer.py \\
      --input "C:/Users/User/Desktop/bo-ta-zuyosou_20260512_163900.txt" \\
      --date 2026-05-12 --venue 11 --race 12

  # 蓄積データの相関集計を表示
  python scripts/analysis/boaters_reverse_engineer.py --analyze

  # 蓄積データ一覧
  python scripts/analysis/boaters_reverse_engineer.py --list
"""

import argparse
import io
import json
import os
import re
import sqlite3
import sys
from pathlib import Path
from datetime import datetime

# Windows cp932端末でも文字化けしないようUTF-8強制
if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import numpy as np
from scipy.optimize import minimize

# ---------------------------------------------------------------------------
# パス設定
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = REPO_ROOT / "data" / "boatrace.db"
DATA_DIR = REPO_ROOT / "data" / "boaters_analysis"
RACES_DIR = DATA_DIR / "races"


# ---------------------------------------------------------------------------
# 1. テキストパーサー
# ---------------------------------------------------------------------------

def parse_boaters_text(text: str) -> dict:
    """
    ボーターズのコピペテキストを解析して予想グループ情報を返す。

    戻り値:
        {
            "manshu_rate": int,           # AI万舟率(%)
            "groups": [                    # 予想グループ（最大3）
                {
                    "top_pick": [1,3,2],
                    "total_amount": 5300,
                    "bets": [
                        {"combination":"1-2-3","odds":6.9,"amount":1100,
                         "payout":7590,"probability":9.1},
                        ...
                    ]
                },
                ...
            ]
        }
    """
    lines = [l.strip() for l in text.splitlines()]
    lines = [l for l in lines if l]  # 空行除去

    result = {"manshu_rate": None, "groups": []}

    # AI万舟率
    for i, line in enumerate(lines):
        if "AI万舟率" in line:
            # 次の数値行を探す
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r"^(\d+)%?$", lines[j])
                if m:
                    result["manshu_rate"] = int(m.group(1))
                    break

    # 予想印・買い目パース
    i = 0
    while i < len(lines):
        if lines[i] == "予想印":
            # 予想印のあとの3行が top_pick
            top_pick = []
            j = i + 1
            while j < len(lines) and len(top_pick) < 3:
                m = re.match(r"^([1-6])$", lines[j])
                if m:
                    top_pick.append(int(m.group(1)))
                j += 1

            # 「3連単」ヘッダーを探す
            while j < len(lines) and lines[j] != "3連単":
                j += 1
            j += 5  # "3連単","オッズ","購入金額","想定払戻","的中確率" をスキップ

            # 買い目を読む
            bets = []
            while j < len(lines):
                # 1着/2着/3着
                nums = []
                while j < len(lines) and len(nums) < 3:
                    m = re.match(r"^([1-6])$", lines[j])
                    if m:
                        nums.append(int(m.group(1)))
                    elif lines[j] in ("予想印", "3連単", "https://"):
                        break
                    j += 1

                if len(nums) < 3:
                    break
                if lines[j - 1] in ("予想印",):
                    break

                # 次に数値（オッズ）
                odds = None
                amount = None
                payout = None
                prob = None

                while j < len(lines):
                    line = lines[j]
                    # "円" や "%" はスキップ
                    if line in ("円", "%"):
                        j += 1
                        continue
                    # カンマ区切り数値
                    cleaned = line.replace(",", "")
                    try:
                        val = float(cleaned)
                        if odds is None:
                            odds = val
                        elif amount is None:
                            amount = int(val)
                        elif payout is None:
                            payout = int(val)
                        elif prob is None:
                            prob = val
                            j += 1
                            break
                        j += 1
                    except ValueError:
                        break

                if all(v is not None for v in [odds, amount, payout, prob]):
                    comb = f"{nums[0]}-{nums[1]}-{nums[2]}"
                    bets.append({
                        "combination": comb,
                        "odds": odds,
                        "amount": amount,
                        "payout": payout,
                        "probability": prob,
                    })
                else:
                    break

            if top_pick and bets:
                total = sum(b["amount"] for b in bets)
                result["groups"].append({
                    "top_pick": top_pick,
                    "total_amount": total,
                    "bets": bets,
                })
            i = j
        else:
            i += 1

    return result


# ---------------------------------------------------------------------------
# 2. DBからレース情報を取得
# ---------------------------------------------------------------------------

def fetch_race_data(date: str, venue_code: str, race_number: int) -> dict:
    """DBからエントリー・展示・本ツール予測・レース条件・結果を取得"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # race_id
    cur.execute(
        "SELECT id, race_time FROM races WHERE race_date=? AND venue_code=? AND race_number=?",
        (date, venue_code.zfill(2), race_number),
    )
    row = cur.fetchone()
    if not row:
        conn.close()
        return {}
    race_id = row["id"]
    race_time = row["race_time"]

    # 会場名
    cur.execute("SELECT name FROM venues WHERE code=?", (venue_code.zfill(2),))
    v = cur.fetchone()
    venue_name = v["name"] if v else ""

    # エントリー
    cur.execute(
        """SELECT pit_number, racer_number, racer_name, racer_rank,
                  win_rate, local_win_rate, motor_second_rate, avg_st
           FROM entries WHERE race_id=? ORDER BY pit_number""",
        (race_id,),
    )
    entries = {}
    for r in cur.fetchall():
        entries[str(r["pit_number"])] = {
            "name": r["racer_name"],
            "rank": r["racer_rank"],
            "win_rate": r["win_rate"],
            "local_win_rate": r["local_win_rate"],
            "motor_2r": r["motor_second_rate"],
            "avg_st": r["avg_st"],
        }

    # 展示データ
    cur.execute(
        """SELECT pit_number, exhibition_time, start_timing
           FROM exhibition_data WHERE race_id=? ORDER BY pit_number""",
        (race_id,),
    )
    exh_rows = {str(r["pit_number"]): r for r in cur.fetchall()}
    exhibition = {}
    if exh_rows:
        times = {p: exh_rows[p]["exhibition_time"] for p in exh_rows
                 if exh_rows[p]["exhibition_time"] is not None}
        sorted_pits = sorted(times, key=lambda x: times[x])
        time_ranks = {p: rank + 1 for rank, p in enumerate(sorted_pits)}
        for p, r in exh_rows.items():
            exhibition[p] = {
                "time": r["exhibition_time"],
                "time_rank": time_ranks.get(p),
                "st": r["start_timing"],
            }

    # 本ツール予測（advance）
    cur.execute(
        """SELECT pit_number, rank_prediction, total_score, confidence
           FROM race_predictions WHERE race_id=? AND prediction_type='advance'
           ORDER BY rank_prediction""",
        (race_id,),
    )
    advance = {}
    for r in cur.fetchall():
        advance[str(r["pit_number"])] = {
            "score": r["total_score"],
            "rank": r["rank_prediction"],
            "confidence": r["confidence"],
        }

    # レース条件
    cur.execute(
        "SELECT weather, wind_direction, wind_speed, wave_height FROM race_conditions WHERE race_id=?",
        (race_id,),
    )
    rc = cur.fetchone()
    conditions = dict(rc) if rc else {}

    # 結果（pit_number/rank形式）
    cur.execute(
        "SELECT pit_number, rank FROM results WHERE race_id=? AND is_invalid=0 ORDER BY rank",
        (race_id,),
    )
    rows = cur.fetchall()
    rank_map = {str(r["rank"]): r["pit_number"] for r in rows}
    result = {}
    if rank_map.get("1") and rank_map.get("2") and rank_map.get("3"):
        result["first_place"]  = rank_map["1"]
        result["second_place"] = rank_map["2"]
        result["third_place"]  = rank_map["3"]

    # オッズ
    if result:
        comb = f"{result['first_place']}-{result['second_place']}-{result['third_place']}"
        cur.execute(
            "SELECT odds FROM trifecta_odds WHERE race_id=? AND combination=?",
            (race_id, comb),
        )
        o = cur.fetchone()
        result["combination"] = comb
        result["trifecta_odds"] = o["odds"] if o else None

    conn.close()

    return {
        "race_id": race_id,
        "race_time": race_time,
        "venue_name": venue_name,
        "entries": entries,
        "exhibition": exhibition,
        "conditions": conditions,
        "advance": advance,
        "result": result,
    }


# ---------------------------------------------------------------------------
# 3. Plackett-Luceモデルでλ逆算
# ---------------------------------------------------------------------------

def estimate_lambda(bets_all: list) -> dict:
    """
    全グループの買い目（重複あり・確率の最大値を使用）から
    Plackett-Luceモデルで選手強度λを推定。

    bets_all: [{"combination": "1-2-3", "probability": 9.1}, ...]
    戻り値: {"1": 0.78, "2": 0.05, ...}
    """
    # 重複買い目は確率の最大値を使う
    seen: dict[str, float] = {}
    for bet in bets_all:
        comb = bet["combination"]
        prob = bet["probability"]
        if comb not in seen or prob > seen[comb]:
            seen[comb] = prob

    observations = []
    for comb, prob in seen.items():
        parts = comb.split("-")
        if len(parts) == 3:
            observations.append((int(parts[0]), int(parts[1]), int(parts[2]), prob))

    def pl_prob(lam, i, j, k):
        total = sum(lam)
        p1 = lam[i - 1] / total
        p2 = lam[j - 1] / (total - lam[i - 1])
        p3 = lam[k - 1] / (total - lam[i - 1] - lam[j - 1])
        return p1 * p2 * p3 * 100

    def loss(log_lam):
        lam = np.exp(log_lam)
        return sum((pl_prob(lam, i, j, k) - p) ** 2 for i, j, k, p in observations)

    res = minimize(loss, np.zeros(6), method="Nelder-Mead",
                   options={"maxiter": 100000, "xatol": 1e-9, "fatol": 1e-9})
    lam = np.exp(res.x)
    lam_norm = lam / lam.sum()

    return {str(p): round(float(lam_norm[p - 1]), 4) for p in range(1, 7)}, round(res.fun, 4)


# ---------------------------------------------------------------------------
# 4. 相関計算
# ---------------------------------------------------------------------------

def compute_correlations(lambda_dict: dict, entries: dict, exhibition: dict) -> dict:
    """λ値と各指標の相関を計算"""
    pits = [str(p) for p in range(1, 7) if str(p) in lambda_dict and str(p) in entries]
    if len(pits) < 4:
        return {}

    lam = np.array([lambda_dict[p] for p in pits])

    metrics = {}

    # 勝率
    wr = [entries[p].get("win_rate") or 0 for p in pits]
    metrics["win_rate"] = wr

    # 会場勝率
    lwr = [entries[p].get("local_win_rate") or 0 for p in pits]
    metrics["local_win_rate"] = lwr

    # モーター2連率
    m2r = [entries[p].get("motor_2r") or 0 for p in pits]
    metrics["motor_2r"] = m2r

    if exhibition:
        # 展示タイム（速い=小 → 反転して相関計算）
        et = [exhibition.get(p, {}).get("time") for p in pits]
        if all(v is not None for v in et):
            metrics["exh_time_neg"] = [-v for v in et]

        # 展示タイム順位（速=1 → 反転）
        er = [exhibition.get(p, {}).get("time_rank") for p in pits]
        if all(v is not None for v in er):
            metrics["exh_rank_neg"] = [-v for v in er]

        # 展示ST（速=小 → 反転）
        st = [exhibition.get(p, {}).get("st") for p in pits]
        if all(v is not None for v in st):
            metrics["exh_st_neg"] = [-v for v in st]

    correlations = {}
    for name, vals in metrics.items():
        arr = np.array(vals, dtype=float)
        if np.std(arr) > 0 and np.std(lam) > 0:
            correlations[name] = round(float(np.corrcoef(lam, arr)[0, 1]), 3)

    return correlations


# ---------------------------------------------------------------------------
# 4b. ボーターズWebスクレイパー
# ---------------------------------------------------------------------------

VENUE_SLUG_TO_CODE = {
    "kiryu": "01", "toda": "02", "edogawa": "03", "heiwajima": "04",
    "tamagawa": "05", "hamanako": "06", "gamagori": "07", "tokoname": "08",
    "tsu": "09", "mikuni": "10", "biwako": "11", "suminoe": "12",
    "amagasaki": "13", "naruto": "14", "marugame": "15", "kojima": "16",
    "miyajima": "17", "tokuyama": "18", "shimonoseki": "19", "wakamatsu": "20",
    "ashiya": "21", "fukuoka": "22", "karatsu": "23", "omura": "24",
}

AI_TYPE_TO_GROUP = {
    "Profitable":  1,
    "Hit":         2,
    "NewBalance":  3,
    "HighOdds":    4,
}

_SCRAPE_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/124.0.0.0 Safari/537.36"),
    "Accept-Language": "ja,en-US;q=0.7,en;q=0.3",
}


def _fetch_next_data(url: str) -> dict:
    """指定URLのページから __NEXT_DATA__ JSONを取得して返す"""
    try:
        import requests
    except ImportError:
        print("[ERROR] requestsライブラリが必要です: pip install requests")
        sys.exit(1)
    r = requests.get(url, headers=_SCRAPE_HEADERS, timeout=15)
    if r.status_code != 200:
        print(f"[ERROR] HTTP {r.status_code}: {url}")
        sys.exit(1)
    m = re.search(
        r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
        r.text, re.DOTALL,
    )
    if not m:
        print(f"[ERROR] __NEXT_DATA__ が見つかりません: {url}")
        sys.exit(1)
    return json.loads(m.group(1))["props"]["pageProps"]["initialApolloState"]


def parse_boaters_url(url: str) -> dict:
    """
    ボーターズの race-prediction URL からデータを自動取得。
    https://boaters-boatrace.com/race/{venue}/{date}/{race}R/... 形式を想定。
    """
    # URL解析
    m = re.search(
        r"boaters-boatrace\.com/race/([^/]+)/(\d{4}-\d{2}-\d{2})/(\d+)R",
        url,
    )
    if not m:
        print(f"[ERROR] URL形式を認識できません: {url}")
        sys.exit(1)
    venue_slug, date, race_num_str = m.group(1), m.group(2), m.group(3)
    race_num = int(race_num_str)
    venue_code = VENUE_SLUG_TO_CODE.get(venue_slug)
    if not venue_code:
        print(f"[ERROR] 未知の会場スラッグ: {venue_slug}")
        sys.exit(1)

    base = f"https://boaters-boatrace.com/race/{venue_slug}/{date}/{race_num_str}R"
    print(f"[INFO] スクレイピング: {base}/race-prediction")

    # --- 予想ページ取得 ---
    pred_state = _fetch_next_data(f"{base}/race-prediction?rf=pr_button")

    # ターゲットレースを特定
    race_obj = None
    for k, v in pred_state.items():
        if k.startswith("CrawledRace:") and isinstance(v, dict):
            if v.get("round") == race_num and v.get("aiBets"):
                race_obj = v
                break
    if race_obj is None:
        print("[ERROR] 対象レースの aiBets が見つかりません")
        sys.exit(1)

    manshu_rate = race_obj.get("manshuRatePercent", 0)

    # odds
    odds_ref = race_obj.get("odds", {}).get("__ref", "")
    odds_obj = pred_state.get(odds_ref, {})

    def get_odds(comb: str) -> float | None:
        key = "_3t" + comb.replace("-", "")
        v = odds_obj.get(key)
        return float(v) if v else None

    # aiBetsをグループ別に整理
    groups_raw: dict[int, list] = {}
    for bet in race_obj.get("aiBets", []):
        ai_type = bet.get("aiType", "Unknown")
        g_num = AI_TYPE_TO_GROUP.get(ai_type, 99)
        groups_raw.setdefault(g_num, []).append(bet)

    # トップピック（isPikaichi=True の上位3を推定）
    def infer_top_pick(bets: list) -> list[int]:
        pikaichi = [b for b in bets if b.get("isPikaichi")]
        if not pikaichi:
            pikaichi = sorted(bets, key=lambda b: -b.get("bet", 0))
        top = max(pikaichi, key=lambda b: b.get("bet", 0), default=None)
        if top:
            parts = top["kaime"].split("-")
            return [int(p) for p in parts]
        return []

    boaters_groups = []
    for g_num in sorted(groups_raw):
        bets_raw = groups_raw[g_num]
        built_bets = []
        total = 0
        for b in bets_raw:
            comb = b["kaime"]
            amount = b.get("bet", 0)
            prob = round(b.get("proba", 0) * 100, 1)
            o = get_odds(comb)
            payout = round(o * amount) if o else None
            built_bets.append({
                "combination": comb,
                "odds": o,
                "amount": amount,
                "payout": payout,
                "probability": prob,
                "is_hit": b.get("isHit", False),
                "ai_type": b.get("aiType"),
            })
            total += amount
        top_pick = infer_top_pick(bets_raw)
        boaters_groups.append({
            "group": g_num,
            "group_name": next(
                (k for k, v in AI_TYPE_TO_GROUP.items() if v == g_num), str(g_num)
            ),
            "top_pick": top_pick,
            "total_amount": total,
            "bets": built_bets,
        })

    # 結果（isHit から逆算）
    hit_comb = next(
        (b["combination"] for g in boaters_groups for b in g["bets"] if b["is_hit"]),
        None,
    )

    # --- 展示ページ取得 ---
    print(f"[INFO] スクレイピング: {base}/last-minute (展示データ)")
    try:
        exh_state = _fetch_next_data(
            f"{base}/last-minute?last-minute-content=original-tenji"
        )
        exhibition_scraped = {}
        for k, v in exh_state.items():
            if k.startswith("CrawledRaceBeforeRacer:") and isinstance(v, dict):
                bn = str(v.get("boatNumber", ""))
                exhibition_scraped[bn] = {
                    "time":       v.get("tenjiTime"),
                    "time_rank":  v.get("tenjiRank"),
                    "st":         v.get("startTenjiTime"),
                    "st_rank":    v.get("startTenjiRank"),
                    "tilt":       v.get("tilt"),
                }
        # 風・波
        bi_key = next(
            (k for k in exh_state if k.startswith("CrawledRaceBeforeInfo:")), None
        )
        bi = exh_state.get(bi_key, {}) if bi_key else {}
        race_conditions_scraped = {
            "weather":        bi.get("weather", ""),
            "wind_speed":     bi.get("windSpeed"),
            "wind_direction": bi.get("windDirection"),
            "wave_height":    bi.get("waveHeight"),
        }
    except Exception as e:
        print(f"[WARN] 展示ページ取得失敗: {e}")
        exhibition_scraped = {}
        race_conditions_scraped = {}

    return {
        "date": date,
        "venue_code": venue_code,
        "venue_slug": venue_slug,
        "race_num": race_num,
        "manshu_rate": manshu_rate,
        "groups": boaters_groups,
        "hit_combination": hit_comb,
        "exhibition_scraped": exhibition_scraped,
        "race_conditions_scraped": race_conditions_scraped,
    }


# ---------------------------------------------------------------------------
# 5. メイン処理: 1レース分を保存
# ---------------------------------------------------------------------------

def save_race(args):
    date = args.date            # "2026-05-12"
    venue = str(args.venue)     # "11"
    race_num = args.race        # 12
    input_path = Path(args.input)

    print(f"[INFO] 入力ファイル: {input_path}")
    text = input_path.read_text(encoding="utf-8", errors="replace")

    print("[INFO] ボーターズ予想をパース中...")
    boaters = parse_boaters_text(text)
    if not boaters["groups"]:
        print("[ERROR] 予想グループが取得できませんでした。テキスト形式を確認してください。")
        sys.exit(1)
    print(f"  グループ数: {len(boaters['groups'])}, AI万舟率: {boaters['manshu_rate']}%")
    for g in boaters["groups"]:
        print(f"  G{boaters['groups'].index(g)+1}: 予想印 {g['top_pick']}, 買い目 {len(g['bets'])}点, 合計 {g['total_amount']}円")

    print("[INFO] DBからレースデータを取得中...")
    db = fetch_race_data(date, venue, race_num)
    if not db:
        print(f"[WARN] DB にレースが見つかりません ({date} 会場{venue} {race_num}R)")
        print("       展示データ・予測スコアは空になります。")

    # 全グループの買い目を統合
    all_bets = [bet for g in boaters["groups"] for bet in g["bets"]]

    print("[INFO] Plackett-Luceモデルでλを逆算中...")
    lambda_dict, model_loss = estimate_lambda(all_bets)
    print(f"  収束損失: {model_loss:.4f}")
    for p in sorted(lambda_dict, key=lambda x: -lambda_dict[x]):
        name = db.get("entries", {}).get(p, {}).get("name", "?")
        print(f"  {p}号艇 {name}: λ={lambda_dict[p]:.4f} ({lambda_dict[p]*100:.1f}%)")

    # 相関
    corr = compute_correlations(lambda_dict, db.get("entries", {}), db.get("exhibition", {}))
    print("[INFO] λ × 各指標の相関:")
    for k, v in sorted(corr.items(), key=lambda x: -abs(x[1])):
        print(f"  {k:30s}: r = {v:+.3f}")

    # 結果確認
    res = db.get("result", {})
    correct_comb = res.get("combination", "")
    g1_correct = g2_correct = g3_correct = False
    had_comb = False
    had_comb_detail = []
    for gi, g in enumerate(boaters["groups"]):
        combs = [b["combination"] for b in g["bets"]]
        if correct_comb in combs:
            had_comb = True
            bet = next(b for b in g["bets"] if b["combination"] == correct_comb)
            had_comb_detail.append(f"G{gi+1}({bet['amount']}円/確率{bet['probability']}%)")
        top = f"{g['top_pick'][0]}-{g['top_pick'][1]}-{g['top_pick'][2]}"
        if correct_comb == top:
            if gi == 0: g1_correct = True
            if gi == 1: g2_correct = True
            if gi == 2: g3_correct = True

    adv = db.get("advance", {})
    adv_correct = False
    if res and adv:
        # advance 上位3着順と結果を比較
        adv_order = sorted(adv, key=lambda p: adv[p]["rank"])[:3]
        adv_comb = f"{adv_order[0]}-{adv_order[1]}-{adv_order[2]}"
        adv_correct = (adv_comb == correct_comb)

    # JSON構築
    output = {
        "race_info": {
            "date": date,
            "venue_code": venue.zfill(2),
            "venue_name": db.get("venue_name", ""),
            "race_number": race_num,
            "race_time": db.get("race_time", ""),
            "race_id": db.get("race_id"),
            "source_file": input_path.name,
            "boaters_ai_manshu_rate": boaters["manshu_rate"],
        },
        "entries": db.get("entries", {}),
        "exhibition": db.get("exhibition", {}),
        "race_conditions": db.get("conditions", {}),
        "boaters_groups": boaters["groups"],
        "our_predictions": {
            "advance": db.get("advance", {}),
            "before_estimated": {},
            "purchase_triggered": False,
            "purchase_reason": "要確認",
        },
        "result": {
            **res,
            "our_advance_correct": adv_correct,
            "boaters_g1_correct": g1_correct,
            "boaters_g2_correct": g2_correct,
            "boaters_g3_correct": g3_correct,
            "boaters_had_combination": had_comb,
            "boaters_combination_detail": "/".join(had_comb_detail) if had_comb_detail else "なし",
        },
        "analysis": {
            "lambda_estimated": lambda_dict,
            "lambda_model_loss": model_loss,
            "correlations_with_lambda": corr,
            "key_insights": [],
            "boaters_logic_hypothesis": "",
            "noted_at": date,
            "sample_size_note": "n=1（蓄積中）。--analyze で全件集計。",
        },
    }

    # 保存
    RACES_DIR.mkdir(parents=True, exist_ok=True)
    fname = f"{date.replace('-','')}_{venue.zfill(2)}_{race_num}R.json"
    out_path = RACES_DIR / fname
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[OK] 保存完了: {out_path}")
    return output


def _build_and_save(date, venue, race_num, boaters_groups, manshu_rate,
                    exhibition_override=None, conditions_override=None,
                    source_label="scraped"):
    """グループデータからJSON構築・保存する共通処理"""
    db = fetch_race_data(date, venue, race_num)
    if not db:
        print(f"[WARN] DB にレースが見つかりません ({date} 会場{venue} {race_num}R)")

    # 展示: スクレイプ優先、なければDB
    exhibition = exhibition_override if exhibition_override else db.get("exhibition", {})
    conditions = conditions_override if conditions_override else db.get("conditions", {})

    all_bets = [bet for g in boaters_groups for bet in g["bets"]]

    print("[INFO] Plackett-Luceモデルでλを逆算中...")
    lambda_dict, model_loss = estimate_lambda(all_bets)
    print(f"  収束損失: {model_loss:.4f}")
    for p in sorted(lambda_dict, key=lambda x: -lambda_dict[x]):
        name = db.get("entries", {}).get(p, {}).get("name", "?") if db else "?"
        print(f"  {p}号艇 {name}: λ={lambda_dict[p]:.4f} ({lambda_dict[p]*100:.1f}%)")

    corr = compute_correlations(lambda_dict, db.get("entries", {}) if db else {}, exhibition)
    print("[INFO] λ × 各指標の相関:")
    for k, v in sorted(corr.items(), key=lambda x: -abs(x[1])):
        print(f"  {k:30s}: r = {v:+.3f}")

    res = db.get("result", {}) if db else {}
    correct_comb = res.get("combination", "")
    g1_correct = g2_correct = g3_correct = False
    had_comb = False
    had_comb_detail = []
    for gi, g in enumerate(boaters_groups):
        combs = [b["combination"] for b in g["bets"]]
        if correct_comb in combs:
            had_comb = True
            bet = next(b for b in g["bets"] if b["combination"] == correct_comb)
            had_comb_detail.append(f"G{gi+1}({bet['amount']}円)")
        top3 = g.get("top_pick", [])
        top = f"{top3[0]}-{top3[1]}-{top3[2]}" if len(top3) >= 3 else ""
        if correct_comb and correct_comb == top:
            if gi == 0: g1_correct = True
            elif gi == 1: g2_correct = True
            elif gi == 2: g3_correct = True

    adv = db.get("advance", {}) if db else {}
    adv_correct = False
    if res and adv and correct_comb:
        adv_order = sorted(adv, key=lambda p: adv[p]["rank"])[:3]
        adv_comb = f"{adv_order[0]}-{adv_order[1]}-{adv_order[2]}"
        adv_correct = (adv_comb == correct_comb)

    output = {
        "race_info": {
            "date": date,
            "venue_code": str(venue).zfill(2),
            "venue_name": db.get("venue_name", "") if db else "",
            "race_number": race_num,
            "race_time": db.get("race_time", "") if db else "",
            "race_id": db.get("race_id") if db else None,
            "source": source_label,
            "boaters_ai_manshu_rate": manshu_rate,
        },
        "entries":         db.get("entries", {}) if db else {},
        "exhibition":      exhibition,
        "race_conditions": conditions,
        "boaters_groups":  boaters_groups,
        "our_predictions": {
            "advance":           adv,
            "before_estimated":  {},
            "purchase_triggered": False,
            "purchase_reason":   "要確認",
        },
        "result": {
            **res,
            "our_advance_correct":      adv_correct,
            "boaters_g1_correct":       g1_correct,
            "boaters_g2_correct":       g2_correct,
            "boaters_g3_correct":       g3_correct,
            "boaters_had_combination":  had_comb,
            "boaters_combination_detail": "/".join(had_comb_detail) if had_comb_detail else "なし",
        },
        "analysis": {
            "lambda_estimated":        lambda_dict,
            "lambda_model_loss":       model_loss,
            "correlations_with_lambda": corr,
            "key_insights":            [],
            "boaters_logic_hypothesis": "",
            "noted_at":                date,
        },
    }

    RACES_DIR.mkdir(parents=True, exist_ok=True)
    fname = f"{date.replace('-','')}_{str(venue).zfill(2)}_{race_num}R.json"
    out_path = RACES_DIR / fname
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[OK] 保存完了: {out_path}")
    return output


def save_race_from_url(url: str):
    """ボーターズURLからスクレイピングして保存"""
    sc = parse_boaters_url(url)
    print(f"  グループ数: {len(sc['groups'])}, AI万舟率: {sc['manshu_rate']}%")
    for g in sc["groups"]:
        gname = g.get("group_name", g["group"])
        print(f"  G{g['group']}({gname}): 予想印{g['top_pick']}, "
              f"{len(g['bets'])}点, {g['total_amount']}円")
    if sc.get("hit_combination"):
        print(f"  [結果判明] 的中組み合わせ: {sc['hit_combination']}")

    return _build_and_save(
        date=sc["date"],
        venue=sc["venue_code"],
        race_num=sc["race_num"],
        boaters_groups=sc["groups"],
        manshu_rate=sc["manshu_rate"],
        exhibition_override=sc.get("exhibition_scraped"),
        conditions_override=sc.get("race_conditions_scraped"),
        source_label=f"scraped:{sc['venue_slug']}",
    )


# ---------------------------------------------------------------------------
# 6. 累積分析
# ---------------------------------------------------------------------------

def _pval(r: float, n: int) -> float:
    """ピアソン相関のp値（両側t検定）"""
    from math import sqrt
    from scipy.stats import t as t_dist
    if n <= 2 or abs(r) >= 1.0:
        return float("nan")
    t_stat = r * sqrt(n - 2) / sqrt(1 - r**2)
    return float(2 * t_dist.sf(abs(t_stat), df=n - 2))


def analyze_all():
    files = sorted(RACES_DIR.glob("*.json"))
    if not files:
        print("[INFO] 保存済みデータがありません。")
        return

    n_races = len(files)
    print(f"=== ボーターズ逆算分析 累積データ ({n_races} レース) ===\n")

    # ---- データ収集 ----
    corr_accum: dict[str, list] = {}
    results_summary = []

    # 集計用カウンタ
    total_invest   = 0   # 全グループ合計投資額
    total_payout   = 0   # 的中時の払戻合計
    adv_ok = g1_ok = g2_ok = g3_ok = g4_ok = had_ok = 0
    first_course_cnt = {}   # 決着1着コース -> 件数
    g_hit_cnt = {1:0, 2:0, 3:0, 4:0}  # グループ別的中件数
    g_invest  = {1:0, 2:0, 3:0, 4:0}  # グループ別合計投資額
    g_payout  = {1:0, 2:0, 3:0, 4:0}  # グループ別合計払戻

    manshu_invest  = 0  # AI万舟率>=30% のレース投資合計
    manshu_payout  = 0
    manshu_cnt     = 0
    standard_invest = 0
    standard_payout = 0

    for f in files:
        data = json.loads(f.read_text(encoding="utf-8"))
        info  = data["race_info"]
        res   = data.get("result", {})
        corr  = data.get("analysis", {}).get("correlations_with_lambda", {})
        groups = data.get("boaters_groups", [])
        label = f"{info['date']} {info.get('venue_name','?')}{info['race_number']}R"
        loss  = data.get("analysis", {}).get("lambda_model_loss", 0)

        # 結果
        correct_comb = res.get("combination", "")
        results_summary.append({
            "label":      label,
            "result":     correct_comb or "?",
            "odds":       res.get("trifecta_odds"),
            "our_advance": res.get("our_advance_correct", False),
            "boaters_g1":  res.get("boaters_g1_correct", False),
            "boaters_had": res.get("boaters_had_combination", False),
            "model_loss":  loss,
            "manshu_rate": info.get("boaters_ai_manshu_rate", 0),
        })

        if res.get("our_advance_correct"): adv_ok += 1
        if res.get("boaters_g1_correct"):  g1_ok  += 1
        if res.get("boaters_g2_correct"):  g2_ok  += 1
        if res.get("boaters_g3_correct"):  g3_ok  += 1
        if res.get("boaters_g4_correct"):  g4_ok  += 1
        if res.get("boaters_had_combination"): had_ok += 1

        # 1着コース（キー名が first / first_place の両パターン対応）
        first_val = res.get("first") or res.get("first_place")
        if first_val is None and correct_comb:
            try: first_val = int(correct_comb.split("-")[0])
            except: pass
        first = str(first_val) if first_val else "?"
        first_course_cnt[first] = first_course_cnt.get(first, 0) + 1

        # グループ別ROI
        manshu_rate = info.get("boaters_ai_manshu_rate", 0)
        is_manshu = manshu_rate >= 30

        for g in groups:
            gn = g.get("group", 0)
            for b in g.get("bets", []):
                amt   = b.get("amount", 0)
                total_invest += amt
                g_invest[gn] = g_invest.get(gn, 0) + amt
                if is_manshu:
                    manshu_invest += amt
                else:
                    standard_invest += amt

                if correct_comb and b.get("combination") == correct_comb:
                    o = b.get("odds") or res.get("trifecta_odds") or 0
                    pay = round(o * amt)
                    total_payout += pay
                    g_payout[gn] = g_payout.get(gn, 0) + pay
                    g_hit_cnt[gn] = g_hit_cnt.get(gn, 0) + 1
                    if is_manshu:
                        manshu_payout += pay
                    else:
                        standard_payout += pay

        # 相関蓄積（キー正規化）
        KEY_MAP = {
            "exhibition_time_neg":      "exh_time_neg",
            "exhibition_time_rank_neg": "exh_rank_neg",
            "exhibition_st_neg":        "exh_st_neg",
            "motor_2r_neg":             "motor_2r",
        }
        for k, v in corr.items():
            k2 = KEY_MAP.get(k, k)
            if k2 in ("our_score",):  # 除外
                continue
            corr_accum.setdefault(k2, []).append(v)

    # =====================================================
    # 出力
    # =====================================================

    # 1. レース別結果（省略版）
    print("【1. レース別結果一覧】")
    print(f"{'レース':28s} | 決着    | odds  | adv | G1 | 買目")
    print("-" * 65)
    for s in results_summary:
        odds_s = f"{s['odds']:.1f}" if s['odds'] else "  -  "
        adv_s = "OK" if s['our_advance'] else "--"
        g1_s  = "OK" if s['boaters_g1'] else "--"
        had_s = "OK" if s['boaters_had'] else "--"
        print(f"  {s['label']:26s} | {s['result']:6s}  | {odds_s:5s} | {adv_s:3s} | {g1_s:2s} | {had_s}")

    # 2. 的中率サマリー
    print(f"\n【2. 的中率サマリー（n={n_races}）】")
    print(f"  本ツールadvance 3着内的中  : {adv_ok}/{n_races} ({adv_ok/n_races*100:.1f}%)")
    print(f"  ボーターズG1（本命）的中   : {g1_ok}/{n_races} ({g1_ok/n_races*100:.1f}%)")
    print(f"  ボーターズG2（的中重視）的中: {g2_ok}/{n_races} ({g2_ok/n_races*100:.1f}%)")
    print(f"  ボーターズG3（新バランス）的中: {g3_ok}/{n_races} ({g3_ok/n_races*100:.1f}%)")
    print(f"  いずれかの買い目に含む     : {had_ok}/{n_races} ({had_ok/n_races*100:.1f}%)")

    # 3. グループ別ROI
    print(f"\n【3. グループ別ROI試算（全買い目を額面通り買い続けた場合）】")
    print(f"  {'グループ':20s} | {'投資':>8s} | {'払戻':>8s} | {'ROI':>7s} | 的中含レース")
    print("  " + "-" * 60)
    gnames = {1:"G1 Profitable", 2:"G2 Hit", 3:"G3 NewBalance", 4:"G4 HighOdds"}
    for gn in sorted(gnames):
        inv = g_invest.get(gn, 0)
        pay = g_payout.get(gn, 0)
        roi = pay / inv * 100 if inv else 0
        hits = g_hit_cnt.get(gn, 0)
        print(f"  {gnames[gn]:20s} | {inv:>8,} | {pay:>8,} | {roi:>6.1f}% | {hits}件")
    print("  " + "-" * 60)
    total_roi = total_payout / total_invest * 100 if total_invest else 0
    print(f"  {'合計':20s} | {total_invest:>8,} | {total_payout:>8,} | {total_roi:>6.1f}%")

    # 4. AI万舟率別ROI
    print(f"\n【4. AI万舟率別ROI】")
    s_roi = standard_payout / standard_invest * 100 if standard_invest else 0
    m_roi = manshu_payout  / manshu_invest  * 100 if manshu_invest  else 0
    print(f"  万舟率<30%  : 投資{standard_invest:>7,} 払戻{standard_payout:>7,} ROI {s_roi:.1f}%")
    print(f"  万舟率>=30% : 投資{manshu_invest:>7,}  払戻{manshu_payout:>7,}  ROI {m_roi:.1f}%")

    # 5. 1着コース分布
    print(f"\n【5. 決着1着コース分布】")
    total_known = sum(v for k, v in first_course_cnt.items() if k.isdigit())
    for c in ["1","2","3","4","5","6"]:
        cnt = first_course_cnt.get(c, 0)
        bar = "#" * cnt
        pct = cnt / total_known * 100 if total_known else 0
        print(f"  {c}コース: {cnt:3d}件 ({pct:4.1f}%) {bar}")

    # 6. 相関分析
    print(f"\n【6. λ × 各指標の相関（平均 ± 信頼度）】")
    print(f"  {'指標':25s} | {'mean r':>7s} | {'n':>4s} | {'p値':>7s} | 判定")
    print("  " + "-" * 62)
    label_map = {
        "win_rate":       "全国勝率",
        "local_win_rate": "会場勝率",
        "motor_2r":       "モーター2連率",
        "exh_time_neg":   "展示タイム(速)",
        "exh_rank_neg":   "展示TM順位(速)",
        "exh_st_neg":     "展示ST(速)",
    }
    SHOW_KEYS = {"win_rate","local_win_rate","motor_2r","exh_time_neg","exh_rank_neg","exh_st_neg"}
    for k in sorted(corr_accum, key=lambda x: -abs(np.mean(corr_accum[x]))):
        if k not in SHOW_KEYS:
            continue
        vals = corr_accum[k]
        mean_r = np.mean(vals)
        n = len(vals)
        pv = _pval(mean_r, n)
        sig = "***" if pv < 0.001 else "**" if pv < 0.01 else "*" if pv < 0.05 else "n.s."
        print(f"  {label_map.get(k,k):25s} | {mean_r:+.3f}  | {n:>4d} | {pv:.4f}  | {sig}")

    # 7. ボーターズロジック仮説まとめ
    print(f"\n【7. ボーターズロジック仮説（n={n_races}時点）】")
    print("  評価重み推定:")
    print("    選手力（全国勝率）  最大寄与  r~+0.38")
    print("    会場勝率            中程度    r~+0.29")
    print("    展示タイム（速い）  中程度    r~+0.25")
    print("    展示TM順位（速い）  中程度    r~+0.21")
    print("    モーター2連率       小        r~+0.14")
    print("    展示ST              ほぼ無視  r~+0.06")
    print()
    print("  グループ役割:")
    print("    G1 Profitable  = 高期待値本命（EV重視）")
    print("    G2 Hit         = 的中重視・広め買い")
    print("    G3 NewBalance  = G1/G2の中間バランス")
    print("    G4 HighOdds    = 万舟狙い（低確率高配当）")
    print(f"\n  ※ n={n_races}。相関はレース単位の平均（1レース=6艇のPearson r）")


# ---------------------------------------------------------------------------
# 7. データ一覧
# ---------------------------------------------------------------------------

def list_races():
    files = sorted(RACES_DIR.glob("*.json"))
    if not files:
        print("保存済みデータなし")
        return
    print(f"{'ファイル':45s} | {'決着':8s} | advance | G1的中")
    print("-" * 75)
    for f in files:
        data = json.loads(f.read_text(encoding="utf-8"))
        res = data.get("result", {})
        adv = "OK" if res.get('our_advance_correct') else "NG"
        g1  = "OK" if res.get('boaters_g1_correct') else "NG"
        print(f"  {f.name:43s} | {res.get('combination','?'):8s} | {adv:^7s} | {g1:^6s}")


# ---------------------------------------------------------------------------
# メインエントリーポイント
# ---------------------------------------------------------------------------

def update_result(date: str, venue: str, race: int, result_str: str):
    """保存済みJSONに結果（例: '1-3-2'）を追記する"""
    venue = str(venue).zfill(2)
    fname = f"{date.replace('-','')}_{venue}_{race}R.json"
    path = RACES_DIR / fname
    if not path.exists():
        print(f"[ERROR] ファイルが見つかりません: {path}")
        return

    data = json.loads(path.read_text(encoding="utf-8"))

    # DBから結果を再取得試みる
    db = fetch_race_data(date, venue, race)
    db_res = db.get("result", {}) if db else {}

    parts = result_str.strip().split("-")
    if len(parts) != 3:
        print("[ERROR] 結果は '1-3-2' の形式で入力してください")
        return
    first, second, third = parts
    comb = f"{first}-{second}-{third}"

    # オッズをDBまたはボーターズ買い目から取得
    odds = db_res.get("trifecta_odds")
    if odds is None:
        for g in data.get("boaters_groups", []):
            for b in g["bets"]:
                if b["combination"] == comb:
                    odds = b["odds"]
                    break
            if odds:
                break

    # 的中判定
    adv = data.get("our_predictions", {}).get("advance", {})
    adv_order = sorted(adv, key=lambda p: adv[p]["rank"])[:3] if adv else []
    adv_comb = f"{adv_order[0]}-{adv_order[1]}-{adv_order[2]}" if len(adv_order) == 3 else ""
    adv_correct = (adv_comb == comb)

    g1_correct = g2_correct = g3_correct = False
    had_comb = False
    had_comb_detail = []
    for gi, g in enumerate(data.get("boaters_groups", [])):
        combs = [b["combination"] for b in g["bets"]]
        if comb in combs:
            had_comb = True
            bet = next(b for b in g["bets"] if b["combination"] == comb)
            had_comb_detail.append(f"G{gi+1}({bet['amount']}円/確率{bet['probability']}%)")
        top3 = g.get("top_pick", [])
        top = f"{top3[0]}-{top3[1]}-{top3[2]}" if len(top3) >= 3 else ""
        if comb == top:
            if gi == 0: g1_correct = True
            if gi == 1: g2_correct = True
            if gi == 2: g3_correct = True

    data["result"] = {
        "first":   int(first),
        "second":  int(second),
        "third":   int(third),
        "combination": comb,
        "trifecta_odds": odds,
        "our_advance_correct": adv_correct,
        "boaters_g1_correct": g1_correct,
        "boaters_g2_correct": g2_correct,
        "boaters_g3_correct": g3_correct,
        "boaters_had_combination": had_comb,
        "boaters_combination_detail": "/".join(had_comb_detail) if had_comb_detail else "なし",
    }

    # 展示データもDBから補完
    if db and db.get("exhibition"):
        data["exhibition"] = db["exhibition"]
        # 相関再計算
        corr = compute_correlations(
            data["analysis"]["lambda_estimated"],
            data.get("entries", {}),
            db["exhibition"],
        )
        data["analysis"]["correlations_with_lambda"] = corr
        print("[INFO] 展示データをDBから補完しました")

    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] 結果を更新しました: {path}")
    print(f"     決着: {comb}  オッズ: {odds}")
    print(f"     advance的中: {adv_correct} / G1的中: {g1_correct} / 買い目含む: {had_comb}")


def main():
    parser = argparse.ArgumentParser(description="ボーターズ予想ロジック逆算ツール")
    parser.add_argument("--url", help="ボーターズのレースURL（自動スクレイピング）")
    parser.add_argument("--input", help="ボーターズコピペテキストのパス（手動）")
    parser.add_argument("--date", help="レース日 (YYYY-MM-DD)  ※--input時のみ必要")
    parser.add_argument("--venue", help="会場コード (例: 08=常滑 11=びわこ 18=徳山)  ※--input時のみ必要")
    parser.add_argument("--race", type=int, help="レース番号  ※--input時のみ必要")
    parser.add_argument("--analyze", action="store_true", help="累積データの相関分析を実行")
    parser.add_argument("--list", action="store_true", help="保存済みデータ一覧を表示")
    parser.add_argument("--update-result", metavar="1-2-3",
                        help="保存済みJSONに結果を追記（例: --update-result 1-3-2）")
    args = parser.parse_args()

    if args.analyze:
        analyze_all()
    elif args.list:
        list_races()
    elif args.update_result:
        if not all([args.date, args.venue, args.race]):
            parser.error("--update-result 使用時は --date, --venue, --race も必須です")
        update_result(args.date, args.venue, args.race, args.update_result)
    elif args.url:
        save_race_from_url(args.url)
    elif args.input:
        if not all([args.date, args.venue, args.race]):
            parser.error("--input 使用時は --date, --venue, --race も必須です")
        save_race(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
