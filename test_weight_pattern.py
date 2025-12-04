"""
指定した重み配分でテストを実行
"""

import sys
import sqlite3
from src.analysis.race_predictor import RacePredictor
from src.analysis.dynamic_integration import DynamicIntegrator

def test_weight(pre_weight, before_weight, num_races=100):
    """指定した重みでテストを実行"""
    
    # 重みを設定
    DynamicIntegrator.DEFAULT_PRE_WEIGHT = pre_weight
    DynamicIntegrator.DEFAULT_BEFORE_WEIGHT = before_weight
    
    # 全条件を同じ重みに設定
    from src.analysis.dynamic_integration import IntegrationCondition
    DynamicIntegrator.CONDITION_WEIGHTS = {
        IntegrationCondition.NORMAL: (pre_weight, before_weight),
        IntegrationCondition.BEFOREINFO_CRITICAL: (pre_weight, before_weight),
        IntegrationCondition.PREINFO_RELIABLE: (pre_weight, before_weight),
        IntegrationCondition.UNCERTAIN: (pre_weight, before_weight),
    }
    
    # テストレース取得
    conn = sqlite3.connect('data/boatrace.db')
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
        LIMIT ?
    """, (num_races,))
    
    test_races = cursor.fetchall()
    
    # 実際の1着を取得するクエリを準備
    def get_actual_winner(race_id):
        cursor.execute("""
            SELECT pit_number 
            FROM results 
            WHERE race_id = ? AND rank = 1 AND is_invalid = 0
        """, (race_id,))
        result = cursor.fetchone()
        return result[0] if result else None
    
    # テスト実行
    predictor = RacePredictor(db_path='data/boatrace.db')
    
    integrated_correct = 0
    pre_only_correct = 0
    both_correct = 0
    both_wrong = 0
    integrated_only = 0
    pre_only = 0
    different_predictions = 0
    
    print(f"=" * 80)
    print(f"重み配分テスト: PRE {pre_weight:.0%} / BEFORE {before_weight:.0%}")
    print(f"テスト対象: {len(test_races)}レース")
    print(f"=" * 80)
    print()
    
    for i, (race_id, date, venue, race_no) in enumerate(test_races, 1):
        predictions = predictor.predict_race(race_id)
        if not predictions or len(predictions) < 2:
            continue
        
        # 統合予測の1位
        integrated_1st = predictions[0]['pit_number']
        
        # PRE単体の1位
        pre_sorted = sorted(predictions, key=lambda x: x.get('pre_score', 0), reverse=True)
        pre_1st = pre_sorted[0]['pit_number']
        
        # 実際の1着
        actual = get_actual_winner(race_id)
        if actual is None:
            continue
        
        # 判定
        int_hit = (integrated_1st == actual)
        pre_hit = (pre_1st == actual)
        
        if integrated_1st != pre_1st:
            different_predictions += 1
        
        if int_hit and pre_hit:
            both_correct += 1
        elif int_hit and not pre_hit:
            integrated_only += 1
        elif not int_hit and pre_hit:
            pre_only += 1
        else:
            both_wrong += 1
        
        if int_hit:
            integrated_correct += 1
        if pre_hit:
            pre_only_correct += 1
        
        if i % 20 == 0:
            print(f"進捗: {i}/{len(test_races)}")
    
    total = both_correct + integrated_only + pre_only + both_wrong
    
    print()
    print(f"=" * 80)
    print(f"結果サマリー")
    print(f"=" * 80)
    print(f"有効レース数: {total}")
    print()
    print(f"【的中率】")
    print(f"  統合予測: {integrated_correct}/{total} ({integrated_correct/total*100:.1f}%)")
    print(f"  PRE単体: {pre_only_correct}/{total} ({pre_only_correct/total*100:.1f}%)")
    print(f"  差分: {(integrated_correct-pre_only_correct)/total*100:+.1f}ポイント")
    print()
    print(f"【予測パターン】")
    print(f"  両方的中: {both_correct}レース ({both_correct/total*100:.1f}%)")
    print(f"  統合のみ的中: {integrated_only}レース ({integrated_only/total*100:.1f}%)")
    print(f"  PRE単体のみ的中: {pre_only}レース ({pre_only/total*100:.1f}%)")
    print(f"  両方外れ: {both_wrong}レース ({both_wrong/total*100:.1f}%)")
    print()
    print(f"【予測の違い】")
    print(f"  予測が異なるレース: {different_predictions}/{total} ({different_predictions/total*100:.1f}%)")
    print(f"=" * 80)
    print()
    
    conn.close()
    
    return {
        'total': total,
        'integrated_correct': integrated_correct,
        'pre_only_correct': pre_only_correct,
        'integrated_only': integrated_only,
        'pre_only': pre_only,
        'both_correct': both_correct,
        'both_wrong': both_wrong,
        'different_predictions': different_predictions
    }

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("使用法: python test_weight_pattern.py <PRE_WEIGHT> <BEFORE_WEIGHT> [NUM_RACES]")
        sys.exit(1)
    
    pre_w = float(sys.argv[1])
    before_w = float(sys.argv[2])
    num_races = int(sys.argv[3]) if len(sys.argv) > 3 else 100
    
    test_weight(pre_w, before_w, num_races)
