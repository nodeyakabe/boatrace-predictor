"""
テスト実行スクリプト
全テストを実行し、レポートを生成
"""
import subprocess
import sys
from datetime import datetime


def run_tests():
    """全テストを実行"""
    print("=" * 80)
    print("BoatRace システムテスト実行")
    print(f"実行日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    # pytest実行
    result = subprocess.run(
        [
            sys.executable, "-m", "pytest",
            "tests/",
            "-v",                    # 詳細表示
            "--tb=short",            # トレースバック簡潔表示
            "--durations=10",        # 遅いテストTOP10表示
            "--color=yes",           # カラー出力
            "-W", "ignore::DeprecationWarning",  # 非推奨警告を無視
        ],
        capture_output=False
    )

    print("\n" + "=" * 80)
    if result.returncode == 0:
        print("✅ 全テスト合格")
    else:
        print("❌ テスト失敗")
    print("=" * 80)

    return result.returncode


if __name__ == "__main__":
    exit_code = run_tests()
    sys.exit(exit_code)
