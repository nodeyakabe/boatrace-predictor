"""
予測が変わったレースの詳細分析
なぜBEFORE_SCOREが間違った方向に導いたのかを調査
"""

import sqlite3
from src.analysis.race_predictor import RacePredictor
from src.analysis.dynamic_integration import DynamicIntegrator, IntegrationCondition

def analyze_changes(pre_weight, before_weight, num_races=30):
    """予測が変わったレースを詳細分析"""
    
    # 重み設定
    DynamicIntegrator.DEFAULT_PRE_WEIGHT = pre_weight
    DynamicIntegrator.DEFAULT_BEFORE_WEIGHT = before_weight
    DynamicIntegrator.CONDITION_WEIGHTS = {
        IntegrationCondition.NORMAL: (pre_weight, before_weight),
        IntegrationCondition.BEFOREINFO_CRITICAL: (pre_weight, before_weight),
        IntegrationCondition.PREINFO_RELIABLE: (pre_weight, before_weight),
        IntegrationCondition.UNCERTAIN: (pre_weight, before_weight),
    }
    
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
    
    def get_actual_winner(race_id):
        cursor.execute("""
            SELECT pit_number 
            FROM results 
            WHERE race_id = ? AND rank = 1 AND is_invalid = 0
        """, (race_id,))
        result = cursor.fetchone()
        return result[0] if result else None
    
    predictor = RacePredictor(db_path='data/boatrace.db')
    
    print("=" * 80)
    print(f"予測変更レースの詳細分析: PRE {pre_weight:.0%} / BEFORE {before_weight:.0%}")
    print("=" * 80)
    print()
    
    changed_races = []
    
    for race_id, date, venue, race_no in test_races:
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
        
        # 予測が変わった場合のみ分析
        if integrated_1st != pre_1st:
            int_hit = (integrated_1st == actual)
            pre_hit = (pre_1st == actual)
            
            # 統合1位の詳細
            int_1st_pred = predictions[0]
            
            # PRE1位の詳細を探す
            pre_1st_pred = None
            for p in predictions:
                if p['pit_number'] == pre_1st:
                    pre_1st_pred = p
                    break
            
            changed_races.append({
                'race_id': race_id,
                'date': date,
                'venue': venue,
                'race_no': race_no,
                'actual': actual,
                'integrated_1st': integrated_1st,
                'pre_1st': pre_1st,
                'int_hit': int_hit,
                'pre_hit': pre_hit,
                'int_1st_pred': int_1st_pred,
                'pre_1st_pred': pre_1st_pred
            })
    
    print(f"予測が変わったレース: {len(changed_races)}件\n")
    
    # 詳細表示
    for i, race in enumerate(changed_races, 1):
        print(f"【レース{i}: {race['date']} {race['venue']} {race['race_no']}R (ID: {race['race_id']})】")
        print(f"実際の1着: {race['actual']}号艇")
        print()
        
        print(f"統合予測1位: {race['integrated_1st']}号艇", end="")
        if race['int_hit']:
            print(" [的中]")
        else:
            print(" [外れ]")
        
        int_pred = race['int_1st_pred']
        print(f"  total_score: {int_pred.get('total_score', 0):.2f}")
        print(f"  pre_score: {int_pred.get('pre_score', 0):.2f}")
        print(f"  beforeinfo_score: {int_pred.get('beforeinfo_score', 0):.2f}")
        print()
        
        print(f"PRE単体1位: {race['pre_1st']}号艇", end="")
        if race['pre_hit']:
            print(" [的中]")
        else:
            print(" [外れ]")
        
        if race['pre_1st_pred']:
            pre_pred = race['pre_1st_pred']
            print(f"  total_score: {pre_pred.get('total_score', 0):.2f}")
            print(f"  pre_score: {pre_pred.get('pre_score', 0):.2f}")
            print(f"  beforeinfo_score: {pre_pred.get('beforeinfo_score', 0):.2f}")
        print()
        
        # なぜ逆転したのか分析
        if race['pre_1st_pred']:
            pre_diff = int_pred.get('pre_score', 0) - race['pre_1st_pred'].get('pre_score', 0)
            before_diff = int_pred.get('beforeinfo_score', 0) - race['pre_1st_pred'].get('beforeinfo_score', 0)
            
            print(f"【逆転の理由】")
            print(f"  PRE_SCORE差: {pre_diff:+.2f}点 ({race['integrated_1st']}号 - {race['pre_1st']}号)")
            print(f"  BEFORE_SCORE差: {before_diff:+.2f}点 ({race['integrated_1st']}号 - {race['pre_1st']}号)")
            print(f"  重み適用後のBEFORE影響: {before_diff * before_weight:+.2f}点")
            
            if before_diff > 0:
                print(f"  → {race['integrated_1st']}号のBEFORE_SCOREが高くて逆転")
            else:
                print(f"  → {race['pre_1st']}号のBEFORE_SCOREが低くて{race['integrated_1st']}号が浮上")
        
        print()
        print("-" * 80)
        print()
    
    # サマリー
    int_correct = sum(1 for r in changed_races if r['int_hit'])
    pre_correct = sum(1 for r in changed_races if r['pre_hit'])
    
    print("=" * 80)
    print("サマリー")
    print("=" * 80)
    print(f"予測が変わったレース数: {len(changed_races)}")
    print(f"統合予測の的中: {int_correct}/{len(changed_races)} ({int_correct/len(changed_races)*100 if changed_races else 0:.1f}%)")
    print(f"PRE単体の的中: {pre_correct}/{len(changed_races)} ({pre_correct/len(changed_races)*100 if changed_races else 0:.1f}%)")
    print()
    print(f"【結論】")
    if int_correct > pre_correct:
        print(f"  BEFORE_SCOREは有効！ (+{int_correct - pre_correct}レース改善)")
    elif int_correct < pre_correct:
        print(f"  BEFORE_SCOREは逆効果... (-{pre_correct - int_correct}レース悪化)")
    else:
        print(f"  BEFORE_SCOREは影響なし（±0レース）")
    
    print("=" * 80)
    
    conn.close()

if __name__ == "__main__":
    # PRE 70% / BEFORE 30%で分析（最も良好だった配分）
    analyze_changes(0.7, 0.3, 30)
