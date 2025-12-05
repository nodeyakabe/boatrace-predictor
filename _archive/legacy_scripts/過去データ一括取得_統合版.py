"""
過去データ一括取得 - 統合版

これまでのトライ&エラーで得た知見を反映した、失敗しない過去データ取得スクリプト

実行方法:
  python 過去データ一括取得_統合版.py [開始日] [終了日]

  例: python 過去データ一括取得_統合版.py 2024-01-01 2024-01-31

知見まとめ:
1. レース基本情報・結果は公式サイトから確実に取得可能
2. 決まり手データは補完が必要（改善版を使用）
3. レース詳細データ（展示タイム等）はv4版を使用
4. 天候・風向データは改善版を使用
5. 潮位データはRDMDB（NEAR-GOOS）から取得
6. オリジナル展示データは過去分は取得不可（毎日手動実行が必要）
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import sqlite3
from datetime import datetime, timedelta
import subprocess
import os

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))


def run_script(script_name, description, args=None):
    """スクリプトを実行"""
    print(f"\n{'='*80}")
    print(f"{description}")
    print(f"{'='*80}")

    python_exe = os.path.join(PROJECT_ROOT, 'venv', 'Scripts', 'python.exe')
    script_path = os.path.join(PROJECT_ROOT, script_name)

    cmd = [python_exe, script_path]
    if args:
        cmd.extend(args)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
            encoding='utf-8'
        )

        if result.stdout:
            print(result.stdout)

        if result.returncode != 0:
            print(f"⚠️ エラーが発生しましたが、処理を続行します")
            if result.stderr:
                print(f"エラー詳細: {result.stderr[:500]}")
            return False

        return True

    except Exception as e:
        print(f"❌ 実行エラー: {e}")
        return False


def main():
    if len(sys.argv) < 3:
        print("使用方法: python 過去データ一括取得_統合版.py [開始日] [終了日]")
        print("例: python 過去データ一括取得_統合版.py 2024-01-01 2024-01-31")
        sys.exit(1)

    start_date_str = sys.argv[1]
    end_date_str = sys.argv[2]

    # 日付検証
    try:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
    except ValueError:
        print("❌ 日付形式が不正です。YYYY-MM-DD形式で指定してください")
        sys.exit(1)

    if start_date > end_date:
        print("❌ 開始日が終了日より後になっています")
        sys.exit(1)

    days = (end_date - start_date).days + 1

    print("="*80)
    print("過去データ一括取得 - 統合版")
    print("="*80)
    print(f"期間: {start_date_str} ～ {end_date_str} ({days}日間)")
    print()
    print("【これまでの知見を反映した取得手順】")
    print("  1. レース基本情報（公式サイト）")
    print("  2. 結果データ（公式サイト）")
    print("  3. 決まり手データ（改善版）")
    print("  4. レース詳細データv4（展示タイム等）")
    print("  5. 天候データ（改善版）")
    print("  6. 風向データ（改善版）")
    print()
    print("【注意事項】")
    print("  - 潮位データは別途RDMDB収集スクリプトを実行してください")
    print("  - オリジナル展示データは過去分取得不可（毎日手動実行が必要）")
    print("="*80)

    input("\nEnterキーを押すと取得を開始します...")

    # データベース接続して事前確認
    conn = sqlite3.connect('data/boatrace.db')
    cursor = conn.cursor()

    # 既存データ確認
    cursor.execute("""
        SELECT COUNT(*) FROM races
        WHERE race_date BETWEEN ? AND ?
    """, (start_date_str, end_date_str))
    existing_races = cursor.fetchone()[0]

    if existing_races > 0:
        print(f"\n既に{existing_races}件のレースデータが存在します")
        choice = input("上書きして続行しますか？ (y/N): ")
        if choice.lower() != 'y':
            print("処理を中止しました")
            conn.close()
            sys.exit(0)

    conn.close()

    # 実行するスクリプト一覧（順番重要）
    tasks = [
        # ステップ1: レース基本情報と結果（BulkScraperで一括取得）
        {
            'skip': True,  # BulkScraperはUIから実行を推奨
            'description': "レース基本情報と結果データを取得"
        },

        # ステップ2: 結果データ補完
        {
            'script': '補完_結果データ.py',
            'description': "結果データを補完"
        },

        # ステップ3: 決まり手データ（改善版）
        {
            'script': '補完_決まり手データ_改善版.py',
            'description': "決まり手データを補完（改善版 - エラーハンドリング強化）"
        },

        # ステップ4: レース詳細データv4（最新・最速版）
        {
            'script': '補完_レース詳細データ_改善版v4.py',
            'description': "レース詳細データv4を補完（展示タイム、モーター・ボート情報等）"
        },

        # ステップ5: 天候データ（改善版）
        {
            'script': '補完_天候データ_改善版.py',
            'description': "天候データを補完（改善版 - 気温・水温・波高）"
        },

        # ステップ6: 風向データ（改善版）
        {
            'script': '補完_風向データ_改善版.py',
            'description': "風向データを補完（改善版 - 風速・風向）"
        },
    ]

    # 実行
    success_count = 0
    failure_count = 0

    for i, task in enumerate(tasks, 1):
        if task.get('skip'):
            print(f"\n[{i}/{len(tasks)}] {task['description']}")
            print("→ UIから実行してください（「📥 過去データ取得」タブ）")
            continue

        print(f"\n[{i}/{len(tasks)}] 実行中...")
        if run_script(task['script'], task['description']):
            success_count += 1
        else:
            failure_count += 1

    # 最終レポート
    print("\n" + "="*80)
    print("データ取得完了")
    print("="*80)
    print(f"成功: {success_count}タスク")
    print(f"失敗: {failure_count}タスク")

    # 最終データ確認
    conn = sqlite3.connect('data/boatrace.db')
    cursor = conn.cursor()

    print("\n【取得データ確認】")

    # レース数
    cursor.execute("""
        SELECT COUNT(*) FROM races
        WHERE race_date BETWEEN ? AND ?
    """, (start_date_str, end_date_str))
    race_count = cursor.fetchone()[0]
    print(f"  レース数: {race_count:,}件")

    # 結果データ
    cursor.execute("""
        SELECT COUNT(*) FROM results r
        JOIN races ra ON r.race_id = ra.id
        WHERE ra.race_date BETWEEN ? AND ?
    """, (start_date_str, end_date_str))
    result_count = cursor.fetchone()[0]
    print(f"  結果データ: {result_count:,}件")

    # 決まり手データ
    cursor.execute("""
        SELECT COUNT(*) FROM results r
        JOIN races ra ON r.race_id = ra.id
        WHERE ra.race_date BETWEEN ? AND ?
        AND r.kimarite IS NOT NULL
    """, (start_date_str, end_date_str))
    kimarite_count = cursor.fetchone()[0]
    if result_count > 0:
        print(f"  決まり手データ: {kimarite_count:,}件 ({kimarite_count/result_count*100:.1f}%)")

    # レース詳細データ
    cursor.execute("""
        SELECT COUNT(*) FROM race_details rd
        JOIN races ra ON rd.race_id = ra.id
        WHERE ra.race_date BETWEEN ? AND ?
    """, (start_date_str, end_date_str))
    detail_count = cursor.fetchone()[0]
    print(f"  レース詳細: {detail_count:,}件")

    # 天候データ
    cursor.execute("""
        SELECT COUNT(DISTINCT venue_code || '-' || weather_date) FROM weather
        WHERE weather_date BETWEEN ? AND ?
    """, (start_date_str, end_date_str))
    weather_count = cursor.fetchone()[0]
    print(f"  天候データ: {weather_count:,}件")

    conn.close()

    print("\n" + "="*80)
    print("🎉 すべての処理が完了しました！")
    print("="*80)

    print("\n【次のステップ】")
    print("  1. 潮位データを取得する場合:")
    print("     python 収集_RDMDB潮位データ_改善版.py")
    print()
    print("  2. オリジナル展示データは毎日手動で取得:")
    print("     python 収集_オリジナル展示_手動実行.py 0")
    print()
    print("  3. UIで確認:")
    print("     streamlit run ui/app.py --server.port 8502")


if __name__ == "__main__":
    main()
