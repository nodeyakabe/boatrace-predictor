"""
DataManagerの動作テスト
"""
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from src.database.data_manager import DataManager
from config.settings import DATABASE_PATH

def test_data_manager_init():
    """DataManagerの初期化テスト"""
    print("="*70)
    print("DataManager初期化テスト")
    print("="*70)

    print(f"\nデータベースパス: {DATABASE_PATH}")
    print(f"パスの存在確認: {os.path.exists(DATABASE_PATH)}")
    print(f"親ディレクトリの存在確認: {os.path.exists(os.path.dirname(DATABASE_PATH))}")

    try:
        data_manager = DataManager()
        print("\n[OK] DataManagerの初期化成功")
        return True
    except Exception as e:
        print(f"\n[NG] DataManagerの初期化失敗: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_save_sample_race():
    """サンプルレースデータの保存テスト"""
    print("\n" + "="*70)
    print("サンプルレースデータ保存テスト")
    print("="*70)

    sample_race = {
        'venue_code': '01',
        'race_date': '20251114',
        'race_number': 1,
        'race_time': '10:30',
        'entries': [
            {
                'pit_number': 1,
                'racer_number': '1234',
                'racer_name': 'テスト選手1'
            },
            {
                'pit_number': 2,
                'racer_number': '5678',
                'racer_name': 'テスト選手2'
            }
        ]
    }

    try:
        data_manager = DataManager()
        result = data_manager.save_race_data(sample_race)

        if result:
            print("[OK] サンプルデータの保存成功")
            return True
        else:
            print("[NG] サンプルデータの保存失敗（戻り値がFalse）")
            return False

    except Exception as e:
        print(f"[NG] サンプルデータの保存中にエラー: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("\n" + "#"*70)
    print("# DataManager動作テスト")
    print("#"*70)

    results = []

    # テスト1: 初期化
    results.append(("DataManager初期化", test_data_manager_init()))

    # テスト2: サンプルデータ保存
    results.append(("サンプルデータ保存", test_save_sample_race()))

    # 結果サマリー
    print("\n" + "="*70)
    print("テスト結果サマリー")
    print("="*70)

    for test_name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"{status}: {test_name}")

    total_tests = len(results)
    passed_tests = sum(1 for _, result in results if result)

    print(f"\n合計: {passed_tests}/{total_tests} テスト成功")

    print("\n" + "#"*70)
