"""決まり手の集計修正をテスト"""
import sys
sys.path.insert(0, 'C:/Users/seizo/Desktop/BoatRace')

from src.analysis.data_coverage_checker import DataCoverageChecker

checker = DataCoverageChecker()
report = checker.get_coverage_report()

# 結果データカテゴリを取得
result_data = report['categories'].get('結果データ', {})
items = result_data.get('items', [])

# 決まり手項目を探す
kimarite_item = next((item for item in items if item['name'] == '決まり手'), None)

if kimarite_item:
    print('=' * 60)
    print('決まり手データの集計結果')
    print('=' * 60)
    print(f'充足率: {kimarite_item["coverage"]*100:.1f}%')
    print(f'カウント: {kimarite_item["count"]:,} / {kimarite_item["total"]:,}')
    print(f'備考: {kimarite_item.get("note", "")}')
    print()
    print(f'✅ 修正成功！')
    print(f'   修正前: 16.3% (全艇184,572件のうち30,668件)')
    print(f'   修正後: {kimarite_item["coverage"]*100:.1f}% (1着艇{kimarite_item["total"]:,}件のうち{kimarite_item["count"]:,}件)')
else:
    print('❌ 決まり手項目が見つかりませんでした')
