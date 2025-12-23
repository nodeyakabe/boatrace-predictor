#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ネガティブパターン抽出スクリプト

「こういう時は外れやすい」という警告パターンを抽出
予測的中率を下げる組み合わせを特定し、警告フラグとして活用
"""

import os
import sys
import sqlite3
from collections import defaultdict

# プロジェクトルートをパスに追加
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
sys.path.insert(0, project_root)

from src.analysis.race_predictor import RacePredictor


def extract_negative_patterns(db_path=None, sample_size=500, min_count=10):
    """
    ネガティブパターンを抽出

    Args:
        db_path: データベースパス
        sample_size: 分析対象レース数
        min_count: 最小出現回数（これ以上のパターンのみ抽出）
    """
    if db_path is None:
        db_path = os.path.join(project_root, 'data', 'boatrace.db')

    print("=" * 80)
    print("ネガティブパターン抽出（警告パターン分析）")
    print("=" * 80)
    print()

    # データベース接続
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 対象レース取得（2025年データから）
    cursor.execute("""
        SELECT r.id, r.venue_code, r.race_date
        FROM races r
        WHERE r.race_date >= '2025-01-01'
          AND r.race_date < '2026-01-01'
          AND EXISTS (
              SELECT 1 FROM results res
              WHERE res.race_id = r.id AND res.rank IS NOT NULL
          )
          AND EXISTS (
              SELECT 1 FROM race_details rd
              WHERE rd.race_id = r.id
                AND rd.exhibition_time IS NOT NULL
                AND rd.st_time IS NOT NULL
          )
        ORDER BY r.race_date DESC
        LIMIT ?
    """, (sample_size,))

    races = cursor.fetchall()
    total_races = len(races)

    print(f"[OK] 対象レース数: {total_races}レース\n")

    if total_races == 0:
        print("[ERROR] データが見つかりません")
        return

    # ネガティブパターン統計
    negative_patterns = defaultdict(lambda: {'count': 0, 'miss': 0})

    # 予測器の初期化
    predictor = RacePredictor()

    print("分析開始...\n")

    # 各レースを分析
    for i, (race_id, venue_code, race_date) in enumerate(races):
        if (i + 1) % 50 == 0:
            print(f"処理中... {i + 1}/{total_races}", end='\r')

        try:
            predictions = predictor.predict_race(race_id)
        except Exception as e:
            continue

        if not predictions:
            continue

        top_pred = predictions[0]
        pit_number = top_pred['pit_number']

        # 実際の勝者を取得
        cursor.execute("""
            SELECT pit_number
            FROM results
            WHERE race_id = ? AND rank = '1'
        """, (race_id,))

        winner_row = cursor.fetchone()
        if not winner_row:
            continue

        winner = winner_row[0]
        is_miss = (pit_number != winner)

        # 外れた場合のみネガティブパターンを記録
        if is_miss:
            # BEFORE情報を取得
            cursor.execute("""
                SELECT
                    rd.pit_number,
                    rd.exhibition_time,
                    rd.st_time
                FROM race_details rd
                WHERE rd.race_id = ?
                ORDER BY rd.pit_number
            """, (race_id,))

            before_data = cursor.fetchall()

            if len(before_data) == 6:
                # トップ予測の艇のBEFORE情報
                top_before = before_data[pit_number - 1]
                ex_time = top_before[1]
                st_time = top_before[2]

                if ex_time is not None and st_time is not None:
                    # ランク計算
                    ex_sorted = sorted([(b[1], b[0]) for b in before_data if b[1] is not None])
                    st_sorted = sorted([(abs(b[2]), b[0]) for b in before_data if b[2] is not None])

                    ex_rank = next((i+1 for i, (t, p) in enumerate(ex_sorted) if p == pit_number), 7)
                    st_rank = next((i+1 for i, (t, p) in enumerate(st_sorted) if p == pit_number), 7)

                    # ネガティブパターンを記録
                    patterns = []

                    # パターン1: 予測1位だが展示・ST両方悪い
                    if ex_rank >= 5 and st_rank >= 5:
                        patterns.append('pre1_but_ex_st_both_bad')

                    # パターン2: 展示は良いがSTが非常に悪い
                    if ex_rank <= 2 and st_rank >= 5:
                        patterns.append('ex_good_but_st_very_bad')

                    # パターン3: STは良いが展示が非常に悪い
                    if st_rank <= 2 and ex_rank >= 5:
                        patterns.append('st_good_but_ex_very_bad')

                    # パターン4: 展示タイムが極端に遅い（ワースト2以内）
                    if ex_rank >= 5:
                        patterns.append('exhibition_rank_5_6')

                    # パターン5: STタイミングが大幅にずれている
                    if st_time is not None:
                        if st_time < -0.15 or st_time > 0.20:
                            patterns.append('st_timing_off_major')

                    # パターン6: 展示とSTの乖離が大きい
                    rank_diff = abs(ex_rank - st_rank)
                    if rank_diff >= 4:
                        patterns.append('ex_st_rank_divergence')

                    # パターン記録
                    for pattern in patterns:
                        negative_patterns[pattern]['count'] += 1
                        negative_patterns[pattern]['miss'] += 1

    print(f"\n処理完了: {total_races}レース\n")

    # 結果出力
    print("=" * 80)
    print("【ネガティブパターン分析結果】")
    print("=" * 80)
    print()

    # パターンを出現頻度順にソート
    sorted_patterns = sorted(
        negative_patterns.items(),
        key=lambda x: x[1]['count'],
        reverse=True
    )

    print(f"最小出現回数: {min_count}回以上\n")

    found_patterns = []
    for pattern_name, stats in sorted_patterns:
        count = stats['count']
        miss = stats['miss']

        if count < min_count:
            continue

        miss_rate = 100 * miss / count if count > 0 else 0

        print(f"{pattern_name:30s}: {count:3d}回出現, {miss:3d}回外れ ({miss_rate:5.1f}%)")

        found_patterns.append({
            'name': pattern_name,
            'count': count,
            'miss': miss,
            'miss_rate': miss_rate
        })

    print()
    print("=" * 80)
    print("【推奨される警告フラグ】")
    print("=" * 80)
    print()

    # 外れ率80%以上のパターンを警告フラグとして推奨
    warning_flags = [p for p in found_patterns if p['miss_rate'] >= 80.0]

    if warning_flags:
        print("以下のパターンは警告フラグとして有効です（外れ率80%以上）:\n")
        for p in warning_flags:
            print(f"  - {p['name']}: {p['count']}回中{p['miss']}回外れ ({p['miss_rate']:.1f}%)")
            print(f"    → 予測信頼度を下げる、または予測を除外することを推奨\n")
    else:
        print("外れ率80%以上の強力なネガティブパターンは見つかりませんでした。")
        print("外れ率70%以上のパターン:\n")

        moderate_flags = [p for p in found_patterns if p['miss_rate'] >= 70.0]
        for p in moderate_flags:
            print(f"  - {p['name']}: {p['count']}回中{p['miss']}回外れ ({p['miss_rate']:.1f}%)")

    print()
    print("=" * 80)
    print("【実装推奨】")
    print("=" * 80)
    print()
    print("これらのネガティブパターンは以下のように活用できます：")
    print()
    print("1. 予測信頼度の調整")
    print("   - パターンマッチ時に confidence_level を1段階下げる")
    print()
    print("2. スコア補正")
    print("   - パターンマッチ時に score × 0.7 などの減算係数を適用")
    print()
    print("3. 警告表示")
    print("   - UIで「このレースは予測精度が低い可能性があります」と表示")
    print()
    print("4. ベット回避")
    print("   - 自動ベットシステムで、該当レースをスキップ")
    print()

    conn.close()


if __name__ == "__main__":
    extract_negative_patterns()
