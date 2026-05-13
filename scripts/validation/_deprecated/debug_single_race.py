"""
単一レースの購入判定をデバッグ
Tier 2（SQL）とTier 3（BetTargetEvaluator）の判定を詳細比較
"""
import sys
import os
# プロジェクトルートをPythonパスに追加
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import sqlite3
from src.betting.bet_target_evaluator import BetTargetEvaluator, BetStatus
from src.betting.evaluator_helpers import create_standard_evaluator

def get_race_data(race_id: int) -> dict:
    """レースデータを取得"""
    conn = sqlite3.connect('data/boatrace.db')
    cursor = conn.cursor()
    
    # レース基本情報
    cursor.execute('''
        SELECT id, venue_code, race_date, race_number
        FROM races
        WHERE id = ?
    ''', (race_id,))
    race = cursor.fetchone()
    if not race:
        conn.close()
        return None
    
    # エントリー情報
    cursor.execute('''
        SELECT pit_number, racer_number, racer_rank, motor_second_rate, second_rate
        FROM entries
        WHERE race_id = ?
        ORDER BY pit_number
    ''', (race_id,))
    entries = [
        {
            'pit_number': row[0],
            'racer_number': row[1],
            'racer_rank': row[2],
            'motor_second_rate': row[3],
            'second_rate': row[4]
        }
        for row in cursor.fetchall()
    ]
    
    # 予測情報
    cursor.execute('''
        SELECT confidence, pit_number, rank_prediction
        FROM race_predictions
        WHERE race_id = ? AND prediction_type = 'before'
        ORDER BY rank_prediction
    ''', (race_id,))
    predictions_raw = cursor.fetchall()
    
    # 信頼度ごとに予測を整理
    predictions_by_conf = {}
    for conf, pit_num, rank_pred in predictions_raw:
        if conf not in predictions_by_conf:
            predictions_by_conf[conf] = []
        predictions_by_conf[conf].append(pit_num)
    
    # オッズ情報
    cursor.execute('''
        SELECT combination, odds
        FROM trifecta_odds
        WHERE race_id = ?
    ''', (race_id,))
    odds_data = {row[0]: row[1] for row in cursor.fetchall()}
    
    conn.close()
    
    return {
        'race_id': race[0],
        'venue_code': int(race[1]),
        'race_date': race[2],
        'race_number': race[3],
        'entries': entries,
        'predictions': predictions_by_conf,
        'odds_data': odds_data
    }

def debug_race(race_id: int):
    """レースの購入判定をデバッグ"""
    print(f"\n{'='*80}")
    print(f"Race ID: {race_id}")
    print(f"{'='*80}")
    
    # データ取得
    data = get_race_data(race_id)
    if not data:
        print("❌ レースデータが見つかりません")
        return
    
    print(f"日付: {data['race_date']}, 会場: {data['venue_code']:02d}, レース: {data['race_number']}R")
    print(f"エントリー数: {len(data['entries'])}")
    print(f"予測信頼度: {list(data['predictions'].keys())}")
    
    # 各信頼度で評価
    evaluator = create_standard_evaluator()
    
    for confidence, prediction in data['predictions'].items():
        print(f"\n--- 信頼度 {confidence} ---")
        print(f"予測: {prediction}")
        
        # 買い目とオッズ
        if len(prediction) >= 3:
            combo = f"{prediction[0]}-{prediction[1]}-{prediction[2]}"
            odds = data['odds_data'].get(combo)
            print(f"買い目: {combo}, オッズ: {odds}")
            
            # BetTargetEvaluatorで判定
            race_data = {
                'entries': data['entries'],
                'venue_code': data['venue_code'],
                'race_date': data['race_date'],
                'race_number': data['race_number'],
                'wind_speed': 0.0,  # データなし
            }
            predictions_dict = {
                'confidence': confidence,
                'old_prediction': prediction,
                'new_prediction': prediction,
            }
            odds_data_dict = {combo: odds} if odds else {}
            
            result = evaluator.evaluate_race(
                race_data=race_data,
                predictions=predictions_dict,
                odds_data=odds_data_dict,
                has_beforeinfo=True
            )
            
            print(f"判定: {result.status.value}")
            print(f"理由: {result.reason}")
            if result.status in [BetStatus.TARGET_ADVANCE, BetStatus.TARGET_CONFIRMED]:
                print(f"✅ 購入対象")
            else:
                print(f"❌ 対象外")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python debug_single_race.py <race_id>")
        sys.exit(1)
    
    race_id = int(sys.argv[1])
    debug_race(race_id)
