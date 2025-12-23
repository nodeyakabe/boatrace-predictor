"""信頼度B分析結果の要約を表示"""
import sqlite3
import pandas as pd
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "boatrace.db"

def main():
    conn = sqlite3.connect(DB_PATH)

    # 信頼度Bのレースを取得
    query = '''
        SELECT
            r.id as race_id,
            rp.pit_number,
            rp.total_score,
            rp.rank_prediction,
            res.rank as actual_rank,
            to3.odds as trifecta_odds
        FROM races r
        JOIN race_predictions rp ON r.id = rp.race_id
        LEFT JOIN results res ON r.id = res.race_id AND rp.pit_number = res.pit_number
        LEFT JOIN (
            SELECT race_id, combination, odds
            FROM trifecta_odds
        ) to3 ON r.id = to3.race_id
        WHERE r.race_date >= '2024-01-01'
          AND r.race_date < '2026-01-01'
          AND rp.prediction_type = 'advance'
          AND rp.confidence = 'B'
    '''

    df = pd.read_sql_query(query, conn)

    print("=" * 80)
    print("信頼度B予想の分析結果")
    print("=" * 80)
    print(f"\n対象レース数: {df['race_id'].nunique():,}レース")
    print(f"対象予想データ数: {len(df):,}件")

    # スコアリング精度分析
    print("\n" + "=" * 80)
    print("1. スコアリング精度（実際の着順とスコア順位の関係）")
    print("=" * 80)

    # 各着順の艇のスコア順位分布
    for rank in [1, 2, 3]:
        rank_df = df[df['actual_rank'] == rank]
        print(f"\n実際の{rank}着艇のスコア順位:")
        for score_rank in range(1, 7):
            count = len(rank_df[rank_df['rank_prediction'] == score_rank])
            pct = count / len(rank_df) * 100 if len(rank_df) > 0 else 0
            print(f"  スコア{score_rank}位: {count:4d}レース ({pct:5.1f}%)")

    # 三連単的中率の計算
    print("\n" + "=" * 80)
    print("2. 三連単的中率")
    print("=" * 80)

    # 各レースで予想1-2-3位と実際の1-2-3位を比較
    race_results = []
    for race_id in df['race_id'].unique():
        race_data = df[df['race_id'] == race_id].copy()

        # 予想上位3艇
        predicted = race_data.nsmallest(3, 'rank_prediction')['pit_number'].tolist()
        if len(predicted) < 3:
            continue

        # 実際の1-2-3着
        actual = race_data[race_data['actual_rank'].isin([1, 2, 3])].sort_values('actual_rank')['pit_number'].tolist()
        if len(actual) < 3:
            continue

        # 三連単的中判定
        is_hit = (predicted == actual)

        # 実際のオッズ取得
        actual_combo = f"{actual[0]}-{actual[1]}-{actual[2]}"
        odds_data = race_data[race_data['pit_number'] == predicted[0]]

        race_results.append({
            'race_id': race_id,
            'is_hit': is_hit,
            'predicted': predicted,
            'actual': actual
        })

    hits = sum(1 for r in race_results if r['is_hit'])
    total = len(race_results)
    hit_rate = hits / total * 100 if total > 0 else 0

    print(f"\n三連単的中: {hits}/{total}レース = {hit_rate:.2f}%")
    print(f"ランダム期待値: 0.83%")
    print(f"改善倍率: {hit_rate / 0.83:.1f}倍")

    # スコア下位艇の分析
    print("\n" + "=" * 80)
    print("3. スコア下位艇（4-6位）の3連単への関与")
    print("=" * 80)

    # 実際の三連単にスコア4-6位が含まれるレース数
    races_with_lower_in_result = 0
    races_with_lower_in_prediction = 0

    for race_id in df['race_id'].unique():
        race_data = df[df['race_id'] == race_id].copy()

        # 実際の1-2-3着
        actual_top3 = race_data[race_data['actual_rank'].isin([1, 2, 3])]['pit_number'].tolist()

        # 予想1-2-3位
        predicted_top3 = race_data.nsmallest(3, 'rank_prediction')['pit_number'].tolist()

        # スコア4-6位の艇
        lower_scored = race_data[race_data['rank_prediction'] >= 4]['pit_number'].tolist()

        # スコア下位が実際の三連単に含まれるか
        if any(pit in actual_top3 for pit in lower_scored):
            races_with_lower_in_result += 1

        # スコア下位を予想に含んでいるか
        if any(pit in predicted_top3 for pit in lower_scored):
            races_with_lower_in_prediction += 1

    total_races = df['race_id'].nunique()
    print(f"\n実際の三連単にスコア下位艇（4-6位）が含まれる:")
    print(f"  {races_with_lower_in_result}/{total_races}レース ({races_with_lower_in_result/total_races*100:.1f}%)")

    print(f"\n予想にスコア下位艇（4-6位）を含む:")
    print(f"  {races_with_lower_in_prediction}/{total_races}レース ({races_with_lower_in_prediction/total_races*100:.1f}%)")

    # 不的中レースの分析
    print("\n" + "=" * 80)
    print("4. 的中・不的中レースの比較")
    print("=" * 80)

    # 的中レースと不的中レースで払戻金を比較
    hit_races = [r['race_id'] for r in race_results if r['is_hit']]
    miss_races = [r['race_id'] for r in race_results if not r['is_hit']]

    print(f"\n的中レース: {len(hit_races)}レース")
    print(f"不的中レース: {len(miss_races)}レース")

    # オッズ情報の取得
    cursor = conn.cursor()

    # 的中時のオッズ
    if hit_races:
        placeholders = ','.join(['?'] * len(hit_races))
        cursor.execute(f'''
            SELECT AVG(odds) as avg_odds, MIN(odds) as min_odds, MAX(odds) as max_odds
            FROM trifecta_odds
            WHERE race_id IN ({placeholders})
        ''', hit_races)
        hit_odds = cursor.fetchone()
        print(f"\n的中レースの払戻金:")
        print(f"  平均: {hit_odds[0]:.2f}倍" if hit_odds[0] else "  データなし")
        print(f"  最小: {hit_odds[1]:.2f}倍" if hit_odds[1] else "")
        print(f"  最大: {hit_odds[2]:.2f}倍" if hit_odds[2] else "")

    # 不的中時のオッズ分布
    if miss_races:
        placeholders = ','.join(['?'] * len(miss_races))
        cursor.execute(f'''
            SELECT AVG(odds) as avg_odds, MIN(odds) as min_odds, MAX(odds) as max_odds
            FROM trifecta_odds
            WHERE race_id IN ({placeholders})
        ''', miss_races[:100])  # 最初の100件のみ
        miss_odds = cursor.fetchone()
        print(f"\n不的中レースの払戻金（サンプル）:")
        print(f"  平均: {miss_odds[0]:.2f}倍" if miss_odds[0] else "  データなし")
        print(f"  最小: {miss_odds[1]:.2f}倍" if miss_odds[1] else "")
        print(f"  最大: {miss_odds[2]:.2f}倍" if miss_odds[2] else "")

    conn.close()
    print("\n" + "=" * 80)
    print("分析完了")
    print("=" * 80)

if __name__ == "__main__":
    main()
