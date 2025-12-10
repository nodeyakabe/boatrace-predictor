#!/usr/bin/env python3
"""
BEFOREパターン適用状況の簡易確認スクリプト
2025年データから最新100レースをサンプリングして分析
"""

import sys
import os

# プロジェクトルートをパスに追加
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

import sqlite3
from collections import defaultdict

def get_connection(db_path):
    """データベース接続を取得"""
    return sqlite3.connect(db_path)

# RacePredictorをインポート
from src.analysis.race_predictor import RacePredictor

def quick_pattern_check(db_path=None, sample_size=100):
    """
    パターン適用状況を簡易確認

    Args:
        db_path: データベースパス
        sample_size: サンプルレース数
    """
    if db_path is None:
        # スクリプトのディレクトリから相対パスで指定
        script_dir = os.path.dirname(os.path.abspath(__file__))
        db_path = os.path.join(script_dir, '..', 'data', 'boatrace.db')

    print("=" * 80)
    print("BEFOREパターン適用状況 簡易確認")
    print("=" * 80)
    print()

    # データベースから2025年の最新レースを取得
    conn = get_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT r.id, r.venue_code, r.race_date
        FROM races r
        WHERE r.race_date >= '2025-01-01'
          AND r.race_date < '2026-01-01'
          AND EXISTS (
              SELECT 1 FROM results res
              WHERE res.race_id = r.id
                AND res.rank IS NOT NULL
          )
          AND EXISTS (
              SELECT 1 FROM race_details rd
              WHERE rd.race_id = r.id
                AND rd.exhibition_time IS NOT NULL
                AND rd.st_time IS NOT NULL
          )
        ORDER BY r.race_date DESC, r.id DESC
        LIMIT ?
    """, (sample_size,))

    races = cursor.fetchall()
    cursor.close()

    if not races:
        print("[ERROR] 2025年のレースデータが見つかりません")
        return

    print(f"[OK] 対象レース数: {len(races)}レース")
    print(f"     期間: {races[-1][2]} - {races[0][2]}")
    print()

    # 予測器の初期化
    predictor = RacePredictor(db_path=db_path)

    # 統計情報
    stats = {
        'total': 0,
        'with_pattern': 0,
        'without_pattern': 0,
        'correct_with_pattern': 0,
        'correct_without_pattern': 0,
        'pattern_counts': defaultdict(int),
        'pattern_hits': defaultdict(int),
    }

    print("処理中...", end='', flush=True)

    # 各レースを分析
    for i, (race_id, venue_code, race_date) in enumerate(races):
        if i % 20 == 0:
            print(f"\r処理中... {i}/{len(races)}", end='', flush=True)

        try:
            # 予測実行
            predictions = predictor.predict_race(race_id)

            if not predictions:
                continue

            stats['total'] += 1

            # 1着予測
            top_pred = predictions[0]

            # 実際の勝者を取得
            conn2 = get_connection(db_path)
            cursor2 = conn2.cursor()
            cursor2.execute("""
                SELECT pit_number
                FROM results
                WHERE race_id = ? AND rank = '1'
            """, (race_id,))
            winner = cursor2.fetchone()
            cursor2.close()

            if not winner:
                continue

            winner_pit = winner[0]
            is_correct = (top_pred['pit_number'] == winner_pit)

            # パターン適用チェック
            has_pattern = (
                'pattern_multiplier' in top_pred and
                top_pred.get('pattern_multiplier', 1.0) > 1.0
            )

            if has_pattern:
                stats['with_pattern'] += 1
                if is_correct:
                    stats['correct_with_pattern'] += 1

                # パターン名を記録
                matched_patterns = top_pred.get('matched_patterns', [])
                for p in matched_patterns:
                    pattern_name = p.get('name', 'unknown')
                    stats['pattern_counts'][pattern_name] += 1
                    if is_correct:
                        stats['pattern_hits'][pattern_name] += 1
            else:
                stats['without_pattern'] += 1
                if is_correct:
                    stats['correct_without_pattern'] += 1

        except Exception as e:
            # エラーを記録（デバッグ用）
            if i == 0:  # 最初のエラーだけ表示
                print(f"\n[WARNING] 予測エラー (race_id={race_id}): {str(e)}\n")
            pass

    print(f"\r処理完了: {stats['total']}/{len(races)}レース")
    print()

    # 結果表示
    print("=" * 80)
    print("【全体統計】")
    print("=" * 80)
    print(f"総レース数: {stats['total']}")
    print()

    if stats['with_pattern'] > 0:
        pattern_rate = stats['correct_with_pattern'] / stats['with_pattern'] * 100
        print(f"パターン適用あり: {stats['with_pattern']}レース ({stats['with_pattern']/stats['total']*100:.1f}%)")
        print(f"  的中数: {stats['correct_with_pattern']}")
        print(f"  的中率: {pattern_rate:.1f}%")
    else:
        print(f"パターン適用あり: 0レース")

    print()

    if stats['without_pattern'] > 0:
        no_pattern_rate = stats['correct_without_pattern'] / stats['without_pattern'] * 100
        print(f"パターン適用なし: {stats['without_pattern']}レース ({stats['without_pattern']/stats['total']*100:.1f}%)")
        print(f"  的中数: {stats['correct_without_pattern']}")
        print(f"  的中率: {no_pattern_rate:.1f}%")
    else:
        print(f"パターン適用なし: {stats['total']}レース")
        if stats['total'] > 0:
            no_pattern_rate = stats['correct_without_pattern'] / stats['total'] * 100
            print(f"  的中数: {stats['correct_without_pattern']}")
            print(f"  的中率: {no_pattern_rate:.1f}%")

    print()

    # パターン別統計
    if stats['pattern_counts']:
        print("=" * 80)
        print("【パターン別適用状況】")
        print("=" * 80)

        # 適用回数でソート
        sorted_patterns = sorted(
            stats['pattern_counts'].items(),
            key=lambda x: x[1],
            reverse=True
        )

        for pattern_name, count in sorted_patterns:
            hits = stats['pattern_hits'].get(pattern_name, 0)
            hit_rate = hits / count * 100 if count > 0 else 0
            print(f"{pattern_name:30s}: {count:3d}回適用, {hits:3d}回的中 ({hit_rate:5.1f}%)")

    print()
    print("=" * 80)

if __name__ == '__main__':
    quick_pattern_check()
