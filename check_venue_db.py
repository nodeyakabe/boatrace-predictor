"""データベース内の会場データを確認"""
import sys
sys.path.append('src')

from database.venue_data import VenueDataManager
from config.settings import DATABASE_PATH

mgr = VenueDataManager(DATABASE_PATH)

# 全会場数
venues = mgr.get_all_venues()
print(f'登録会場数: {len(venues)}')

# 桐生のデータ詳細
if len(venues) > 0:
    venue = mgr.get_venue_data('01')
    if venue:
        print(f'\n桐生のデータ:')
        for k, v in venue.items():
            print(f'  {k}: {v}')
    else:
        print('\n桐生のデータが見つかりません')
else:
    print('\n会場データがDBに登録されていません')
    print('会場データを取得してください:')
    print('  python fetch_venue_data.py')
