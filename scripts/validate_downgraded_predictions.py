"""
環境要因減点によりダウングレードされたC/D予想の的中率検証

信頼度Bから環境要因減点でC/Dにダウングレードされた予想が、
既存の戦略AのC/D条件で購入するのに適しているかを検証する
"""

import sys
from pathlib import Path
import sqlite3
import pandas as pd

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / 'src'))

from analysis.environmental_penalty import EnvironmentalPenaltySystem

DB_PATH = project_root / 'data' / 'boatrace.db'


def load_confidence_b_data():
    """信頼度Bの予測データを環境情報とともに取得"""
    conn = sqlite3.connect(str(DB_PATH))

    query = """
    SELECT
        p.race_id,
        p.pit_number,
        p.rank_prediction,
        p.total_score,
        p.confidence,
        r.venue_code,
        r.race_date,
        r.race_time,
        rc.weather,
        rc.wind_direction,
        rc.wind_speed,
        rc.wave_height,
        res.rank as actual_rank,
        e.racer_rank as c1_rank
    FROM race_predictions p
    JOIN races r ON p.race_id = r.id
    LEFT JOIN race_conditions rc ON p.race_id = rc.race_id
    LEFT JOIN results res ON p.race_id = res.race_id AND p.pit_number = res.pit_number
    LEFT JOIN entries e ON p.race_id = e.race_id AND e.pit_number = 1
    WHERE p.prediction_type = 'before'
      AND p.confidence = 'B'
      AND r.race_date LIKE '2025%'
      AND res.rank IS NOT NULL
      AND res.is_invalid = 0
    ORDER BY p.race_id, p.rank_prediction
    """

    df = pd.read_sql_query(query, conn)
    conn.close()

    return df


def apply_environmental_penalty(df):
    """環境要因減点を適用"""
    penalty_system = EnvironmentalPenaltySystem()

    adjusted_data = []

    for idx, row in df.iterrows():
        venue_code = row['venue_code'] if isinstance(row['venue_code'], str) else f"{row['venue_code']:02d}"

        result = penalty_system.should_accept_bet(
            venue_code=venue_code,
            race_time=row['race_time'] or '12:00',
            wind_direction=row['wind_direction'],
            wind_speed=row['wind_speed'],
            wave_height=row['wave_height'],
            weather=row['weather'],
            original_score=row['total_score'],
            min_threshold=0  # 閾値チェックなし
        )

        adjusted_data.append({
            'race_id': row['race_id'],
            'pit_number': row['pit_number'],
            'rank_prediction': row['rank_prediction'],
            'original_confidence': 'B',
            'adjusted_confidence': result['adjusted_confidence'],
            'penalty': result['penalty'],
            'original_score': row['total_score'],
            'adjusted_score': result['adjusted_score'],
            'actual_rank': row['actual_rank'],
            'c1_rank': row['c1_rank'],
            'venue_code': row['venue_code']
        })

    return pd.DataFrame(adjusted_data)


def analyze_by_confidence(df):
    """調整後の信頼度別に分析"""
    print("=" * 100)
    print("環境要因減点後の信頼度別分析")
    print("=" * 100)

    for conf in ['B', 'C', 'D']:
        subset = df[df['adjusted_confidence'] == conf]

        if len(subset) == 0:
            continue

        # 1着予想のみ
        pred_1st = subset[subset['rank_prediction'] == 1]

        # 的中率計算
        hit_rate = (pred_1st['actual_rank'].astype(int) == 1).mean() * 100

        print(f"\n【調整後 信頼度{conf}】")
        print(f"  総レース数: {len(pred_1st)}")
        print(f"  1着的中率: {hit_rate:.2f}%")
        print(f"  元信頼度からの割合: {len(pred_1st) / len(df[df['rank_prediction'] == 1]) * 100:.1f}%")

        # 1コース級別内訳
        if 'c1_rank' in pred_1st.columns:
            print(f"\n  【1コース級別内訳】")
            for rank in ['A1', 'A2', 'B1', 'B2']:
                rank_subset = pred_1st[pred_1st['c1_rank'] == rank]
                if len(rank_subset) > 0:
                    rank_hit_rate = (rank_subset['actual_rank'].astype(int) == 1).mean() * 100
                    print(f"    {rank}: {len(rank_subset)}レース, 的中率{rank_hit_rate:.2f}%")


