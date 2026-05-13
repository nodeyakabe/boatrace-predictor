#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
設定抽出スクリプト

config/feature_flags.py から有効フラグを抽出し、
docs/guides/PREDICTION_SYSTEM_STATUS.md を自動更新する。
"""
import os
import sys
import sqlite3
from datetime import datetime

# プロジェクトルートをパスに追加
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.feature_flags import FEATURE_FLAGS, FEATURE_RISKS


def get_enabled_flags() -> dict:
    """有効なフラグを取得"""
    enabled = {}
    disabled = {}
    for name, value in FEATURE_FLAGS.items():
        if value:
            enabled[name] = {
                'name': name,
                'enabled': True,
                'risk_info': FEATURE_RISKS.get(name, {})
            }
        else:
            disabled[name] = {
                'name': name,
                'enabled': False,
                'risk_info': FEATURE_RISKS.get(name, {})
            }
    return enabled, disabled


def get_prediction_stats(db_path: str, year: str = '2025') -> dict:
    """予測の統計情報を取得"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    stats = {
        'year': year,
        'total_races': 0,
        'min_date': '',
        'max_date': '',
        'confidence_counts': {},
        'first_accuracy': {},
        'second_accuracy': {},
        'third_accuracy': {},
        'trifecta_accuracy': {}
    }

    # 基本統計
    cursor.execute(f'''
        SELECT
            COUNT(DISTINCT rp.race_id) as total_races,
            MIN(r.race_date) as min_date,
            MAX(r.race_date) as max_date
        FROM race_predictions rp
        JOIN races r ON rp.race_id = r.id
        WHERE r.race_date LIKE '{year}%'
          AND rp.prediction_type = 'before'
          AND rp.rank_prediction = 1
    ''')
    result = cursor.fetchone()
    stats['total_races'] = result[0] or 0
    stats['min_date'] = result[1] or ''
    stats['max_date'] = result[2] or ''

    # 信頼度別レース数
    cursor.execute(f'''
        SELECT
            rp.confidence,
            COUNT(DISTINCT rp.race_id) as race_count
        FROM race_predictions rp
        JOIN races r ON rp.race_id = r.id
        WHERE r.race_date LIKE '{year}%'
          AND rp.prediction_type = 'before'
          AND rp.rank_prediction = 1
        GROUP BY rp.confidence
        ORDER BY rp.confidence
    ''')
    for row in cursor.fetchall():
        if row[0]:
            stats['confidence_counts'][row[0]] = row[1]

    # 1着的中率
    cursor.execute(f'''
        WITH predictions AS (
            SELECT
                rp.race_id,
                rp.confidence,
                rp.pit_number as pred_pit
            FROM race_predictions rp
            JOIN races r ON rp.race_id = r.id
            WHERE r.race_date LIKE '{year}%'
              AND rp.prediction_type = 'before'
              AND rp.rank_prediction = 1
        )
        SELECT
            p.confidence,
            COUNT(*) as total,
            SUM(CASE WHEN p.pred_pit = res.pit_number THEN 1 ELSE 0 END) as correct
        FROM predictions p
        LEFT JOIN results res ON p.race_id = res.race_id AND res.rank = '1'
        WHERE p.confidence IS NOT NULL
        GROUP BY p.confidence
        ORDER BY p.confidence
    ''')
    for row in cursor.fetchall():
        stats['first_accuracy'][row[0]] = {
            'total': row[1],
            'correct': row[2],
            'rate': round(100.0 * row[2] / row[1], 2) if row[1] > 0 else 0
        }

    # 2着的中率
    cursor.execute(f'''
        WITH predictions AS (
            SELECT
                rp.race_id,
                MAX(CASE WHEN rp.rank_prediction = 1 THEN rp.confidence END) as confidence,
                MAX(CASE WHEN rp.rank_prediction = 2 THEN rp.pit_number END) as pred_2nd
            FROM race_predictions rp
            JOIN races r ON rp.race_id = r.id
            WHERE r.race_date LIKE '{year}%'
              AND rp.prediction_type = 'before'
              AND rp.rank_prediction <= 2
            GROUP BY rp.race_id
        )
        SELECT
            p.confidence,
            COUNT(*) as total,
            SUM(CASE WHEN p.pred_2nd = res.pit_number THEN 1 ELSE 0 END) as correct
        FROM predictions p
        LEFT JOIN results res ON p.race_id = res.race_id AND res.rank = '2'
        WHERE p.confidence IS NOT NULL
        GROUP BY p.confidence
        ORDER BY p.confidence
    ''')
    for row in cursor.fetchall():
        stats['second_accuracy'][row[0]] = {
            'total': row[1],
            'correct': row[2],
            'rate': round(100.0 * row[2] / row[1], 2) if row[1] > 0 else 0
        }

    # 3着的中率
    cursor.execute(f'''
        WITH predictions AS (
            SELECT
                rp.race_id,
                MAX(CASE WHEN rp.rank_prediction = 1 THEN rp.confidence END) as confidence,
                MAX(CASE WHEN rp.rank_prediction = 3 THEN rp.pit_number END) as pred_3rd
            FROM race_predictions rp
            JOIN races r ON rp.race_id = r.id
            WHERE r.race_date LIKE '{year}%'
              AND rp.prediction_type = 'before'
              AND rp.rank_prediction <= 3
            GROUP BY rp.race_id
        )
        SELECT
            p.confidence,
            COUNT(*) as total,
            SUM(CASE WHEN p.pred_3rd = res.pit_number THEN 1 ELSE 0 END) as correct
        FROM predictions p
        LEFT JOIN results res ON p.race_id = res.race_id AND res.rank = '3'
        WHERE p.confidence IS NOT NULL
        GROUP BY p.confidence
        ORDER BY p.confidence
    ''')
    for row in cursor.fetchall():
        stats['third_accuracy'][row[0]] = {
            'total': row[1],
            'correct': row[2],
            'rate': round(100.0 * row[2] / row[1], 2) if row[1] > 0 else 0
        }

    # 三連単的中率
    cursor.execute(f'''
        WITH trifecta_predictions AS (
            SELECT
                rp.race_id,
                MAX(CASE WHEN rp.rank_prediction = 1 THEN rp.confidence END) as confidence,
                MAX(CASE WHEN rp.rank_prediction = 1 THEN rp.pit_number END) as pred_1st,
                MAX(CASE WHEN rp.rank_prediction = 2 THEN rp.pit_number END) as pred_2nd,
                MAX(CASE WHEN rp.rank_prediction = 3 THEN rp.pit_number END) as pred_3rd
            FROM race_predictions rp
            JOIN races r ON rp.race_id = r.id
            WHERE r.race_date LIKE '{year}%'
              AND rp.prediction_type = 'before'
              AND rp.rank_prediction <= 3
            GROUP BY rp.race_id
        ),
        actual_trifecta AS (
            SELECT
                race_id,
                MAX(CASE WHEN rank = '1' THEN pit_number END) as actual_1st,
                MAX(CASE WHEN rank = '2' THEN pit_number END) as actual_2nd,
                MAX(CASE WHEN rank = '3' THEN pit_number END) as actual_3rd
            FROM results
            WHERE rank IN ('1', '2', '3')
            GROUP BY race_id
        )
        SELECT
            tp.confidence,
            COUNT(*) as total,
            SUM(CASE
                WHEN tp.pred_1st = at.actual_1st
                AND tp.pred_2nd = at.actual_2nd
                AND tp.pred_3rd = at.actual_3rd
                THEN 1 ELSE 0 END) as correct
        FROM trifecta_predictions tp
        JOIN actual_trifecta at ON tp.race_id = at.race_id
        WHERE tp.confidence IS NOT NULL
        GROUP BY tp.confidence
        ORDER BY tp.confidence
    ''')
    for row in cursor.fetchall():
        stats['trifecta_accuracy'][row[0]] = {
            'total': row[1],
            'correct': row[2],
            'rate': round(100.0 * row[2] / row[1], 2) if row[1] > 0 else 0
        }

    conn.close()
    return stats


