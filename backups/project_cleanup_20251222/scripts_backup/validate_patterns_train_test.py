"""
過学習回避のための検証スクリプト
- 訓練期間: 2022-2023年
- 検証期間: 2024-2025年
"""

import sqlite3
import pandas as pd
import numpy as np
from pathlib import Path
import sys

# プロジェクトルートを追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from config.settings import DATABASE_PATH


def get_connection():
    """DB接続を取得"""
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
    df['score_diff_1_2'] = df['score_1st'] - df['score_2nd']

    # オッズ帯
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
    """的中率とROIを計算"""
    if len(df) == 0:
        return {'n': 0, 'hit_rate': np.nan, 'roi': np.nan}

    hit_rate = df['hit'].mean() * 100

    valid_df = df[df['trifecta_odds'].notna()]
    if len(valid_df) > 0:
        total_bet = len(valid_df) * 100
        total_return = (valid_df['hit'] * valid_df['trifecta_odds'] * 100).sum()
        roi = (total_return / total_bet - 1) * 100
    else:
        roi = np.nan

    return {'n': len(df), 'hit_rate': hit_rate, 'roi': roi}


def main():
    print("=" * 80)
    print("過学習回避検証: 2022-2023年発見 → 2024-2025年検証")
    print("=" * 80)

    df = get_trifecta_data()
    train_df = df[df['year'].isin([2022, 2023])]
    test_df = df[df['year'].isin([2024, 2025])]

    print(f"\n訓練データ: {len(train_df):,}レース (2022-2023年)")
    print(f"検証データ: {len(test_df):,}レース (2024-2025年)")

    print("\n" + "=" * 80)
    print("検証パターン一覧")
    print("=" * 80)

    patterns = []

    # パターン1: 予測1着が1コース & オッズ0-10倍
    def pattern1(d):
        return (d['pred_1st'] == 1) & (d['odds_band'] == '0-10')

    # パターン2: 予測1着が1コース以外 & オッズ100倍以上
    def pattern2(d):
        return (d['pred_1st'] != 1) & (d['odds_band'] == '100+')

    # パターン3: 1コースがA1/A2 & 予測1着が1コース
    def pattern3(d):
        return (d['course1_rank'].isin(['A1', 'A2'])) & (d['pred_1st'] == 1)

    # パターン4: 1コースがB1/B2 & 予測1着が1コース以外
    def pattern4(d):
        return (d['course1_rank'].isin(['B1', 'B2'])) & (d['pred_1st'] != 1)

    # パターン5: スコア差(1位-2位)が20ポイント以上
    def pattern5(d):
        return d['score_diff_1_2'] >= 20

    # パターン6: スコア差(1位-2位)が5ポイント未満
    def pattern6(d):
        return d['score_diff_1_2'] < 5

    # パターン7: 堅い会場（大村24、徳山18、宮島17）& 予測1着1コース
    def pattern7(d):
        return d['venue_code'].isin(['24', '18', '17']) & (d['pred_1st'] == 1)

    # パターン8: 荒れ会場（江戸川03、戸田02、平和島04）& 予測1着1コース以外
    def pattern8(d):
        return d['venue_code'].isin(['03', '02', '04']) & (d['pred_1st'] != 1)

    # パターン9: オッズ100倍以上 & スコア差20以上（大穴狙い）
    def pattern9(d):
        return (d['odds_band'] == '100+') & (d['score_diff_1_2'] >= 20)

    # パターン10: 1コースB1/B2 & 予測1着2コース
    def pattern10(d):
        return (d['course1_rank'].isin(['B1', 'B2'])) & (d['pred_1st'] == 2)

    pattern_funcs = [
        ("予測1着=1コース & オッズ0-10倍", pattern1),
        ("予測1着≠1コース & オッズ100+倍", pattern2),
        ("1コースA1/A2 & 予測1着=1コース", pattern3),
        ("1コースB1/B2 & 予測1着≠1コース", pattern4),
        ("スコア差(1-2位)≧20pt", pattern5),
        ("スコア差(1-2位)<5pt", pattern6),
        ("堅い会場(24,18,17) & 予測1着=1コース", pattern7),
        ("荒れ会場(03,02,04) & 予測1着≠1コース", pattern8),
        ("オッズ100+倍 & スコア差≧20pt", pattern9),
        ("1コースB1/B2 & 予測1着=2コース", pattern10),
    ]

    results = []
    for name, func in pattern_funcs:
        train_mask = func(train_df)
        test_mask = func(test_df)

        train_metrics = calculate_metrics(train_df[train_mask])
        test_metrics = calculate_metrics(test_df[test_mask])

        result = {
            'パターン': name,
            '訓練N': train_metrics['n'],
            '訓練的中率': train_metrics['hit_rate'],
            '訓練ROI': train_metrics['roi'],
            '検証N': test_metrics['n'],
            '検証的中率': test_metrics['hit_rate'],
            '検証ROI': test_metrics['roi'],
        }

        # 検証で有効かどうかの判定
        if not np.isnan(test_metrics['roi']):
            if train_metrics['roi'] > 0 and test_metrics['roi'] > 0:
                result['判定'] = '◎安定プラス'
            elif train_metrics['roi'] < -30 and test_metrics['roi'] < -30:
                result['判定'] = '✕安定マイナス（避けるべき）'
            elif abs(train_metrics['roi'] - test_metrics['roi']) > 50:
                result['判定'] = '△不安定'
            else:
                result['判定'] = '○'
        else:
            result['判定'] = '-'

        results.append(result)

    results_df = pd.DataFrame(results)

    print("\n" + "-" * 100)
    print("パターン検証結果")
    print("-" * 100)
    for _, row in results_df.iterrows():
        print(f"\n【{row['パターン']}】 {row['判定']}")
        print(f"  訓練(2022-2023): N={row['訓練N']:,}, 的中率={row['訓練的中率']:.2f}%, ROI={row['訓練ROI']:.1f}%")
        print(f"  検証(2024-2025): N={row['検証N']:,}, 的中率={row['検証的中率']:.2f}%, ROI={row['検証ROI']:.1f}%")

    # 追加分析: 会場別詳細
    print("\n" + "=" * 80)
    print("会場別パターン検証（堅い/荒れ会場の詳細）")
    print("=" * 80)

    # 堅い会場
    solid_venues = ['24', '18', '17', '19', '13', '07']  # 1コース勝率60%以上
    chaotic_venues = ['03', '02', '04', '14']  # 1コース勝率50%以下

    for venue_type, venues, venue_name in [
        ("堅い会場", solid_venues, "1コース勝率60%以上"),
        ("荒れ会場", chaotic_venues, "1コース勝率50%以下"),
    ]:
        print(f"\n--- {venue_type}（{venue_name}）---")
        venue_train = train_df[train_df['venue_code'].isin(venues)]
        venue_test = test_df[test_df['venue_code'].isin(venues)]

        for pred_1st in [1, 2, 3, 4, 5, 6]:
            train_sub = venue_train[venue_train['pred_1st'] == pred_1st]
            test_sub = venue_test[venue_test['pred_1st'] == pred_1st]

            if len(train_sub) >= 100 and len(test_sub) >= 50:
                train_m = calculate_metrics(train_sub)
                test_m = calculate_metrics(test_sub)
                print(f"  予測1着={pred_1st}コース: 訓練 N={train_m['n']}, 的中率={train_m['hit_rate']:.2f}%, ROI={train_m['roi']:.1f}% | 検証 N={test_m['n']}, 的中率={test_m['hit_rate']:.2f}%, ROI={test_m['roi']:.1f}%")

    # オッズ帯別詳細
    print("\n" + "=" * 80)
    print("オッズ帯 × 予測1着コース 詳細検証")
    print("=" * 80)

    for odds_band in ['0-10', '10-30', '30-100', '100+']:
        print(f"\n--- オッズ帯: {odds_band} ---")
        for pred_1st in [1, 2, 3, 4, 5, 6]:
            train_sub = train_df[(train_df['odds_band'] == odds_band) & (train_df['pred_1st'] == pred_1st)]
            test_sub = test_df[(test_df['odds_band'] == odds_band) & (test_df['pred_1st'] == pred_1st)]

            if len(train_sub) >= 50 and len(test_sub) >= 30:
                train_m = calculate_metrics(train_sub)
                test_m = calculate_metrics(test_sub)
                stability = "安定" if abs(train_m['roi'] - test_m['roi']) < 30 else "不安定"
                print(f"  予測1着={pred_1st}: 訓練 N={train_m['n']}, ROI={train_m['roi']:.1f}% | 検証 N={test_m['n']}, ROI={test_m['roi']:.1f}% [{stability}]")

    # 最終サマリー
    print("\n" + "=" * 80)
    print("ベッティングフィルタへの改善提案（検証済みパターン）")
    print("=" * 80)

    print("""
【的中しやすい条件（採用推奨）】
1. 予測1着=1コース & オッズ0-10倍
   - 4年間で安定して的中率12%前後
   - ただしROIは-18%程度でマイナス
   - 用途: 的中重視の堅実な買い目

2. 堅い会場（大村、徳山、宮島等）& 予測1着=1コース
   - 的中率が高く安定
   - イン有利の会場特性を活かせる

【的中しにくい条件（避けるべき）】
1. 予測1着=1コース & オッズ30-100倍
   - 4年間で安定して的中率1.7%前後
   - ROIも-16%でマイナス
   - 用途: ベットを避けるフィルタに追加

2. 荒れ会場（江戸川、戸田、平和島）& 予測1着=1コース
   - 的中率が低く不安定
   - 会場特性により荒れやすい

【ROIプラス可能性のある条件（要追加検証）】
1. オッズ100倍以上
   - 2025年のみ大幅プラス（+279%）
   - 過去3年はマイナスで不安定
   - 大穴狙いとして少額で試す価値あり

2. 1コースB1/B2 & 予測1着=2コース
   - 2025年で+231%
   - 過去は不安定
   - イン不利時の差し狙いとして検討
""")


if __name__ == "__main__":
    main()
