"""
古いドキュメントをアーカイブするスクリプト

改善点_1118.md ⑩ ドキュメント整理
"""

import os
import shutil
from pathlib import Path
from datetime import datetime

# アーカイブ対象ファイル
ARCHIVE_FILES = {
    # 復元作業関連（2025-11-13）
    "archive_2025_11_13": [
        "復元作業報告_20251113.md",
        "機能比較レポート_復元版vs破損版.md",
        "欠落機能と復元計画.md",
        "復元完了_購入履歴とバックテスト追加.md",
        "復元完了_最終レポート.md",
        "復元完了_次回起動時の確認事項.txt",
        "PROJECT_BUG_REPORT_20251113.md",
        "CRITICAL_DISCOVERY_20251113.md",
        "FILE_ORGANIZATION_ANALYSIS_20251113.md",
        "EXECUTION_SUMMARY_20251113.md",
        "WORK_SUMMARY_20251113.md",
        "FINAL_WORK_SUMMARY_20251113.md",
        "COMPREHENSIVE_CODE_ANALYSIS_20251113.txt",
        "VENUE_ANALYZER_FIX_SUMMARY.txt",
    ],
    # 重複クイックスタート
    "archive_quickstart_duplicates": [
        "README_QUICK_START.md",
        "QUICK_START_GUIDE.md",
        "QUICK_START.md",
        "NEXT_SESSION_QUICKSTART.md",
        "README_WORK_GUIDE.md",
    ],
    # 古いレポート
    "archive_old_reports": [
        "ULTIMATE_SUMMARY_REPORT.md",
        "FINAL_SUMMARY_REPORT.md",
        "FINAL_EXPERIMENTS_REPORT.md",
        "MODEL_ANALYSIS_REPORT.md",
        "RACER_ANALYSIS_REPORT.md",
        "BACKTEST_COMPARISON_REPORT.md",
        "SMART_RECOMMENDATIONS_VERIFICATION.md",
        "PHASE_1-3_IMPLEMENTATION_SUMMARY.md",
        "PHASE_1-4_FINAL_REPORT.md",
    ],
    # 実験レポート
    "archive_experiments": [
        "EXPERIMENT_004_REPORT.md",
        "EXPERIMENT_005_REPORT.md",
        "EXPERIMENT_006_REPORT.md",
        "EXPERIMENT_007_REPORT.md",
        "EXPERIMENT_009B_REPORT.md",
        "EXPERIMENTS_SUMMARY_REPORT.md",
    ],
}

# 削除対象ファイル（デバッグ出力）
DELETE_FILES = [
    "test_output.txt",
    "st_debug_output.txt",
    "table3_output.txt",
    "table_debug.txt",
    "test_v4_output.txt",
    "tide_investigation_result.txt",
    "investigate_tide_url_output.txt",
    "exhibition_investigation.txt",
    "payout_analysis.txt",
    "table_info.txt",
]


def archive_documents(base_dir: str = ".", dry_run: bool = True):
    """
    古いドキュメントをアーカイブ

    Args:
        base_dir: プロジェクトのベースディレクトリ
        dry_run: Trueの場合は実行せずに計画を表示
    """
    base_path = Path(base_dir)
    docs_archive = base_path / "docs" / "archive"

    print("=" * 60)
    print("ドキュメントアーカイブスクリプト")
    print("=" * 60)

    if dry_run:
        print("\n[DRY RUN モード - 実際の移動は行いません]\n")

    # アーカイブ
    moved_count = 0
    for archive_name, files in ARCHIVE_FILES.items():
        archive_dir = docs_archive / archive_name

        if not dry_run:
            archive_dir.mkdir(parents=True, exist_ok=True)

        print(f"\n[DIR] {archive_name}/")

        for filename in files:
            src = base_path / filename
            dst = archive_dir / filename

            if src.exists():
                if dry_run:
                    print(f"  [移動予定] {filename}")
                else:
                    shutil.move(str(src), str(dst))
                    print(f"  [移動完了] {filename}")
                moved_count += 1
            else:
                print(f"  [存在しない] {filename}")

    # 削除
    deleted_count = 0
    print(f"\n[DELETE] 削除対象（デバッグ出力）:")

    for filename in DELETE_FILES:
        src = base_path / filename
        if src.exists():
            if dry_run:
                print(f"  [削除予定] {filename}")
            else:
                src.unlink()
                print(f"  [削除完了] {filename}")
            deleted_count += 1
        else:
            print(f"  [存在しない] {filename}")

    # サマリー
    print("\n" + "=" * 60)
    print("サマリー")
    print("=" * 60)
    print(f"アーカイブ対象: {moved_count}ファイル")
    print(f"削除対象: {deleted_count}ファイル")

    if dry_run:
        print("\n実際に実行するには、--execute オプションを付けて実行してください:")
        print("  python archive_old_docs.py --execute")
    else:
        print(f"\n✅ 完了: {moved_count}ファイルをアーカイブ、{deleted_count}ファイルを削除")

    return moved_count, deleted_count


def list_remaining_docs(base_dir: str = "."):
    """
    アーカイブ後に残るドキュメントを一覧表示
    """
    base_path = Path(base_dir)

    # 現在のmdファイル
    md_files = list(base_path.glob("*.md"))

    # アーカイブ対象を除外
    archive_set = set()
    for files in ARCHIVE_FILES.values():
        archive_set.update(files)

    remaining = [f for f in md_files if f.name not in archive_set]

    print("\n" + "=" * 60)
    print("アーカイブ後に残るドキュメント")
    print("=" * 60)

    for f in sorted(remaining, key=lambda x: x.name):
        print(f"  - {f.name}")

    print(f"\n合計: {len(remaining)}ファイル")


if __name__ == "__main__":
    import sys

    dry_run = "--execute" not in sys.argv

    archive_documents(dry_run=dry_run)
    list_remaining_docs()
