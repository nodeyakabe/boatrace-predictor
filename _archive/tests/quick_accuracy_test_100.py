"""
100レースでの精度比較テスト（約2-3分）
"""

import sqlite3
from src.analysis.race_predictor import RacePredictor

def main():
    print("=" * 80)
    print("精度比較テスト: 統合スコア vs PRE単体（100レース）")
    print("=" * 80)
    print()
    
    conn = sqlite3.connect('data/boatrace.db')
    predictor = RacePredictor(db_path='data/boatrace.db')
    
    # 最新100レース取得
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
        LIMIT 100
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
    
    for i, (race_id, race_date, venue, race_no) in enumerate(test_races):
        print(f"進捗: {i+1}/{len(test_races)}", end='\r')
        
        try:
            # 実際の結果
            cursor.execute("""
                SELECT pit_number, rank FROM results
                WHERE race_id = ? AND rank IS NOT NULL AND is_invalid = 0
                ORDER BY rank
            """, (race_id,))
            actual = cursor.fetchall()
            if not actual:
                continue
            actual_winner = actual[0][0]
            
            # 統合スコアで予測
            predictions = predictor.predict_race(race_id)
            if not predictions or len(predictions) == 0:
                errors += 1
                continue
            
            integrated_pred = predictions[0]['pit_number']
            
            # PRE単体での予測
            pre_only = sorted(predictions, key=lambda x: x.get('pre_score', 0), reverse=True)
            pre_pred = pre_only[0]['pit_number']
            
            # 的中判定
            if integrated_pred == actual_winner:
                integrated_win += 1
            if pre_pred == actual_winner:
                pre_only_win += 1
            
            # 3着以内判定
            actual_ranks = {p[0]: p[1] for p in actual}
            if actual_ranks.get(integrated_pred, 999) <= 3:
                integrated_top3 += 1
            if actual_ranks.get(pre_pred, 999) <= 3:
                pre_only_top3 += 1
            
            total += 1
            
            # 予測が異なる場合のみ詳細記録
            if integrated_pred != pre_pred:
                details.append({
                    'date': race_date,
                    'venue': venue,
                    'race_no': race_no,
                    'actual': actual_winner,
                    'integrated': integrated_pred,
                    'pre_only': pre_pred,
                    'int_hit': integrated_pred == actual_winner,
                    'pre_hit': pre_pred == actual_winner
                })
        
        except Exception as e:
            errors += 1
            continue
    
    conn.close()
    
    print()
    print()
    print("=" * 80)
    print("検証結果")
    print("=" * 80)
    print(f"総レース数: {total}")
    print(f"エラー数: {errors}")
    print()
    
    if total > 0:
        int_win_rate = (integrated_win / total) * 100
        int_top3_rate = (integrated_top3 / total) * 100
        pre_win_rate = (pre_only_win / total) * 100
        pre_top3_rate = (pre_only_top3 / total) * 100
        
        print("【統合スコア（動的統合 + 進入予測モデル）】")
        print(f"  1着的中: {integrated_win}/{total} ({int_win_rate:.2f}%)")
        print(f"  3着内的中: {integrated_top3}/{total} ({int_top3_rate:.2f}%)")
        print()
        print("【PRE単体スコア】")
        print(f"  1着的中: {pre_only_win}/{total} ({pre_win_rate:.2f}%)")
        print(f"  3着内的中: {pre_only_top3}/{total} ({pre_top3_rate:.2f}%)")
        print()
        print("【改善効果】")
        win_diff = int_win_rate - pre_win_rate
        top3_diff = int_top3_rate - pre_top3_rate
        print(f"  1着的中率: {win_diff:+.2f}ポイント")
        print(f"  3着内的中率: {top3_diff:+.2f}ポイント")
        print()
        
        print(f"予測が異なったレース: {len(details)}件 ({len(details)/total*100:.1f}%)")
        
        # 差が顕著なレースの詳細
        if details:
            print()
            print("【予測が異なったレースの内訳】")
            int_better = sum(1 for d in details if d['int_hit'] and not d['pre_hit'])
            pre_better = sum(1 for d in details if d['pre_hit'] and not d['int_hit'])
            both_wrong = sum(1 for d in details if not d['int_hit'] and not d['pre_hit'])
            
            print(f"  統合のみ的中: {int_better}件")
            print(f"  PRE単体のみ的中: {pre_better}件")
            print(f"  両方外れ: {both_wrong}件")
            
            # サンプル表示
            if int_better > 0:
                print()
                print("【統合のみ的中したレース（最大5件）】")
                shown = 0
                for d in details:
                    if d['int_hit'] and not d['pre_hit'] and shown < 5:
                        print(f"  {d['date']} {d['venue']} {d['race_no']}R: 実際{d['actual']}号 → 統合{d['integrated']}号◎ PRE{d['pre_only']}号×")
                        shown += 1
    
    print()
    print("=" * 80)

if __name__ == "__main__":
    main()
