from src.analysis.data_coverage_checker import DataCoverageChecker

checker = DataCoverageChecker('data/boatrace.db')
report = checker.get_coverage_report()

print("="*60)
print("DATA QUALITY REPORT")
print("="*60)
print(f"Overall Score: {report['overall_score']*100:.1f}%")
print(f"Total Races: {report['total_races']:,}")
print()

print("Category Scores:")
print("-"*60)
for cat_name, cat_data in report['categories'].items():
    score = cat_data.get('score', 0) * 100
    print(f"{cat_name:20s}: {score:5.1f}%")

print()
print("="*60)
print("MISSING ITEMS (Coverage < 90%)")
print("="*60)

missing_items = checker.get_missing_items()
high_priority = [item for item in missing_items if item['coverage'] < 0.9]

if high_priority:
    for item in high_priority[:20]:
        print(f"[{item['category']}] {item['name']}")
        print(f"  Coverage: {item['coverage']*100:.1f}% | Importance: {'★'*item['importance']}")
        print(f"  Status: {item['status']}")
        if item.get('note'):
            print(f"  Note: {item['note']}")
        print()
else:
    print("No items with coverage < 90%")
