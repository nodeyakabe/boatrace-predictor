"""
10レースでの新機能検証テスト
"""

import sqlite3
from src.analysis.race_predictor import RacePredictor
import time

def main():
    print("=" * 80)
    print("新機能検証テスト: 10レース")
    print("=" * 80)
    print()
    
    conn = sqlite3.connect('data/boatrace.db')
    predictor = RacePredictor(db_path='data/boatrace.db')
    
    # 最新10レース取得
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT r.id, r.race_date, r.venue_code, r.race_number
        FROM races r
        JOIN race_details rd ON r.id = rd.race_id
        JOIN results res ON r.id = res.race_id
        WHERE rd.exhibition_course IS NOT NULL
        AND res.rank IS NOT NULL
        AND res.is_invalid = 0
        ORDER BY r.race_date DESC, r.id DESC
        LIMIT 10
    """)
    
    test_races = cursor.fetchall()
    print(f"検証対象: {len(test_races)}レース")
    print()
    
    # 統計
    integrated_win = 0
    integrated_top3 = 0
    pre_only_win = 0
    pre_only_top3 = 0
    total = 0
    errors = 0
    
    details = []
    total_time = 0
    
    for i, (race_id, race_date, venue, race_no) in enumerate(test_races):
        print(f"\n[{i+1}/{len(test_races)}] {race_date} {venue} {race_no}R (ID: {race_id})")
        
        try:
            # 実際の結果
            cursor.execute("""
                SELECT pit_number, rank FROM results
                WHERE race_id = ? AND rank IS NOT NULL AND is_invalid = 0
                ORDER BY rank
            """, (race_id,))
            actual = cursor.fetchall()
            if not actual:
                print("  → 結果データなし")
                continue
            actual_winner = actual[0][0]
            
            # 統合スコアで予測（時間計測）
            start = time.time()
            predictions = predictor.predict_race(race_id)
            elapsed = time.time() - start
            total_time += elapsed
            
            if not predictions or len(predictions) == 0:
                print(f"  → 予測エラー ({elapsed:.1f}秒)")
                errors += 1
                continue
            
            integrated_pred = predictions[0]['pit_number']
            
            # PRE単体での予測
            pre_only = sorted(predictions, key=lambda x: x.get('pre_score', 0), reverse=True)
            pre_pred = pre_only[0]['pit_number']
            
            # 的中判定
            int_hit = integrated_pred == actual_winner
            pre_hit = pre_pred == actual_winner
            
            if int_hit:
                integrated_win += 1
            if pre_hit:
                pre_only_win += 1
            
            # 3着以内判定
            actual_ranks = {p[0]: p[1] for p in actual}
            if actual_ranks.get(integrated_pred, 999) <= 3:
                integrated_top3 += 1
            if actual_ranks.get(pre_pred, 999) <= 3:
                pre_only_top3 += 1
            
            total += 1
            
            # 結果表示
            int_mark = '◎' if int_hit else '×'
            pre_mark = '◎' if pre_hit else '×'
            
            print(f"  実際の1着: {actual_winner}号")
            print(f"  統合予測: {integrated_pred}号 {int_mark} (スコア: {predictions[0]['total_score']:.1f})")
            print(f"  PRE予測: {pre_pred}号 {pre_mark}")
            print(f"  処理時間: {elapsed:.1f}秒")
            
            # 予測が異なる場合は詳細記録
            if integrated_pred != pre_pred:
                details.append({
                    'date': race_date,
                    'venue': venue,
                    'race_no': race_no,
                    'actual': actual_winner,
                    'integrated': integrated_pred,
                    'pre_only': pre_pred,
                    'int_hit': int_hit,
                    'pre_hit': pre_hit
                })
        
        except Exception as e:
            print(f"  → エラー: {e}")
            errors += 1
            continue
    
    conn.close()
    
    # 最終結果
    print()
    print("=" * 80)
    print("検証結果サマリー")
    print("=" * 80)
    print(f"総レース数: {total}")
    print(f"エラー数: {errors}")
    print(f"平均処理時間: {total_time/total if total > 0 else 0:.1f}秒/レース")
    print()
    
    if total > 0:
        int_win_rate = (integrated_win / total) * 100
        int_top3_rate = (integrated_top3 / total) * 100
        pre_win_rate = (pre_only_win / total) * 100
        pre_top3_rate = (pre_only_top3 / total) * 100
        
        print("【統合スコア（動的統合 + 進入予測モデル）】")
        print(f"  1着的中: {integrated_win}/{total} ({int_win_rate:.1f}%)")
        print(f"  3着内的中: {integrated_top3}/{total} ({int_top3_rate:.1f}%)")
        print()
        print("【PRE単体スコア】")
        print(f"  1着的中: {pre_only_win}/{total} ({pre_win_rate:.1f}%)")
        print(f"  3着内的中: {pre_only_top3}/{total} ({pre_top3_rate:.1f}%)")
        print()
        print("【改善効果】")
        win_diff = int_win_rate - pre_win_rate
        top3_diff = int_top3_rate - pre_top3_rate
        print(f"  1着的中率: {win_diff:+.1f}ポイント")
        print(f"  3着内的中率: {top3_diff:+.1f}ポイント")
        print()
        
        if details:
            print(f"予測が異なったレース: {len(details)}件")
            print()
            print("【統合とPREで予測が異なったレース】")
            for d in details:
                int_mark = '◎' if d['int_hit'] else '×'
                pre_mark = '◎' if d['pre_hit'] else '×'
                print(f"  {d['date']} {d['venue']} {d['race_no']}R: 実際{d['actual']}号 → 統合{d['integrated']}号{int_mark} / PRE{d['pre_only']}号{pre_mark}")
    
    print()
    print("=" * 80)

if __name__ == "__main__":
    main()
