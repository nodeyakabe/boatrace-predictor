"""
オッズデータ不整合問題の緊急調査スクリプト
"""
import sqlite3
import pandas as pd

DB_PATH = r'c:\Users\User\Desktop\BR\BoatRace_package_20251115_172032\data\boatrace.db'

def investigate_race_data():
    conn = sqlite3.connect(DB_PATH)

    print("=" * 80)
    print("【調査1】該当2レースのrace_id特定")
    print("=" * 80)

    # race_id取得
    race_ids = pd.read_sql_query("""
        SELECT id, race_date, venue_code, race_number
        FROM races
        WHERE (race_date = '2026-01-18' AND venue_code = 18 AND race_number = 8)
           OR (race_date = '2026-01-15' AND venue_code = 24 AND race_number = 11)
        ORDER BY race_date DESC
    """, conn)
    print(race_ids)
    print()

    if len(race_ids) == 0:
        print("⚠️ 該当レースがDBに存在しません！")
        conn.close()
        return

    for _, row in race_ids.iterrows():
        race_id = row['id']
        race_date = row['race_date']
        venue_code = row['venue_code']
        race_number = row['race_number']

        print("=" * 80)
        print(f"【調査2】{race_date} venue={venue_code} R{race_number} (race_id={race_id}) の詳細")
        print("=" * 80)

        # 予想データ
        print("\n--- 予想データ (race_predictions) ---")
        predictions = pd.read_sql_query(f"""
            SELECT pit_number, rank_prediction, prediction_type
            FROM race_predictions
            WHERE race_id = '{race_id}' AND prediction_type = 'before'
            ORDER BY rank_prediction
        """, conn)
        print(predictions)

        if len(predictions) >= 3:
            pred_combination = f"{predictions.iloc[0]['pit_number']}-{predictions.iloc[1]['pit_number']}-{predictions.iloc[2]['pit_number']}"
            print(f"\n予想買い目: {pred_combination}")
        else:
            print("\n⚠️ 予想データが不足しています")
            pred_combination = None

        # 該当買い目のオッズ
        if pred_combination:
            print(f"\n--- 予想買い目 {pred_combination} のオッズ ---")
            target_odds = pd.read_sql_query(f"""
                SELECT combination, odds
                FROM trifecta_odds
                WHERE race_id = '{race_id}' AND combination = '{pred_combination}'
            """, conn)
            print(target_odds)
            if len(target_odds) == 0:
                print(f"⚠️ 買い目 {pred_combination} のオッズが存在しません！")

        # 全オッズデータ（サンプル20件）
        print(f"\n--- race_id={race_id} の全オッズデータ（最初の20件） ---")
        all_odds = pd.read_sql_query(f"""
            SELECT combination, odds
            FROM trifecta_odds
            WHERE race_id = '{race_id}'
            ORDER BY odds ASC
            LIMIT 20
        """, conn)
        print(all_odds)

        # オッズ総件数
        odds_count = pd.read_sql_query(f"""
            SELECT COUNT(*) as count FROM trifecta_odds WHERE race_id = '{race_id}'
        """, conn)
        print(f"\nオッズ総件数: {odds_count.iloc[0]['count']}")

        # 結果データ
        print("\n--- 結果データ (results) ---")
        results = pd.read_sql_query(f"""
            SELECT pit_number, rank
            FROM results
            WHERE race_id = '{race_id}'
            ORDER BY rank
        """, conn)
        print(results)

        if len(results) >= 3:
            actual_result = f"{results.iloc[0]['pit_number']}-{results.iloc[1]['pit_number']}-{results.iloc[2]['pit_number']}"
            print(f"\n実際の結果: {actual_result}")

            # 実結果のオッズも確認
            print(f"\n--- 実結果 {actual_result} のオッズ ---")
            actual_odds = pd.read_sql_query(f"""
                SELECT combination, odds
                FROM trifecta_odds
                WHERE race_id = '{race_id}' AND combination = '{actual_result}'
            """, conn)
            print(actual_odds)

        print("\n")

    print("=" * 80)
    print("【調査3】オッズの範囲確認（8倍前後のオッズ）")
    print("=" * 80)

    for _, row in race_ids.iterrows():
        race_id = row['id']
        race_date = row['race_date']
        venue_code = row['venue_code']
        race_number = row['race_number']

        print(f"\n{race_date} venue={venue_code} R{race_number}")
        odds_range = pd.read_sql_query(f"""
            SELECT combination, odds
            FROM trifecta_odds
            WHERE race_id = '{race_id}' AND odds BETWEEN 7.0 AND 9.0
            ORDER BY odds
        """, conn)
        print(odds_range)

    conn.close()

if __name__ == '__main__':
    investigate_race_data()
