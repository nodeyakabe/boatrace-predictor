# -*- coding: utf-8 -*-
"""
P-1で除外されたレースの信頼度分布を分析

前付けレースが本当にA/Bランクに含まれているか確認
"""
import sys
import sqlite3
import io
import json
from pathlib import Path
from collections import defaultdict

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))


def load_forward_movers():
    """前付け常習者リストを読み込む"""
    path = ROOT_DIR / "config" / "forward_movers.json"
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return set(str(rn) for rn in data.get('racer_numbers', []))
    except:
        return set()


def main():
    db_path = ROOT_DIR / "data" / "boatrace.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    forward_movers = load_forward_movers()
    print(f"前付け常習者数: {len(forward_movers)}")
    print()

    # 全レース取得
    cursor.execute('''
        SELECT r.id as race_id
        FROM races r
        WHERE r.race_date >= '2025-01-01' AND r.race_date <= '2025-11-30'
          AND EXISTS (SELECT 1 FROM race_predictions WHERE race_id = r.id AND prediction_type = 'before')
          AND EXISTS (SELECT 1 FROM results WHERE race_id = r.id AND is_invalid = 0)
    ''')
    races = cursor.fetchall()

    # 信頼度別カウント
    all_confidence = defaultdict(int)
    forward_mover_confidence = defaultdict(int)
    excluded_races = []

    for race in races:
        race_id = race['race_id']

        # 予測の信頼度を取得
        cursor.execute('''
            SELECT confidence FROM race_predictions
            WHERE race_id = ? AND prediction_type = 'before'
            ORDER BY total_score DESC LIMIT 1
        ''', (race_id,))
        pred = cursor.fetchone()
        if not pred:
            continue

        confidence = pred['confidence']
        all_confidence[confidence] += 1

        # 前付け常習者がいるか確認
        cursor.execute('SELECT racer_number FROM entries WHERE race_id = ?', (race_id,))
        racer_numbers = [str(row['racer_number']) for row in cursor.fetchall()]

        if set(racer_numbers) & forward_movers:
            forward_mover_confidence[confidence] += 1
            excluded_races.append((race_id, confidence))

    conn.close()

    # 結果表示
    print("=" * 80)
    print("信頼度別レース数")
    print("=" * 80)
    print(f"{'信頼度':<10} {'全体':>12} {'前付けあり':>12} {'除外率':>10}")
    print("-" * 50)

    for conf in ['A', 'B', 'C', 'D', 'E']:
        total = all_confidence[conf]
        forward = forward_mover_confidence[conf]
        rate = forward / total * 100 if total > 0 else 0
        print(f"{conf:<10} {total:>12,} {forward:>12,} {rate:>9.1f}%")

    print("-" * 50)
    total_all = sum(all_confidence.values())
    total_forward = sum(forward_mover_confidence.values())
    print(f"{'合計':<10} {total_all:>12,} {total_forward:>12,} {total_forward/total_all*100:>9.1f}%")

    print()
    print("=" * 80)
    print("重要な発見")
    print("=" * 80)

    ab_total = all_confidence['A'] + all_confidence['B']
    ab_forward = forward_mover_confidence['A'] + forward_mover_confidence['B']

    print(f"信頼度A+Bのレース数: {ab_total:,}")
    print(f"  うち前付け常習者あり: {ab_forward:,} ({ab_forward/ab_total*100:.1f}%)")

    if ab_forward > 0:
        print()
        print("⚠️ 信頼度A/Bでも前付け常習者が含まれるレースがある")
        print("   → P-1フィルターでこれらが除外される可能性")
    else:
        print()
        print("✅ 信頼度A/Bには前付け常習者レースは含まれていない")


if __name__ == "__main__":
    main()
