"""
設定ファイルの確認
"""

from config.settings import VENUES

print("=" * 60)
print("設定ファイル確認")
print("=" * 60)

print("\n登録されている競艇場:")
for key, venue in VENUES.items():
    print(f"  {key}: {venue['name']}（コード: {venue['code']}）")

print("\n" + "=" * 60)
