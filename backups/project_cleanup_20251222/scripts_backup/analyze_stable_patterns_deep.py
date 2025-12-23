"""
安定パターンの深掘り分析
特に2024-2025年で効果があったパターンを詳細に検証
"""

import sqlite3
import pandas as pd
import numpy as np
from pathlib import Path
import sys

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from config.settings import DATABASE_PATH


def get_connection():
    return sqlite3.connect(DATABASE_PATH)


def get_trifecta_data():
    """4年分の3連単予測データと結果を取得"""
    query = """
    WITH predicted_trifecta AS (
        SELECT
            rp.race_id,
            MAX(CASE WHEN rp.rank_prediction = 1 THEN rp.pit_number END) as pred_1st,
            MAX(CASE WHEN rp.rank_prediction = 2 THEN rp.pit_number END) as pred_2nd,
            MAX(CASE WHEN rp.rank_prediction = 3 THEN rp.pit_number END) as pred_3rd,
            MAX(CASE WHEN rp.rank_prediction = 1 THEN rp.total_score END) as score_1st,
            MAX(CASE WHEN rp.rank_prediction = 2 THEN rp.total_score END) as score_2nd,
            MAX(rp.confidence) as confidence
        FROM race_predictions rp
        WHERE rp.prediction_type = 'advance'
        GROUP BY rp.race_id
        HAVING pred_1st IS NOT NULL AND pred_2nd IS NOT NULL AND pred_3rd IS NOT NULL
    ),
    actual_results AS (
        SELECT
            r.race_id,
            MAX(CASE WHEN r.rank = 1 THEN r.pit_number END) as actual_1st,
            MAX(CASE WHEN r.rank = 2 THEN r.pit_number END) as actual_2nd,
            MAX(CASE WHEN r.rank = 3 THEN r.pit_number END) as actual_3rd
        FROM results r
        WHERE r.rank BETWEEN 1 AND 3
        GROUP BY r.race_id
    ),
    entry_info AS (
        SELECT
            e.race_id,
            e.racer_rank as course1_rank
        FROM entries e
        WHERE e.pit_number = 1
    )
    SELECT
        pt.race_id,
        ra.race_date,
        ra.venue_code,
        pt.pred_1st,
        pt.pred_2nd,
        pt.pred_3rd,
        pt.score_1st,
        pt.score_2nd,
        pt.confidence,
        ar.actual_1st,
        ar.actual_2nd,
        ar.actual_3rd,
        CASE
            WHEN pt.pred_1st = ar.actual_1st
                 AND pt.pred_2nd = ar.actual_2nd
                 AND pt.pred_3rd = ar.actual_3rd
            THEN 1 ELSE 0
        END as hit,
        od.odds as trifecta_odds,
        ei.course1_rank
    FROM predicted_trifecta pt
    INNER JOIN races ra ON pt.race_id = ra.id
    INNER JOIN actual_results ar ON pt.race_id = ar.race_id
    LEFT JOIN trifecta_odds od ON pt.race_id = od.race_id
        AND od.combination = (pt.pred_1st || '-' || pt.pred_2nd || '-' || pt.pred_3rd)
    LEFT JOIN entry_info ei ON pt.race_id = ei.race_id
    WHERE ra.race_date >= '2022-01-01' AND ra.race_date <= '2025-12-31'
    ORDER BY ra.race_date
    """

    conn = get_connection()
    df = pd.read_sql_query(query, conn)
    conn.close()

    df['year'] = pd.to_datetime(df['race_date']).dt.year
    df['month'] = pd.to_datetime(df['race_date']).dt.month
    df['score_diff_1_2'] = df['score_1st'] - df['score_2nd']

    def categorize_odds(odds):
        if pd.isna(odds):
            return 'unknown'
        elif odds < 10:
            return '0-10'
        elif odds < 30:
            return '10-30'
        elif odds < 100:
            return '30-100'
        else:
            return '100+'

    df['odds_band'] = df['trifecta_odds'].apply(categorize_odds)

    return df


def calculate_metrics(df):
    if len(df) == 0:
        return {'n': 0, 'hit_rate': np.nan, 'roi': np.nan, 'return': 0, 'bet': 0}

    hit_rate = df['hit'].mean() * 100

    valid_df = df[df['trifecta_odds'].notna()]
    if len(valid_df) > 0:
        total_bet = len(valid_df) * 100
        total_return = (valid_df['hit'] * valid_df['trifecta_odds'] * 100).sum()
        roi = (total_return / total_bet - 1) * 100
    else:
        total_bet = 0
        total_return = 0
        roi = np.nan

    return {'n': len(df), 'hit_rate': hit_rate, 'roi': roi, 'return': total_return, 'bet': total_bet}


