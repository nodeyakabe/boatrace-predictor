#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
未使用UIコンポーネント削除スクリプト

app.pyから参照されていない古いUIコンポーネントを削除
"""
import sys
import os

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import shutil
from pathlib import Path
from datetime import datetime


# 削除対象ファイル
UNUSED_COMPONENTS = [
    'betting_recommendation.py',      # unified_race_detailに統合済み
    'hybrid_prediction.py',           # integrated_predictionと重複
    'integrated_prediction.py',       # unified_race_detailに統合済み
    'original_tenji_collector.py',    # 小さいファイル、おそらく古い実装
    'prediction_viewer.py',           # unified_race_listに統合済み
    'realtime_dashboard.py',          # 未使用
    'smart_recommendations.py',       # 未使用、関数なし
    'stage2_training.py',             # model_trainingで対応
    'venue_strategy.py',              # venue_analysisと重複の可能性
]


def create_backup_dir():
    """バックアップディレクトリを作成"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_dir = Path(f'backups/ui_components_cleanup_{timestamp}')
    backup_dir.mkdir(parents=True, exist_ok=True)
    return backup_dir


def main():
    print("="*70)
    print("未使用UIコンポーネント削除")
    print("="*70)

    ui_components_dir = Path('ui/components')

    if not ui_components_dir.exists():
        print(f"\n❌ {ui_components_dir} が見つかりません")
        return

    # バックアップディレクトリ作成
    backup_dir = create_backup_dir()
    print(f"\nバックアップ先: {backup_dir}")

    print(f"\n削除対象: {len(UNUSED_COMPONENTS)}ファイル")

    deleted = []
    not_found = []

    for filename in UNUSED_COMPONENTS:
        filepath = ui_components_dir / filename

        if not filepath.exists():
            print(f"  ⚠️  {filename} - 既に存在しません")
            not_found.append(filename)
            continue

        # バックアップ
        backup_filepath = backup_dir / filename
        shutil.copy2(filepath, backup_filepath)

        # 削除
        filepath.unlink()
        deleted.append(filename)
        print(f"  ✓ {filename} - 削除しました")

    print("\n" + "="*70)
    print("削除完了")
    print("="*70)
    print(f"\n削除: {len(deleted)}ファイル")
    print(f"見つからず: {len(not_found)}ファイル")

    if deleted:
        print("\n【削除されたファイル】")
        for f in deleted:
            print(f"  - {f}")

    if not_found:
        print("\n【既に存在しないファイル】")
        for f in not_found:
            print(f"  - {f}")

    print(f"\n【バックアップ保存先】")
    print(f"  {backup_dir.absolute()}")

    print("\n【残存UIコンポーネント数】")
    remaining = list(ui_components_dir.glob('*.py'))
    remaining = [f for f in remaining if f.name != '__init__.py']
    print(f"  {len(remaining)}ファイル")

    print("\n" + "="*70)


if __name__ == "__main__":
    # 確認プロンプト
    print("未使用UIコンポーネントを削除します。")
    print(f"削除対象: {len(UNUSED_COMPONENTS)}ファイル")
    print("\n削除対象リスト:")
    for f in UNUSED_COMPONENTS:
        print(f"  - {f}")

    response = input("\n実行しますか? (yes/no): ")

    if response.lower() in ['yes', 'y']:
        main()
    else:
        print("キャンセルされました")
