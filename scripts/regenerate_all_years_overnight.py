#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
2022-2024年のadvance予測データを完全アルゴリズムで順次再生成するスクリプト

特徴:
- hierarchical_predictor有効（A-E信頼度分布）
- UPSERT方式（既存データを安全に上書き）
- 年度を順番に処理（競合を回避）
- 途中停止しても再開可能
- 推定完了時刻を表示
"""

import sys
import os
import sqlite3
import warnings
import json
from datetime import datetime, timedelta

# パス設定
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
warnings.filterwarnings('ignore')

from config.settings import DATABASE_PATH
from config.feature_flags import FEATURE_FLAGS
from src.analysis.race_predictor import RacePredictor


def get_all_races_for_year(year: str) -> list:
    """指定年度の全レースIDを取得"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT r.id, r.race_date
        FROM races r
        WHERE r.race_date LIKE ? || '%'
        ORDER BY r.race_date, r.id
    ''', (year,))
    races = cursor.fetchall()
    conn.close()
    return races


def upsert_predictions(race_id: str, predictions: list):
    """予測データをUPSERT（INSERT OR REPLACE）で保存"""
    conn = sqlite3.connect(DATABASE_PATH, timeout=60)
    cursor = conn.cursor()

    for pred in predictions:
        applied = json.dumps(pred.get('applied_rules', []), ensure_ascii=False)
        cursor.execute('''
            INSERT OR REPLACE INTO race_predictions (
                race_id, pit_number, rank_prediction, total_score,
                confidence, racer_name, racer_number, applied_rules,
                course_score, racer_score, motor_score, kimarite_score, grade_score,
                prediction_type, generated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            race_id,
            pred['pit_number'],
            pred['rank_prediction'],
            pred.get('total_score', 0),
            pred.get('confidence', 'E'),
            pred.get('racer_name', ''),
            pred.get('racer_number', ''),
            applied,
            pred.get('course_score', 0),
            pred.get('racer_score', 0),
            pred.get('motor_score', 0),
            pred.get('kimarite_score', 0),
            pred.get('grade_score', 0),
            'advance',
            datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        ))

    conn.commit()
    conn.close()


def check_confidence_distribution(year: str) -> dict:
    """信頼度分布を確認"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT rp.confidence, COUNT(DISTINCT rp.race_id)
        FROM race_predictions rp
        JOIN races r ON rp.race_id = r.id
        WHERE r.race_date LIKE ? || '%'
        AND rp.prediction_type = 'advance' AND rp.rank_prediction = 1
        GROUP BY rp.confidence
    ''', (year,))
    result = dict(cursor.fetchall())
    conn.close()
    return result


def regenerate_year(year: str, predictor: RacePredictor) -> tuple:
    """指定年度の予測を再生成"""
    print(f"\n{'='*70}")
    print(f"{year}年 advance予測 再生成開始")
    print(f"hierarchical_predictor: {FEATURE_FLAGS.get('hierarchical_predictor', False)}")
    print(f"{'='*70}")

    races = get_all_races_for_year(year)
    total = len(races)
    print(f"総レース数: {total:,}件")

    # 現在の信頼度分布
    current_dist = check_confidence_distribution(year)
    print(f"現在の信頼度分布: {current_dist}")

    success = 0
    failed = 0
    start_time = datetime.now()
    last_date = ""

    for i, (race_id, race_date) in enumerate(races, 1):
        try:
            predictions = predictor.predict_race(race_id, use_beforeinfo=False)
            if predictions:
                upsert_predictions(race_id, predictions)
                success += 1
            else:
                failed += 1
        except Exception as e:
            failed += 1

        # 日付が変わったら表示
        date_str = race_date[:10] if race_date else ""
        if date_str != last_date:
            last_date = date_str
            elapsed = (datetime.now() - start_time).total_seconds()
            if success > 0:
                rate = success / elapsed
                remaining_races = total - i
                remaining_seconds = remaining_races / rate if rate > 0 else 0
                eta = datetime.now() + timedelta(seconds=remaining_seconds)
                print(f"[{date_str}] {i:,}/{total:,} ({100*i/total:.1f}%) "
                      f"成功={success:,} 失敗={failed} "
                      f"{rate:.1f}/s 残り{remaining_seconds/60:.0f}分 "
                      f"完了予定: {eta.strftime('%H:%M')}")

    elapsed = (datetime.now() - start_time).total_seconds()

    # 完了後の信頼度分布
    final_dist = check_confidence_distribution(year)

    print(f"\n{year}年 完了")
    print(f"成功: {success:,}件 / 失敗: {failed}件")
    print(f"所要時間: {elapsed/60:.1f}分")
    print(f"信頼度分布: {final_dist}")

    return success, failed


def main():
    print("="*70)
    print("2022-2024年 advance予測データ 完全再生成")
    print(f"開始時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)

    # フィーチャーフラグ確認
    print("\n現在のフィーチャーフラグ:")
    important_flags = [
        'hierarchical_predictor',
        'lightgbm_ranking',
        'pairwise_scoring',
        'confidence_based_switching'
    ]
    for flag in important_flags:
        value = FEATURE_FLAGS.get(flag, False)
        print(f"  {flag}: {value}")

    if not FEATURE_FLAGS.get('hierarchical_predictor', False):
        print("\n警告: hierarchical_predictor が無効です！")
        print("config/feature_flags.py で True に設定してください。")
        # 続行はするが警告を出す

    # Predictor初期化
    print("\nPredictor初期化中...")
    predictor = RacePredictor()
    print("初期化完了")

    # 年度ごとに順次処理（2025年も含む）
    years = ['2022', '2023', '2024', '2025']
    results = {}

    for year in years:
        success, failed = regenerate_year(year, predictor)
        results[year] = {'success': success, 'failed': failed}

    # 最終サマリー
    print("\n" + "="*70)
    print("全年度 完了サマリー")
    print("="*70)

    total_success = 0
    total_failed = 0

    for year in years:
        s = results[year]['success']
        f = results[year]['failed']
        dist = check_confidence_distribution(year)
        print(f"{year}年: 成功={s:,} 失敗={f} 信頼度分布={dist}")
        total_success += s
        total_failed += f

    print(f"\n合計: 成功={total_success:,}件 失敗={total_failed}件")
    print(f"完了時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == '__main__':
    main()