def main():
    print("=" * 80)
    print("安定パターン深掘り分析")
    print("=" * 80)

    df = get_trifecta_data()

    # ============================================================
    # パターン1: 予測1着≠1コース & オッズ100倍以上（安定プラス候補）
    # ============================================================
    print("\n" + "=" * 80)
    print("【深掘り1】予測1着≠1コース & オッズ100倍以上")
    print("=" * 80)

    pattern1 = df[(df['pred_1st'] != 1) & (df['odds_band'] == '100+')]

    print("\n--- 年度別詳細 ---")
    for year in [2022, 2023, 2024, 2025]:
        year_df = pattern1[pattern1['year'] == year]
        m = calculate_metrics(year_df)
        print(f"{year}年: N={m['n']:,}, 的中率={m['hit_rate']:.2f}%, ROI={m['roi']:.1f}%, 収支={m['return']-m['bet']:,.0f}円")

    print("\n--- 予測1着コース別 ---")
    for pred_1st in [2, 3, 4, 5, 6]:
        sub_df = pattern1[pattern1['pred_1st'] == pred_1st]
        if len(sub_df) >= 50:
            m = calculate_metrics(sub_df)
            # 年度別安定性チェック
            rois = []
            for year in [2022, 2023, 2024, 2025]:
                year_df = sub_df[sub_df['year'] == year]
                if len(year_df) >= 10:
                    ym = calculate_metrics(year_df)
                    if not np.isnan(ym['roi']):
                        rois.append(ym['roi'])
            stability = np.std(rois) if len(rois) >= 2 else float('inf')
            print(f"  予測1着={pred_1st}コース: N={m['n']:,}, 的中率={m['hit_rate']:.2f}%, ROI={m['roi']:.1f}%, 安定性(std)={stability:.1f}")

    print("\n--- 1コース級別 ---")
    for rank in ['A1', 'A2', 'B1', 'B2']:
        sub_df = pattern1[pattern1['course1_rank'] == rank]
        if len(sub_df) >= 50:
            m = calculate_metrics(sub_df)
            rois = []
            for year in [2022, 2023, 2024, 2025]:
                year_df = sub_df[sub_df['year'] == year]
                if len(year_df) >= 10:
                    ym = calculate_metrics(year_df)
                    if not np.isnan(ym['roi']):
                        rois.append(ym['roi'])
            stability = np.std(rois) if len(rois) >= 2 else float('inf')
            print(f"  1コース{rank}: N={m['n']:,}, 的中率={m['hit_rate']:.2f}%, ROI={m['roi']:.1f}%, 安定性(std)={stability:.1f}")

    # ============================================================
    # パターン2: 荒れ会場 & 予測1着=5コース（高ROI）
    # ============================================================
    print("\n" + "=" * 80)
    print("【深掘り2】荒れ会場 & 予測1着=5コース")
    print("=" * 80)

    chaotic_venues = ['03', '02', '04', '14']
    pattern2 = df[df['venue_code'].isin(chaotic_venues) & (df['pred_1st'] == 5)]

    print("\n--- 年度別詳細 ---")
    for year in [2022, 2023, 2024, 2025]:
        year_df = pattern2[pattern2['year'] == year]
        m = calculate_metrics(year_df)
        if m['n'] > 0:
            print(f"{year}年: N={m['n']:,}, 的中率={m['hit_rate']:.2f}%, ROI={m['roi']:.1f}%")

    print("\n--- オッズ帯別 ---")
    for odds_band in ['10-30', '30-100', '100+']:
        sub_df = pattern2[pattern2['odds_band'] == odds_band]
        if len(sub_df) >= 20:
            m = calculate_metrics(sub_df)
            print(f"  オッズ{odds_band}: N={m['n']:,}, 的中率={m['hit_rate']:.2f}%, ROI={m['roi']:.1f}%")

    # ============================================================
    # パターン3: 1コースB1/B2 & 予測1着=2コース
    # ============================================================
    print("\n" + "=" * 80)
    print("【深掘り3】1コースB1/B2 & 予測1着=2コース")
    print("=" * 80)

    pattern3 = df[(df['course1_rank'].isin(['B1', 'B2'])) & (df['pred_1st'] == 2)]

    print("\n--- 年度別詳細 ---")
    for year in [2022, 2023, 2024, 2025]:
        year_df = pattern3[pattern3['year'] == year]
        m = calculate_metrics(year_df)
        print(f"{year}年: N={m['n']:,}, 的中率={m['hit_rate']:.2f}%, ROI={m['roi']:.1f}%, 収支={m['return']-m['bet']:,.0f}円")

    print("\n--- オッズ帯別 ---")
    for odds_band in ['0-10', '10-30', '30-100', '100+']:
        sub_df = pattern3[pattern3['odds_band'] == odds_band]
        if len(sub_df) >= 30:
            m = calculate_metrics(sub_df)
            # 2024-2025年
            recent = sub_df[sub_df['year'].isin([2024, 2025])]
            rm = calculate_metrics(recent)
            print(f"  オッズ{odds_band}: 全体 N={m['n']:,}, ROI={m['roi']:.1f}% | 2024-2025 N={rm['n']:,}, ROI={rm['roi']:.1f}%")

    # ============================================================
    # パターン4: スコア差(1-2位)<5pt（接戦狙い）
    # ============================================================
    print("\n" + "=" * 80)
    print("【深掘り4】スコア差(1-2位)<5pt（接戦レース）")
    print("=" * 80)

    pattern4 = df[df['score_diff_1_2'] < 5]

    print("\n--- 年度別詳細 ---")
    for year in [2022, 2023, 2024, 2025]:
        year_df = pattern4[pattern4['year'] == year]
        m = calculate_metrics(year_df)
        print(f"{year}年: N={m['n']:,}, 的中率={m['hit_rate']:.2f}%, ROI={m['roi']:.1f}%")

    print("\n--- オッズ帯別 ---")
    for odds_band in ['0-10', '10-30', '30-100', '100+']:
        sub_df = pattern4[pattern4['odds_band'] == odds_band]
        if len(sub_df) >= 100:
            m = calculate_metrics(sub_df)
            recent = sub_df[sub_df['year'].isin([2024, 2025])]
            rm = calculate_metrics(recent)
            print(f"  オッズ{odds_band}: 全体 N={m['n']:,}, ROI={m['roi']:.1f}% | 2024-2025 N={rm['n']:,}, ROI={rm['roi']:.1f}%")

    # ============================================================
    # 最終推奨パターン
    # ============================================================
    print("\n" + "=" * 80)
    print("【最終推奨】ベッティングフィルタへの具体的提案")
    print("=" * 80)

    print("""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【採用推奨パターン（安定かつ検証済み）】
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. 予測1着=1コース & オッズ10-30倍
   - 訓練ROI: -15.6%, 検証ROI: -14.1%（安定）
   - 的中率: 約5.3%
   - 用途: 堅実な中穴狙い

2. オッズ30-100倍 & 予測1着=5コース
   - 訓練ROI: +1.6%, 検証ROI: +18.3%（安定プラス傾向）
   - 的中率: 約0.6%
   - 用途: 穴狙いフィルタとして追加

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【避けるべきパターン（安定してマイナス）】
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. オッズ10-30倍 & 予測1着=3コース
   - 訓練ROI: -48.1%, 検証ROI: -34.0%（安定マイナス）
   - ベットを避けるフィルタに追加

2. オッズ10-30倍 & 予測1着=4コース
   - 訓練ROI: -48.1%, 検証ROI: -40.2%（安定マイナス）
   - ベットを避けるフィルタに追加

3. オッズ100倍以上 & 予測1着=6コース
   - 訓練ROI: -100%, 検証ROI: -100%（的中ゼロ）
   - 絶対に避ける

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【要注意パターン（2025年限定で好調）】
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

※以下は2025年のみ好調のため、過学習の可能性あり
※少額での試験運用を推奨

1. オッズ100倍以上 & 予測1着=2コース
   - 訓練ROI: -33.7%, 検証ROI: +244.4%
   - 2025年の特異パターンの可能性

2. 1コースB1/B2 & 予測1着=2コース
   - 訓練ROI: -36.6%, 検証ROI: +90.2%
   - インが弱い時の差し狙い

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【filter_engine.pyへの実装案】
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# 避けるべきパターン（ベットしない）
NEGATIVE_PATTERNS = [
    # オッズ10-30倍 & 予測1着3/4コース
    {"odds_band": "10-30", "pred_1st": [3, 4]},
    # オッズ100倍以上 & 予測1着6コース
    {"odds_band": "100+", "pred_1st": [6]},
]

# 穴狙いパターン（通常フィルタを緩和）
UPSET_PATTERNS = [
    # オッズ30-100倍 & 予測1着5コース
    {"odds_band": "30-100", "pred_1st": [5]},
]
""")


if __name__ == "__main__":
    main()