def generate_status_markdown(enabled_flags: dict, disabled_flags: dict, stats: dict) -> str:
    """ステータスMarkdownを生成"""
    now = datetime.now().strftime('%Y-%m-%d')

    md = f"""# 予測システム現状ステータス

**最終更新**: {now}
**更新方法**: `python scripts/maintenance/extract_current_config.py`

---

## 1. 現在の性能指標

### 測定条件

| 項目 | 値 |
|------|-----|
| **データセット** | {stats['year']}年 before予測 |
| **期間** | {stats['min_date']} 〜 {stats['max_date']} |
| **対象レース数** | {stats['total_races']:,} レース |
| **prediction_type** | before |

### 1着的中率（信頼度別）

| 信頼度 | 的中 | 総数 | 的中率 |
|--------|------|------|--------|
"""
    for conf in ['A', 'B', 'C', 'D', 'E']:
        if conf in stats['first_accuracy']:
            data = stats['first_accuracy'][conf]
            md += f"| **{conf}** | {data['correct']:,} | {data['total']:,} | **{data['rate']:.2f}%** |\n"

    md += """
### 2着的中率（信頼度別）

| 信頼度 | 的中 | 総数 | 的中率 |
|--------|------|------|--------|
"""
    for conf in ['A', 'B', 'C', 'D', 'E']:
        if conf in stats['second_accuracy']:
            data = stats['second_accuracy'][conf]
            md += f"| **{conf}** | {data['correct']:,} | {data['total']:,} | **{data['rate']:.2f}%** |\n"

    md += """
### 3着的中率（信頼度別）

| 信頼度 | 的中 | 総数 | 的中率 |
|--------|------|------|--------|
"""
    for conf in ['A', 'B', 'C', 'D', 'E']:
        if conf in stats['third_accuracy']:
            data = stats['third_accuracy'][conf]
            md += f"| **{conf}** | {data['correct']:,} | {data['total']:,} | **{data['rate']:.2f}%** |\n"

    md += """
### 三連単的中率（信頼度別）

| 信頼度 | 的中 | 総数 | 的中率 |
|--------|------|------|--------|
"""
    for conf in ['A', 'B', 'C', 'D', 'E']:
        if conf in stats['trifecta_accuracy']:
            data = stats['trifecta_accuracy'][conf]
            md += f"| **{conf}** | {data['correct']:,} | {data['total']:,} | **{data['rate']:.2f}%** |\n"

    md += """
---

## 2. 有効なフィーチャーフラグ

**更新日**: """ + now + """
**ソース**: `config/feature_flags.py`

### 有効なフラグ一覧

| フラグ名 | 状態 | テスト結果 |
|----------|------|------------|
"""
    for name, info in sorted(enabled_flags.items()):
        risk_info = info.get('risk_info', {})
        test_result = risk_info.get('test_result', '-')
        if isinstance(test_result, str) and len(test_result) > 50:
            test_result = test_result[:47] + '...'
        md += f"| `{name}` | ON | {test_result} |\n"

    md += """
### 無効化中のフラグ

| フラグ名 | 状態 | 理由 |
|----------|------|------|
"""
    for name, info in sorted(disabled_flags.items()):
        risk_info = info.get('risk_info', {})
        status = risk_info.get('status', '-')
        md += f"| `{name}` | OFF | {status} |\n"

    md += """
---

## 3. ベンチマーク実行方法

### 標準ベンチマーク

```bash
# 2025年before予測で性能測定
python scripts/benchmark_prediction_system.py
```

### 前回比較

```bash
# 前回の結果と比較
python scripts/benchmark_prediction_system.py --compare
```

### 設定抽出

```bash
# 現在のフラグ・設定をこのファイルに反映
python scripts/maintenance/extract_current_config.py
```

### 変更追跡

```bash
# 変更前後の性能差分を記録
python scripts/benchmark_prediction_system.py --save-baseline
# （フラグ変更後）
python scripts/benchmark_prediction_system.py --compare
python scripts/maintenance/track_performance_change.py --description "変更内容"
```

---

## 4. 関連ファイル

| ファイル | 説明 |
|----------|------|
| [config/feature_flags.py](../../config/feature_flags.py) | フィーチャーフラグ定義 |
| [config/settings.py](../../config/settings.py) | スコアリング重み設定 |
| [scripts/benchmark_prediction_system.py](../../scripts/benchmark_prediction_system.py) | ベンチマークスクリプト |
| [data/benchmark_results/](../../data/benchmark_results/) | ベンチマーク結果保存先 |

---

**自動更新**: `python scripts/maintenance/extract_current_config.py` で最新状態に更新
"""
    return md


