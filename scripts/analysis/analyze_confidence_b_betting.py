"""
信頼度Bの最適な買い目分析

信頼度C/Dと同様に、オッズ範囲×1コース級別で高ROI条件を抽出
"""

import sys
from pathlib import Path
import sqlite3
import pandas as pd

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

DB_PATH = project_root / 'data' / 'boatrace.db'


def load_confidence_b_data():
    """信頼度Bの予測データをオッズ・級別情報とともに取得"""
    conn = sqlite3.connect(str(DB_PATH))

    # まず基本データを取得
    query = """
    SELECT
        p.race_id,
        p.pit_number,
        p.rank_prediction,
        p.total_score,
        p.confidence,
        r.venue_code,
        r.race_date,
        res.rank as actual_rank,
        e.racer_rank as c1_rank
    FROM race_predictions p
    JOIN races r ON p.race_id = r.id
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

    # race_idのリストを取得
    race_ids = df['race_id'].unique().tolist()

    if len(race_ids) == 0:
        conn.close()
        return df

    # 3連単オッズを取得（1着固定のみ）
    odds_query = f"""
    SELECT
        race_id,
        combination,
        odds
    FROM trifecta_odds
    WHERE race_id IN ({','.join(map(str, race_ids))})
      AND combination LIKE '1-%'
    """

    odds_df = pd.read_sql_query(odds_query, conn)
    conn.close()

    # 各レースの3連単平均オッズを計算
    avg_odds = odds_df.groupby('race_id')['odds'].mean().reset_index()
    avg_odds.columns = ['race_id', 'trifecta_avg']

    # データをマージ
    df = df.merge(avg_odds, on='race_id', how='left')

    return df


def analyze_by_c1_rank_and_odds(df):
    """1コース級別×オッズ範囲で分析"""
    print("=" * 100)
    print("信頼度B 1コース級別×オッズ範囲分析")
    print("=" * 100)

    # 1着予想のみ
    pred_1st = df[df['rank_prediction'] == 1].copy()

    # オッズデータがあるもののみ
    pred_1st = pred_1st[pred_1st['trifecta_avg'].notna()].copy()

    # actual_rankを数値に変換
    pred_1st['actual_rank'] = pd.to_numeric(pred_1st['actual_rank'], errors='coerce')

    print(f"\n総レース数: {len(pred_1st)}")
    print(f"全体的中率: {(pred_1st['actual_rank'] == 1).mean() * 100:.2f}%")
    print(f"平均3連単オッズ: {pred_1st['trifecta_avg'].mean():.1f}倍")

    # 1コース級別で分析
    for c1_rank in ['A1', 'A2', 'B1', 'B2']:
        rank_data = pred_1st[pred_1st['c1_rank'] == c1_rank].copy()

        if len(rank_data) == 0:
            continue

        print(f"\n{'=' * 100}")
        print(f"1コース級別: {c1_rank} (n={len(rank_data)})")
        print(f"{'=' * 100}")

        # オッズ範囲を定義
        odds_ranges = [
            (0, 10, '0-10倍'),
            (10, 15, '10-15倍'),
            (15, 20, '15-20倍'),
            (20, 25, '20-25倍'),
            (25, 30, '25-30倍'),
            (30, 40, '30-40倍'),
            (40, 50, '40-50倍'),
            (50, 60, '50-60倍'),
            (60, 80, '60-80倍'),
            (80, 100, '80-100倍'),
            (100, 150, '100-150倍'),
            (150, 200, '150-200倍'),
            (200, 300, '200-300倍'),
            (300, 500, '300-500倍'),
            (500, 999, '500倍以上'),
        ]

        results = []

        for min_odds, max_odds, label in odds_ranges:
            subset = rank_data[
                (rank_data['trifecta_avg'] >= min_odds) &
                (rank_data['trifecta_avg'] < max_odds)
            ]

            if len(subset) < 5:  # サンプル数が少ない場合はスキップ
                continue

            hit_count = (subset['actual_rank'].astype(int) == 1).sum()
            hit_rate = (subset['actual_rank'].astype(int) == 1).mean() * 100
            avg_odds = subset['trifecta_avg'].mean()

            # ROI計算（全通り買いと仮定）
            total_bet = len(subset) * 20  # 20通り買い
            total_return = hit_count * avg_odds * 100  # 的中時の払い戻し
            roi = (total_return / total_bet) * 100 if total_bet > 0 else 0

            results.append({
                'range': label,
                'count': len(subset),
                'hit_rate': hit_rate,
                'avg_odds': avg_odds,
                'roi': roi,
                'hit_count': hit_count
            })

        # 結果を表示（ROIが高い順）
        results_df = pd.DataFrame(results)
        if len(results_df) > 0:
            results_df = results_df.sort_values('roi', ascending=False)

            print(f"\n{'オッズ範囲':<20} {'レース数':>8} {'的中数':>8} {'的中率':>8} {'平均オッズ':>10} {'ROI':>8}")
            print("-" * 100)

            for _, row in results_df.iterrows():
                marker = ""
                if row['roi'] >= 150 and row['count'] >= 10:
                    marker = " [高ROI候補]"
                elif row['roi'] >= 120 and row['count'] >= 20:
                    marker = " [中ROI候補]"

                print(f"{row['range']:<20} {row['count']:>8} {row['hit_count']:>8} "
                      f"{row['hit_rate']:>7.2f}% {row['avg_odds']:>9.1f}倍 "
                      f"{row['roi']:>7.1f}%{marker}")


def analyze_score_ranges(df):
    """スコア範囲での分析"""
    print("\n" + "=" * 100)
    print("信頼度B スコア範囲分析")
    print("=" * 100)

    pred_1st = df[df['rank_prediction'] == 1].copy()
    pred_1st = pred_1st[pred_1st['trifecta_avg'].notna()].copy()

    # actual_rankを数値に変換
    pred_1st['actual_rank'] = pd.to_numeric(pred_1st['actual_rank'], errors='coerce')

    # スコア範囲を定義
    score_ranges = [
        (100, 105, '100-105'),
        (105, 110, '105-110'),
        (110, 115, '110-115'),
        (115, 120, '115-120'),
        (120, 999, '120以上'),
    ]

    print(f"\n{'スコア範囲':<15} {'レース数':>8} {'的中率':>8} {'平均オッズ':>10} {'ROI':>8}")
    print("-" * 80)

    for min_score, max_score, label in score_ranges:
        subset = pred_1st[
            (pred_1st['total_score'] >= min_score) &
            (pred_1st['total_score'] < max_score)
        ]

        if len(subset) < 5:
            continue

        hit_count = (subset['actual_rank'].astype(int) == 1).sum()
        hit_rate = (subset['actual_rank'].astype(int) == 1).mean() * 100
        avg_odds = subset['trifecta_avg'].mean()

        total_bet = len(subset) * 20
        total_return = hit_count * avg_odds * 100
        roi = (total_return / total_bet) * 100 if total_bet > 0 else 0

        print(f"{label:<15} {len(subset):>8} {hit_rate:>7.2f}% {avg_odds:>9.1f}倍 {roi:>7.1f}%")


def main():
    print("=" * 100)
    print("信頼度B 最適買い目分析")
    print("=" * 100)
    print("\n目的: 信頼度C/Dと同様に、高ROI条件を抽出")
    print()

    # データロード
    print("データロード中...")
    df = load_confidence_b_data()
    print(f"信頼度Bデータ: {len(df)}レース")

    if len(df) == 0:
        print("エラー: データが見つかりません")
        return

    # 分析実行
    analyze_by_c1_rank_and_odds(df)
    analyze_score_ranges(df)

    print("\n" + "=" * 100)
    print("分析完了")
    print("=" * 100)


if __name__ == '__main__':
    main()
