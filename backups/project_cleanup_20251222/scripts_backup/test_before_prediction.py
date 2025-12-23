#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
before予測生成のテスト（1レース分のみ）
"""
import sys
import os

# 最初に文字コード設定
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

os.environ['PYTHONUNBUFFERED'] = '1'

import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.analysis.race_predictor import RacePredictor

def test_before_prediction():
    """1レース分のbefore予測を生成してテスト"""
    print("=" * 80)
    print("before予測生成テスト（2025年の1レース）")
    print("=" * 80)
    print()

    db_path = PROJECT_ROOT / "data" / "boatrace.db"

    # 2025年の最初のレースを取得（直前情報がある可能性が高い）
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT r.id, r.venue_code, r.race_date, r.race_number
        FROM races r
        WHERE r.race_date >= '2025-01-01'
        ORDER BY r.race_date, r.venue_code, r.race_number
        LIMIT 1
    """)

    race = cursor.fetchone()
    conn.close()

    if not race:
        print("テスト対象レースが見つかりません")
        return False

    race_id, venue_code, race_date, race_number = race

    print(f"テスト対象: {race_date} 会場{int(venue_code):02d} R{race_number}")
    print(f"race_id: {race_id}")
    print()

    # before予測生成
    predictor = RacePredictor(use_cache=True)

    try:
        print("before予測を生成中（use_beforeinfo=True）...")
        predictions = predictor.predict_race(race_id, use_beforeinfo=True)

        if predictions and len(predictions) >= 6:
            print(f"OK: 予測生成成功（{len(predictions)}件）")
            print()
            print("予測結果（上位3艇）:")
            for i, pred in enumerate(predictions[:3], 1):
                print(f"  {i}位予測: 艇{pred['pit_number']} {pred['racer_name']} "
                      f"(スコア{pred['total_score']:.1f}pt, 信頼度{pred['confidence']})")
            print()
            return True
        else:
            print(f"NG: 予測生成失敗（{len(predictions) if predictions else 0}件）")
            return False

    except Exception as e:
        print(f"エラー: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_before_prediction()

    print()
    print("=" * 80)
    if success:
        print("テスト成功 - before予測スクリプトは正常に動作します")
    else:
        print("テスト失敗 - スクリプトに問題があります")
    print("=" * 80)

    sys.exit(0 if success else 1)