def main():
    """メイン処理"""
    print("=" * 70)
    print("設定抽出スクリプト")
    print(f"実行時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    # データベースパス
    db_path = os.path.join(PROJECT_ROOT, 'data', 'boatrace.db')
    if not os.path.exists(db_path):
        print(f"[ERROR] データベースが見つかりません: {db_path}")
        sys.exit(1)

    # フラグ取得
    print("\n[1/3] フィーチャーフラグを取得中...")
    enabled, disabled = get_enabled_flags()
    print(f"  有効: {len(enabled)}個, 無効: {len(disabled)}個")

    # 統計取得
    print("\n[2/3] 予測統計を取得中...")
    stats = get_prediction_stats(db_path, '2025')
    print(f"  対象レース数: {stats['total_races']:,}")
    print(f"  期間: {stats['min_date']} 〜 {stats['max_date']}")

    # Markdown生成
    print("\n[3/3] ステータスドキュメントを生成中...")
    md_content = generate_status_markdown(enabled, disabled, stats)

    # ファイル書き出し
    output_path = os.path.join(PROJECT_ROOT, 'docs', 'guides', 'PREDICTION_SYSTEM_STATUS.md')
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(md_content)

    print(f"\n[完了] {output_path}")
    print("=" * 70)


if __name__ == '__main__':
    main()
