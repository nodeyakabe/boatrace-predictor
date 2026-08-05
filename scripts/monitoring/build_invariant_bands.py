#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_invariant_bands.py — Invariant Watch v1 Phase 1
カテゴリ B/C の基準帯域を IS 2020-2025 実績から算出し
config/invariant_bands.json に出力する。

制約:
  - 本スクリプトは帯域初期構築時に一度だけ実行する
  - 帯域変更はユーザー承認 + 変更履歴 + findings 記録が必須
  - DB に対して SELECT のみ（書き込みなし）

出力: config/invariant_bands.json
"""

import sqlite3
import json
import hashlib
import sys
import math
import os
from datetime import datetime, date
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "boatrace.db"
OUTPUT_PATH = PROJECT_ROOT / "config" / "invariant_bands.json"

IS_START = "2020-01-01"
IS_END   = "2025-12-31"

def pct(sorted_vals, p):
    if not sorted_vals:
        return None
    idx = int(len(sorted_vals) * p / 100)
    idx = min(idx, len(sorted_vals) - 1)
    return sorted_vals[idx]


def main():
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

    print("=== Invariant Watch v1 - Phase 1: 帯域構築 ===")
    print(f"DB: {DB_PATH}")
    print(f"IS期間: {IS_START} ~ {IS_END}")
    print()

    conn = sqlite3.connect(str(DB_PATH))
    cur  = conn.cursor()

    bands = {}

    # ---------------------------------------------------------------
    # B-2: スコア分布 (total_score, before 予測 rank=1, IS 2020-2025)
    # ---------------------------------------------------------------
    print("[B-2] スコア分布を計算中...")
    cur.execute("""
        SELECT rp.total_score
        FROM race_predictions rp
        JOIN races r ON rp.race_id = r.id
        WHERE rp.prediction_type = 'before'
          AND rp.rank_prediction  = 1
          AND r.race_date BETWEEN ? AND ?
          AND rp.total_score IS NOT NULL
        ORDER BY rp.total_score
    """, (IS_START, IS_END))
    scores = [row[0] for row in cur.fetchall()]
    N_score = len(scores)
    p10 = pct(scores, 10)
    p25 = pct(scores, 25)
    p50 = pct(scores, 50)
    p75 = pct(scores, 75)
    p90 = pct(scores, 90)
    print(f"  N={N_score:,}  P10={p10} P25={p25} P50={p50} P75={p75} P90={p90}")

    bands["b2_score_distribution"] = {
        "description": "before rank=1 total_score の分位数 (IS 2020-2025)",
        "source": "race_predictions (before, rank_prediction=1) + races, IS 2020-2025",
        "n_samples": N_score,
        "p10": p10, "p25": p25, "p50": p50, "p75": p75, "p90": p90,
        "warn_tolerance_pt": 5.0,   # ±5pt でWARN
        "note": (
            "P90 = P95 = 110.0 (total_score は 110.0 でキャップされる設計)。"
            "P50基準±5ptを目安にドリフト検知。"
        )
    }

    # ---------------------------------------------------------------
    # B-3: 信頼度構成比 (before 予測 rank=1, IS 2020-2025)
    # ---------------------------------------------------------------
    print("[B-3] 信頼度構成比を計算中...")
    cur.execute("""
        SELECT rp.confidence, COUNT(*)
        FROM race_predictions rp
        JOIN races r ON rp.race_id = r.id
        WHERE rp.prediction_type = 'before'
          AND rp.rank_prediction  = 1
          AND r.race_date BETWEEN ? AND ?
          AND rp.confidence IS NOT NULL
        GROUP BY rp.confidence
        ORDER BY rp.confidence
    """, (IS_START, IS_END))
    cf_rows = cur.fetchall()
    cf_total = sum(r[1] for r in cf_rows)
    cf_pct = {r[0]: round(r[1] / cf_total * 100, 2) for r in cf_rows}
    print(f"  合計={cf_total:,}")
    for k, v in cf_pct.items():
        print(f"    {k}: {v}%")

    bands["b3_confidence_composition"] = {
        "description": "before rank=1 の信頼度構成比 (IS 2020-2025)",
        "source": "race_predictions (before, rank_prediction=1) + races, IS 2020-2025",
        "n_samples": cf_total,
        "composition_pct": cf_pct,
        "warn_tolerance_pt": 5.0,   # 各クラス ±5pt でWARN
        "note": (
            "特に A率 (22.7%) の急落 / 急騰はモデル or データ異常のシグナル。"
            "正常範囲: CLAUDE.md 定義 advance 2-6% / before 15-27% (A率 = before A%)。"
        )
    }

    # ---------------------------------------------------------------
    # B-4: 三連単的中率ベースライン
    #   - IS 2020-2025、confidence=A、オッズ 30-300x、before予測
    # ---------------------------------------------------------------
    print("[B-4] 三連単的中率を計算中（IS 2020-2025, confidence=A, odds 30-300x）...")
    cur.execute("""
        WITH preds AS (
            SELECT rp1.race_id,
                   rp1.pit_number AS p1_pit,
                   rp2.pit_number AS p2_pit,
                   rp3.pit_number AS p3_pit
            FROM race_predictions rp1
            JOIN race_predictions rp2
                ON rp1.race_id = rp2.race_id
               AND rp2.rank_prediction = 2
               AND rp2.prediction_type = 'before'
            JOIN race_predictions rp3
                ON rp1.race_id = rp3.race_id
               AND rp3.rank_prediction = 3
               AND rp3.prediction_type = 'before'
            JOIN races r ON rp1.race_id = r.id
            JOIN trifecta_odds t
                ON rp1.race_id = t.race_id
               AND t.combination = (
                   CAST(rp1.pit_number AS TEXT) || '-' ||
                   CAST(rp2.pit_number AS TEXT) || '-' ||
                   CAST(rp3.pit_number AS TEXT)
               )
            WHERE rp1.rank_prediction = 1
              AND rp1.prediction_type = 'before'
              AND rp1.confidence       = 'A'
              AND r.race_date BETWEEN ? AND ?
              AND t.odds BETWEEN 30 AND 300
        ),
        hits AS (
            SELECT p.race_id,
                   CASE
                       WHEN res1.rank = '1'
                        AND res2.rank = '2'
                        AND res3.rank = '3'
                       THEN 1 ELSE 0
                   END AS hit
            FROM preds p
            JOIN results res1 ON p.race_id = res1.race_id AND p.p1_pit = res1.pit_number
            JOIN results res2 ON p.race_id = res2.race_id AND p.p2_pit = res2.pit_number
            JOIN results res3 ON p.race_id = res3.race_id AND p.p3_pit = res3.pit_number
        )
        SELECT COUNT(*), SUM(hit), ROUND(SUM(hit)*100.0/COUNT(*), 4)
        FROM hits
    """, (IS_START, IS_END))
    b4_row = cur.fetchone()
    b4_n, b4_hits, b4_pct_val = b4_row
    print(f"  N={b4_n:,}  hits={b4_hits}  hit_rate={b4_pct_val}%")

    bands["b4_hit_rate"] = {
        "description": "三連単的中率ベースライン (IS 2020-2025, confidence=A, odds 30-300x)",
        "source": "race_predictions + results + trifecta_odds, IS 2020-2025",
        "n_samples": b4_n,
        "n_hits": int(b4_hits),
        "baseline_pct": b4_pct_val,
        "n_min_to_alert": 50,       # n<50 は帯域チェックをスキップ（CI が広すぎる）
        "ci_confidence": 0.90,
        "note": (
            "正規近似 90%CI を使用。"
            "ライブデータ (2026-05-19〜現在) は 0 hits / 19 confirmed — "
            "n<50 のためベースライン構築から除外。"
            "confidence=A & odds 30-300x のフィルターを揃えているが、"
            "条件別オッズレンジの差異は捨象している。"
        )
    }

    # ---------------------------------------------------------------
    # B-1: 条件発火率 (週次) — IS 2020-2025 バックテスト実績から推計
    # ---------------------------------------------------------------
    print("[B-1] 週次発火率ベースラインを計算中...")
    # IS バックテスト: 4906件/6年 = 818/年 = 15.7/週 (confirmed)
    # 2026ライブ: dismissed 含む total 181件/72日 = 17.6/週
    # ライブ dismissed/confirmed 比 = 83/98 ≈ 0.85

    # IS バックテストから confirmed を計算（race_predictions全体から上位条件の発火数推計）
    # bet_notifications が存在しない IS期間は直接の条件発火数が取れないため、
    # 2020-2025 バックテスト既知値 (4906件/6年) を使う
    IS_CONFIRMED_ANNUAL = 4906 / 6          # 818/年
    IS_CONFIRMED_WEEKLY = IS_CONFIRMED_ANNUAL / 52  # 15.7/週

    # Poisson 近似: σ = √μ → band = μ ± 2σ
    sigma = math.sqrt(IS_CONFIRMED_WEEKLY)
    band_lo = max(1.0, IS_CONFIRMED_WEEKLY - 2 * sigma)
    band_hi = IS_CONFIRMED_WEEKLY + 2 * sigma

    # dismissed は live観測から補正係数を適用
    DISMISSED_RATIO = 83 / 98              # live: 0.85
    TOTAL_WEEKLY_EXPECTED = IS_CONFIRMED_WEEKLY * (1 + DISMISSED_RATIO)

    print(f"  IS週次発火(confirmed)={IS_CONFIRMED_WEEKLY:.1f} ±{2*sigma:.1f}")
    print(f"  帯域: [{band_lo:.1f}, {band_hi:.1f}] 件/週")

    bands["b1_weekly_fire_rate"] = {
        "description": "週次発火率ベースライン (confirmed bet_notifications)",
        "source": (
            "IS 2020-2025 バックテスト実績 4906件/6年 = 818件/年 / 52週 = 15.7件/週; "
            "Poisson σ = sqrt(μ)。"
            "dismissed 比率は live 2026-05-19〜07-30 より 0.85 を使用。"
        ),
        "confirmed_weekly_mu": round(IS_CONFIRMED_WEEKLY, 2),
        "confirmed_weekly_sigma": round(sigma, 2),
        "confirmed_band_lo": round(band_lo, 1),
        "confirmed_band_hi": round(band_hi, 1),
        "dismissed_ratio": round(DISMISSED_RATIO, 2),
        "total_weekly_expected": round(TOTAL_WEEKLY_EXPECTED, 1),
        "warn_absolute_lo": 4,     # 絶対下限: これ未満は WARN
        "warn_absolute_hi": 40,    # 絶対上限: これ超えは WARN
        "note": (
            "バックテスト実績を μ 推計に使用。条件ポートフォリオが変わった場合は再構築が必要。"
            "直近4週の weekly confirmed 件数が帯域外で3週連続した場合 RED。"
        )
    }

    # ---------------------------------------------------------------
    # C-5: adjusted_weight 欠損率ベースライン (IS 2020-2025)
    # ---------------------------------------------------------------
    print("[C-5] adjusted_weight 欠損率を計算中...")
    cur.execute("""
        SELECT COUNT(*),
               SUM(CASE WHEN rd.adjusted_weight IS NULL THEN 1 ELSE 0 END)
        FROM race_details rd
        JOIN races r ON rd.race_id = r.id
        WHERE r.race_date BETWEEN ? AND ?
    """, (IS_START, IS_END))
    c5_total, c5_nulls = cur.fetchone()
    c5_null_pct = round(c5_nulls / c5_total * 100, 2)
    print(f"  total={c5_total:,}  nulls={c5_nulls:,}  null_rate={c5_null_pct}%")

    bands["c5_adjusted_weight_missing"] = {
        "description": "race_details.adjusted_weight 欠損率ベースライン (IS 2020-2025)",
        "source": "race_details + races, IS 2020-2025",
        "n_rows": c5_total,
        "n_nulls": int(c5_nulls),
        "baseline_null_pct": c5_null_pct,
        "warn_threshold_pct": 15.0,   # ベースラインの約2倍
        "red_threshold_pct": 25.0,
        "note": "直近30日の欠損率と比較。直近欠損率が著増した場合はデータ収集問題のシグナル。"
    }

    conn.close()

    # ---------------------------------------------------------------
    # メタデータ付与 + JSON 書き出し
    # ---------------------------------------------------------------
    metadata = {
        "built_at": datetime.now().isoformat(),
        "built_by": "build_invariant_bands.py",
        "is_range": {"start": IS_START, "end": IS_END},
        "holdout_note": (
            "holdout DB (2017-2019) はこのマシンに存在しない。"
            "全帯域は IS 2020-2025 から算出（単一ソース）。"
            "外挿の精度は holdout 分離なしのため若干過大。"
        ),
        "change_policy": (
            "帯域変更はユーザー承認 + 変更履歴 + findings 記録が必須。"
            "実績が帯域に収まらないからと帯域を広げるのは禁止。"
        ),
        "checks_coverage": {
            "b1": "weekly fire rate",
            "b2": "score distribution P10/P25/P50/P75/P90",
            "b3": "confidence composition A-E %",
            "b4": "trifecta hit rate (confidence=A, odds 30-300x)",
            "c5": "adjusted_weight missing rate"
        }
    }

    # コンテンツ部分 (ハッシュ対象) を構築
    content = {"_metadata": metadata, **bands}

    # ハッシュ計算 (_content_hash を除いて)
    canonical = json.dumps(content, ensure_ascii=False, sort_keys=True)
    content_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    content["_content_hash"] = content_hash

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(content, f, ensure_ascii=False, indent=2)

    print()
    print(f"[OK] 帯域ファイル書き出し: {OUTPUT_PATH}")
    print(f"     SHA256: {content_hash}")
    print()
    print("=== 帯域サマリー ===")
    print(f"B-1 週次発火(confirmed): μ={IS_CONFIRMED_WEEKLY:.1f} 帯域[{band_lo:.1f}, {band_hi:.1f}] 絶対WARNライン[4, 40]")
    print(f"B-2 スコアP25/P50/P75/P90: {p25}/{p50}/{p75}/{p90}  許容±{bands['b2_score_distribution']['warn_tolerance_pt']}pt")
    print(f"B-3 信頼度構成 A={cf_pct.get('A','?')}% B={cf_pct.get('B','?')}% C={cf_pct.get('C','?')}% D={cf_pct.get('D','?')}% E={cf_pct.get('E','?')}%  許容±5pt")
    print(f"B-4 的中率ベースライン: {b4_pct_val}% (N={b4_n:,})  n_min={bands['b4_hit_rate']['n_min_to_alert']}")
    print(f"C-5 adjusted_weight欠損率: {c5_null_pct}%  WARN>{bands['c5_adjusted_weight_missing']['warn_threshold_pct']}% RED>{bands['c5_adjusted_weight_missing']['red_threshold_pct']}%")
    print()
    print("Phase 1 完了。次: Phase 2 (invariant_watch.py) を実装。")


if __name__ == "__main__":
    main()
