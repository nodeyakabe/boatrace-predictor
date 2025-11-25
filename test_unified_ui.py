"""
統合UI動作確認テスト
"""
import sys
import os

# プロジェクトルートをパスに追加
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

print("=" * 60)
print("統合UI動作確認テスト")
print("=" * 60)

# 1. インポートテスト
print("\n[1] インポートテスト...")
try:
    from ui.components.unified_race_list import render_unified_race_list
    print("  [OK] unified_race_list.py")
except Exception as e:
    print(f"  [ERROR] unified_race_list.py - {e}")

try:
    from ui.components.unified_race_detail import render_unified_race_detail
    print("  [OK] unified_race_detail.py")
except Exception as e:
    print(f"  [ERROR] unified_race_detail.py - {e}")

# 2. 依存モジュールテスト
print("\n[2] 依存モジュールテスト...")
required_modules = [
    'src.analysis.realtime_predictor',
    'src.analysis.race_predictor',
    'src.betting.bet_generator',
    'src.betting.race_scorer',
    'src.prediction.integrated_predictor',
    'ui.components.common.widgets',
    'ui.components.common.db_utils'
]

for module_name in required_modules:
    try:
        __import__(module_name)
        print(f"  [OK] {module_name}")
    except Exception as e:
        print(f"  [ERROR] {module_name} - {e}")

# 3. データベース接続テスト
print("\n[3] データベース接続テスト...")
try:
    from config.settings import DATABASE_PATH
    import sqlite3

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM races")
    race_count = cursor.fetchone()[0]
    conn.close()

    print(f"  [OK] データベース接続 - OK")
    print(f"  [OK] レース数: {race_count:,}件")
except Exception as e:
    print(f"  [ERROR] データベース接続 - エラー: {e}")

# 4. 旧コンポーネントの状態確認
print("\n[4] 旧コンポーネントの状態確認...")
old_components = [
    'ui/components/realtime_dashboard.py',
    'ui/components/integrated_prediction.py',
    'ui/components/smart_recommendations.py',
    'ui/components/prediction_viewer.py'
]

for component in old_components:
    if os.path.exists(component):
        print(f"  [INFO] {component} - 存在（統合後は削除可能）")
    else:
        print(f"  - {component} - 存在しない")

# 5. 新コンポーネントの確認
print("\n[5] 新コンポーネントの確認...")
new_components = [
    'ui/components/unified_race_list.py',
    'ui/components/unified_race_detail.py'
]

for component in new_components:
    if os.path.exists(component):
        file_size = os.path.getsize(component)
        print(f"  [OK] {component} - 存在 ({file_size:,} bytes)")
    else:
        print(f"  [ERROR] {component} - 存在しない")

print("\n" + "=" * 60)
print("テスト完了")
print("=" * 60)
print("\n次のステップ:")
print("1. Streamlitアプリを起動: streamlit run ui/app_v2.py")
print("2. ブラウザで「レース予想」タブを確認")
print("3. 「レース一覧・推奨」で一覧表示をテスト")
print("4. 「詳細」ボタンで詳細画面への遷移をテスト")
print("5. 問題なければ旧コンポーネント4ファイルを削除可能")
print("=" * 60)
