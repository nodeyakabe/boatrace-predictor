#!/usr/bin/env python3
"""
ベースライン比較レポート
B1 vs B2 の差分を表示する

使用方法:
  python scripts/maintenance/compare_baselines.py \
      --b1 data/baselines/B1_wind_direction.json \
      --b2 data/baselines/B2_actual_course.json
"""
import argparse
import json
import sys
import io
from pathlib import Path

# Windows で絵文字を含む出力を UTF-8 で出力する
if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')


def load(path: str) -> dict:
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def fmt_diff(val, prev, pct=False, invert=False):
    diff = val - prev
    if pct:
        s = f"{diff:+.1f}pt"
    else:
        s = f"{diff:+,.0f}"
    good = diff > 0
    if invert:
        good = not good
    mark = "✅" if good else ("⚠️" if abs(diff) < 0.01 else "🔴")
    return s, mark


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--b1', required=True, help='ベースライン1 JSONパス')
    parser.add_argument('--b2', required=True, help='ベースライン2 JSONパス')
    parser.add_argument('--label1', default='B1（変更前）')
    parser.add_argument('--label2', default='B2（変更後）')
    args = parser.parse_args()

    b1 = load(args.b1)
    b2 = load(args.b2)

    t1 = b1['total']
    t2 = b2['total']

    print("=" * 70)
    print(f"  ベースライン比較レポート")
    print(f"  {args.label1}: {Path(args.b1).name}")
    print(f"  {args.label2}: {Path(args.b2).name}")
    print("=" * 70)

    print("\n### 全体サマリー\n")
    print(f"{'指標':<20} {'B1':>14} {'B2':>14} {'差分':>12} {'判定':>4}")
    print("-" * 70)

    # 件数
    d, m = fmt_diff(t2['bets'], t1['bets'])
    print(f"{'購入件数':<20} {t1['bets']:>14,} {t2['bets']:>14,} {d:>12} {m}")

    # 的中率
    d, m = fmt_diff(t2['hit_rate'], t1['hit_rate'], pct=True)
    print(f"{'的中率':<20} {t1['hit_rate']:>13.1f}% {t2['hit_rate']:>13.1f}% {d:>12} {m}")

    # ROI
    d, m = fmt_diff(t2['roi'], t1['roi'], pct=True)
    print(f"{'ROI':<20} {t1['roi']:>13.1f}% {t2['roi']:>13.1f}% {d:>12} {m}")

    # 収支
    d, m = fmt_diff(t2['profit'], t1['profit'])
    print(f"{'収支':<20} {t1['profit']:>+14,.0f} {t2['profit']:>+14,.0f} {d:>12} {m}")

    # 投資額
    d, m = fmt_diff(t2['investment'], t1['investment'])
    print(f"{'投資額':<20} {t1['investment']:>14,} {t2['investment']:>14,} {d:>12}")

    print("-" * 70)

    # 総合判定
    roi_diff = t2['roi'] - t1['roi']
    profit_diff = t2['profit'] - t1['profit']

    print("\n### 総合判定\n")
    if roi_diff >= 5.0 and profit_diff > 0:
        print("  🟢 明確な改善  → 変更を採用")
    elif roi_diff >= 0 and profit_diff >= 0:
        print("  🟡 微改善/中立 → 採用（問題なし）")
    elif roi_diff >= -3.0:
        print("  🟡 誤差範囲の可能性あり → 詳細分析推奨")
    else:
        print("  🔴 退行を確認  → 変更をリバート")

    # 条件別差分（上位変化）
    if 'conditions' in b1 and 'conditions' in b2:
        print("\n### 条件別変化（収支差分の大きい順）\n")
        print(f"{'条件':<30} {'B1収支':>12} {'B2収支':>12} {'差分':>10}")
        print("-" * 70)

        c1_map = {c['id']: c for c in b1['conditions']}
        c2_map = {c['id']: c for c in b2['conditions']}

        diffs = []
        for cid, c2 in c2_map.items():
            c1 = c1_map.get(cid)
            if c1:
                diffs.append((c2['profit'] - c1['profit'], cid, c1, c2))

        diffs.sort(key=lambda x: abs(x[0]), reverse=True)

        for diff, cid, c1, c2 in diffs[:10]:
            name = c2.get('name', cid)[:28]
            mark = "↑" if diff > 0 else "↓"
            print(f"  {name:<28} {c1['profit']:>+12,.0f} {c2['profit']:>+12,.0f} {diff:>+10,.0f} {mark}")

    print("\n" + "=" * 70)


if __name__ == '__main__':
    main()
