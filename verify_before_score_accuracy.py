"""
BEFORE_SCOREの各項目の予測精度を検証
"""

import sqlite3
from src.analysis.beforeinfo_scorer import BeforeInfoScorer

def verify_before_score_components():
    """各項目が実際の結果と相関しているか検証"""
    
    conn = sqlite3.connect('data/boatrace.db')
    cursor = conn.cursor()
    
    # 最新100レース取得
    cursor.execute("""
        SELECT DISTINCT r.id
        FROM races r
        JOIN race_details rd ON r.id = rd.race_id
        JOIN results res ON r.id = res.race_id
        WHERE rd.exhibition_course IS NOT NULL
        AND res.rank IS NOT NULL
        AND res.is_invalid = 0
        ORDER BY r.race_date DESC, r.id DESC
        LIMIT 100
    """)
    
    race_ids = [row[0] for row in cursor.fetchall()]
    
    scorer = BeforeInfoScorer(db_path='data/boatrace.db')
    
    # 統計データ
    stats = {
        'total_score': {'wins': 0, 'total': 0},
        'exhibition_time_score': {'wins': 0, 'total': 0},
        'st_score': {'wins': 0, 'total': 0},
        'entry_score': {'wins': 0, 'total': 0},
        'prev_race_score': {'wins': 0, 'total': 0},
        'tilt_wind_score': {'wins': 0, 'total': 0},
        'parts_weight_score': {'wins': 0, 'total': 0},
    }
    
    print("=" * 80)
    print("BEFORE_SCOREの各項目精度検証")
    print("=" * 80)
    print()
    
    for race_id in race_ids:
        # 各艇のBEFORE_SCORE取得
        cursor.execute("""
            SELECT pit_number 
            FROM results 
            WHERE race_id = ? AND is_invalid = 0
            ORDER BY pit_number
        """, (race_id,))
        
        pits = [row[0] for row in cursor.fetchall()]
        if len(pits) < 6:
            continue
        
        # 実際の1着を取得
        cursor.execute("""
            SELECT pit_number 
            FROM results 
            WHERE race_id = ? AND rank = 1 AND is_invalid = 0
        """, (race_id,))
        
        result = cursor.fetchone()
        if not result:
            continue
        
        actual_winner = result[0]
        
        # 各艇のスコア計算
        scores_by_pit = {}
        for pit in pits:
            score = scorer.calculate_beforeinfo_score(race_id, pit)
            if score:
                scores_by_pit[pit] = score
        
        if len(scores_by_pit) < 3:
            continue
        
        # 各項目で最高スコアの艇が実際に勝ったか確認
        for key in stats.keys():
            # その項目で最高スコアの艇を見つける
            max_pit = None
            max_value = float('-inf')
            
            for pit, score in scores_by_pit.items():
                value = score.get(key, 0)
                if value > max_value:
                    max_value = value
                    max_pit = pit
            
            if max_pit is not None:
                stats[key]['total'] += 1
                if max_pit == actual_winner:
                    stats[key]['wins'] += 1
    
    # 結果表示
    print(f"検証レース数: {stats['total_score']['total']}")
    print()
    print("【各項目の的中率】")
    print(f"（その項目で最高スコアの艇が実際に1着になった確率）")
    print()
    
    for key, data in sorted(stats.items(), key=lambda x: x[1]['wins']/max(x[1]['total'],1), reverse=True):
        total = data['total']
        wins = data['wins']
        accuracy = wins / total * 100 if total > 0 else 0
        
        key_name = {
            'total_score': '合計スコア',
            'exhibition_time_score': '展示タイム',
            'st_score': 'スタートタイミング',
            'entry_score': '進入コース',
            'prev_race_score': '前走成績',
            'tilt_wind_score': 'チルト・風',
            'parts_weight_score': '部品交換・体重'
        }.get(key, key)
        
        print(f"  {key_name:20s}: {wins:3d}/{total:3d} ({accuracy:5.1f}%)")
    
    print()
    print("【参考】ランダム予測: 約16.7% (6艇中1艇)")
    print("【参考】1号艇固定予測: 約50-55%")
    print()
    print("=" * 80)
    
    conn.close()

if __name__ == "__main__":
    verify_before_score_components()