def compare_with_original_confidence(df):
    """元の信頼度C/Dとの比較"""
    print("\n" + "=" * 100)
    print("元の信頼度C/Dとの比較")
    print("=" * 100)

    # 元の信頼度C/Dのデータを取得
    conn = sqlite3.connect(str(DB_PATH))

    query_original = """
    SELECT
        p.confidence,
        p.rank_prediction,
        res.rank as actual_rank,
        e.racer_rank as c1_rank
    FROM race_predictions p
    JOIN races r ON p.race_id = r.id
    LEFT JOIN results res ON p.race_id = res.race_id AND p.pit_number = res.pit_number
    LEFT JOIN entries e ON p.race_id = e.race_id AND e.pit_number = 1
    WHERE p.prediction_type = 'before'
      AND p.confidence IN ('C', 'D')
      AND r.race_date LIKE '2025%'
      AND res.rank IS NOT NULL
      AND res.is_invalid = 0
    """

    df_original = pd.read_sql_query(query_original, conn)
    conn.close()

    for conf in ['C', 'D']:
        print(f"\n【信頼度{conf}の比較】")

        # 元の信頼度C/D
        original = df_original[df_original['confidence'] == conf]
        original_1st = original[original['rank_prediction'] == 1]
        original_hit_rate = (original_1st['actual_rank'].astype(int) == 1).mean() * 100 if len(original_1st) > 0 else 0

        # ダウングレードされた信頼度C/D
        downgraded = df[df['adjusted_confidence'] == conf]
        downgraded_1st = downgraded[downgraded['rank_prediction'] == 1]
        downgraded_hit_rate = (downgraded_1st['actual_rank'].astype(int) == 1).mean() * 100 if len(downgraded_1st) > 0 else 0

        print(f"  元の信頼度{conf}:")
        print(f"    レース数: {len(original_1st)}")
        print(f"    的中率: {original_hit_rate:.2f}%")

        print(f"  Bからダウングレード:")
        print(f"    レース数: {len(downgraded_1st)}")
        print(f"    的中率: {downgraded_hit_rate:.2f}%")

        diff = downgraded_hit_rate - original_hit_rate
        print(f"  差分: {diff:+.2f}pt")

        if diff > 0:
            print(f"  → ダウングレード{conf}の方が的中率が高い（良好）")
        elif diff < -5:
            print(f"  → ダウングレード{conf}の方が的中率が大幅に低い（要注意）")
        else:
            print(f"  → ほぼ同等（問題なし）")


def analyze_by_c1_rank_and_odds_range(df):
    """1コース級別×オッズ範囲での分析（戦略A条件との照合）"""
    print("\n" + "=" * 100)
    print("戦略A条件との照合（1コース級別分析）")
    print("=" * 100)

    # 戦略AのC/D条件を参照
    strategy_conditions = {
        'C': [
            {'c1_rank': 'B1', 'description': 'C×B1×150-200倍'},
        ],
        'D': [
            {'c1_rank': 'B1', 'description': 'D×B1×200-300倍'},
            {'c1_rank': 'A1', 'description': 'D×A1×100-150倍'},
            {'c1_rank': 'A1', 'description': 'D×A1×200-300倍'},
            {'c1_rank': 'A2', 'description': 'D×A2×30-40倍'},
            {'c1_rank': 'A1', 'description': 'D×A1×40-50倍'},
            {'c1_rank': 'A1', 'description': 'D×A1×20-25倍'},
        ]
    }

    for conf in ['C', 'D']:
        subset = df[df['adjusted_confidence'] == conf]
        pred_1st = subset[subset['rank_prediction'] == 1]

        if len(pred_1st) == 0:
            continue

        print(f"\n【調整後 信頼度{conf}】")

        for rank in ['A1', 'A2', 'B1', 'B2']:
            rank_subset = pred_1st[pred_1st['c1_rank'] == rank]

            if len(rank_subset) == 0:
                continue

            hit_rate = (rank_subset['actual_rank'].astype(int) == 1).mean() * 100

            # 戦略Aに該当する条件があるか
            has_condition = any(cond.get('c1_rank') == rank for cond in strategy_conditions.get(conf, []))
            status = "✓ 戦略A対象" if has_condition else "✗ 戦略A対象外"

            print(f"  {rank}: {len(rank_subset)}レース, 的中率{hit_rate:.2f}% ({status})")


def main():
    print("=" * 100)
    print("環境要因減点によるダウングレード予想の的中率検証")
    print("=" * 100)
    print("\n【検証内容】")
    print("1. 信頼度Bから環境要因減点でC/Dにダウングレードされた予想の的中率")
    print("2. 元の信頼度C/Dとの比較")
    print("3. 戦略A条件との照合")
    print()

    # データロード
    print("データロード中...")
    df = load_confidence_b_data()
    print(f"信頼度Bデータ: {len(df)}レース")

    # 環境要因減点を適用
    print("\n環境要因減点適用中...")
    df_adjusted = apply_environmental_penalty(df)

    # 分布確認
    pred_1st = df_adjusted[df_adjusted['rank_prediction'] == 1]
    print(f"\n【調整後の信頼度分布】（1着予想のみ）")
    print(f"  信頼度B維持: {len(pred_1st[pred_1st['adjusted_confidence'] == 'B'])}レース ({len(pred_1st[pred_1st['adjusted_confidence'] == 'B']) / len(pred_1st) * 100:.1f}%)")
    print(f"  B→C降格: {len(pred_1st[pred_1st['adjusted_confidence'] == 'C'])}レース ({len(pred_1st[pred_1st['adjusted_confidence'] == 'C']) / len(pred_1st) * 100:.1f}%)")
    print(f"  B→D降格: {len(pred_1st[pred_1st['adjusted_confidence'] == 'D'])}レース ({len(pred_1st[pred_1st['adjusted_confidence'] == 'D']) / len(pred_1st) * 100:.1f}%)")

    # 分析実行
    analyze_by_confidence(df_adjusted)
    compare_with_original_confidence(df_adjusted)
    analyze_by_c1_rank_and_odds_range(df_adjusted)

    print("\n" + "=" * 100)
    print("検証完了")
    print("=" * 100)


if __name__ == '__main__':
    main()
