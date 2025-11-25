"""
過去データのアクセス可能性をテストするスクリプト
"""

import requests
from datetime import datetime, timedelta

def test_data_availability():
    """様々な過去日付でデータが取得可能か確認"""
    
    base_url = "https://www.boatrace.jp/owpc/pc/race/racelist"
    
    # テスト対象日付
    test_dates = [
        ("20240101", "2024-01-01"),  # 1年前
        ("20230601", "2023-06-01"),  # 1.5年前
        ("20230101", "2023-01-01"),  # 2年前
        ("20221201", "2022-12-01"),  # 現在のDBの最古付近
        ("20221101", "2022-11-01"),  # 現在のDBの最古
        ("20221001", "2022-10-01"),  # 現在のDBより前
        ("20220601", "2022-06-01"),  # 2.5年前
        ("20220101", "2022-01-01"),  # 3年前
        ("20210601", "2021-06-01"),  # 3.5年前
        ("20210101", "2021-01-01"),  # 4年前
        ("20200601", "2020-06-01"),  # 4.5年前
        ("20200115", "2020-01-15"),  # 5年前（元のスクリプトの開始日付近）
    ]
    
    print("=" * 80)
    print("過去データアクセス可能性テスト")
    print("=" * 80)
    print("\n公式サイト: https://www.boatrace.jp/owpc/pc/race/racelist")
    print("テスト会場: 01 (桐生)\n")
    
    results = []
    
    for date_str, human_date in test_dates:
        url = f"{base_url}?jcd=01&hd={date_str}"
        
        try:
            response = requests.get(url, timeout=10)
            status = response.status_code
            
            # HTMLの内容をチェック
            html = response.text
            
            # データが存在するかの判定
            has_data = False
            error_indicators = [
                "レース情報が存在しません",
                "該当するデータがありません",
                "データが見つかりません",
                "not found",
                "エラー"
            ]
            
            # レース情報の存在を示す要素をチェック
            data_indicators = [
                "is-fs14",  # レース番号表示クラス
                "table1",   # レース表テーブル
                "racetable",
                "race_table"
            ]
            
            has_error = any(indicator in html.lower() for indicator in error_indicators)
            has_race_data = any(indicator in html for indicator in data_indicators)
            
            if status == 200 and not has_error and has_race_data:
                has_data = True
                result = "✅ データあり"
            elif status == 200 and not has_error:
                result = "⚠️  ページは取得できたがレースデータ不明"
            elif status == 404:
                result = "❌ 404 Not Found"
            else:
                result = f"❌ HTTP {status}"
            
            results.append((human_date, date_str, status, result, has_data))
            print(f"{human_date} ({date_str}): {result}")
            print(f"  URL: {url}")
            print(f"  Status: {status}, HTML Length: {len(html):,} bytes")
            
        except requests.exceptions.Timeout:
            results.append((human_date, date_str, None, "❌ タイムアウト", False))
            print(f"{human_date} ({date_str}): ❌ タイムアウト")
        except Exception as e:
            results.append((human_date, date_str, None, f"❌ エラー: {e}", False))
            print(f"{human_date} ({date_str}): ❌ エラー: {e}")
        
        print()
    
    # サマリー
    print("=" * 80)
    print("サマリー")
    print("=" * 80)
    
    available_count = sum(1 for r in results if r[4])
    total_count = len(results)
    
    print(f"\n総テスト数: {total_count}")
    print(f"データ取得可能: {available_count}")
    print(f"データ取得不可: {total_count - available_count}")
    
    # 取得可能な最古の日付を特定
    if available_count > 0:
        oldest_available = None
        for r in reversed(results):
            if r[4]:
                oldest_available = r[0]
                break
        
        if oldest_available:
            print(f"\n✅ 取得可能な最古の日付: {oldest_available}")
    else:
        print("\n❌ テストした全ての日付でデータ取得不可")
    
    # 推奨事項
    print("\n【推奨事項】")
    if available_count == total_count:
        print("✅ 全ての過去データが取得可能です")
        print("   → fetch_historical_data.py を実行してデータを拡張できます")
    elif available_count > 0:
        print("⚠️  一部の過去データのみ取得可能です")
        print(f"   → {oldest_available}以降のデータを対象に収集スクリプトを実行してください")
    else:
        print("❌ 過去データの取得は困難です")
        print("   → 現在のデータ（2022-11-02以降）で運用することを推奨します")
    
    print("=" * 80)

if __name__ == "__main__":
    test_data_availability()
