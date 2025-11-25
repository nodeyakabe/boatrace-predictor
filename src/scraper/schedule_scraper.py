"""
開催スケジュールスクレイパー
月間スケジュールから開催日を効率的に取得
"""

import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime, timedelta


class ScheduleScraper:
    """開催スケジュールスクレイパー"""

    def __init__(self, delay=1.0):
        """
        初期化

        Args:
            delay: リクエスト間の待機時間（秒）
        """
        self.base_url = "https://www.boatrace.jp/owpc/pc/race/monthlyschedule"
        self.delay = delay
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })

    def get_monthly_schedule(self, year, month):
        """
        指定月の開催スケジュールを取得

        Args:
            year: 年（例: 2024）
            month: 月（例: 10）

        Returns:
            dict: {
                競艇場コード: [日付リスト],
                '01': ['20241011', '20241020', '20241029'],
                '02': ['20241005', '20241013'],
                ...
            }
        """
        params = {
            "ym": f"{year}{month:02d}"
        }

        try:
            response = self.session.get(
                self.base_url,
                params=params,
                timeout=15
            )
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')

            # リンクからjcdとhdを抽出
            links = soup.find_all('a', href=True)

            schedule = {}

            for link in links:
                href = link.get('href', '')

                # jcd=XX と hd=YYYYMMDD を含むリンクを探す
                if 'jcd=' in href and 'hd=' in href:
                    # jcdを抽出
                    jcd_match = re.search(r'jcd=(\d+)', href)
                    # hdを抽出
                    hd_match = re.search(r'hd=(\d{8})', href)

                    if jcd_match and hd_match:
                        venue_code = jcd_match.group(1)
                        date_str = hd_match.group(1)

                        # 指定月のデータのみ
                        if date_str.startswith(f"{year}{month:02d}"):
                            if venue_code not in schedule:
                                schedule[venue_code] = []

                            if date_str not in schedule[venue_code]:
                                schedule[venue_code].append(date_str)

            # 各競艇場の日付をソート
            for venue_code in schedule:
                schedule[venue_code].sort()

            return schedule

        except Exception as e:
            print(f"月間スケジュール取得エラー ({year}/{month}): {e}")
            return {}

    def get_schedule_for_period(self, start_date, end_date):
        """
        期間内の開催スケジュールを取得

        Args:
            start_date: 開始日（datetime）
            end_date: 終了日（datetime）

        Returns:
            dict: {競艇場コード: [日付リスト]}
        """
        all_schedule = {}

        # 月ごとに取得
        current_date = start_date.replace(day=1)
        end_month = end_date.replace(day=1)

        while current_date <= end_month:
            print(f"スケジュール取得中: {current_date.year}年{current_date.month}月")

            monthly_schedule = self.get_monthly_schedule(
                current_date.year,
                current_date.month
            )

            # 指定期間内の日付のみフィルタ
            for venue_code, dates in monthly_schedule.items():
                if venue_code not in all_schedule:
                    all_schedule[venue_code] = []

                for date_str in dates:
                    date_obj = datetime.strptime(date_str, '%Y%m%d')

                    if start_date <= date_obj <= end_date:
                        all_schedule[venue_code].append(date_str)

            # 次の月へ
            if current_date.month == 12:
                current_date = current_date.replace(year=current_date.year + 1, month=1)
            else:
                current_date = current_date.replace(month=current_date.month + 1)

        return all_schedule

    def get_total_race_days(self, schedule):
        """
        総開催日数を計算

        Args:
            schedule: get_schedule_for_period()の戻り値

        Returns:
            int: 総開催日数（競艇場×日数）
        """
        total = 0
        for venue_code, dates in schedule.items():
            total += len(dates)
        return total

    def get_today_schedule(self):
        """
        本日の開催スケジュールを取得

        Returns:
            dict: {競艇場コード: 日付} 本日開催されている競艇場のリスト
            例: {'01': '20251030', '05': '20251030', ...}
        """
        today = datetime.now()
        today_str = today.strftime('%Y%m%d')

        # 今月のスケジュールを取得
        monthly_schedule = self.get_monthly_schedule(today.year, today.month)

        # 本日開催の競艇場のみ抽出
        today_schedule = {}
        for venue_code, dates in monthly_schedule.items():
            if today_str in dates:
                today_schedule[venue_code] = today_str

        return today_schedule

    def get_upcoming_races_today(self):
        """
        本日のこれから開催されるレースを取得

        Returns:
            list: [
                {
                    'venue_code': '01',
                    'date': '20251030',
                    'races_remaining': 8  # 残りレース数（推定）
                },
                ...
            ]
        """
        today_schedule = self.get_today_schedule()
        now = datetime.now()
        current_hour = now.hour
        current_minute = now.minute

        # レース時刻の推定（通常は10:00開始、30分間隔程度）
        # 簡易的に、現在時刻から残りレース数を推定
        races_per_day = 12
        estimated_completed = 0

        if current_hour >= 10:
            # 10:00スタート想定で、約30分間隔
            minutes_since_start = (current_hour - 10) * 60 + current_minute
            estimated_completed = min(int(minutes_since_start / 30), races_per_day)

        upcoming_races = []
        for venue_code, date in today_schedule.items():
            races_remaining = max(0, races_per_day - estimated_completed)
            if races_remaining > 0:
                upcoming_races.append({
                    'venue_code': venue_code,
                    'date': date,
                    'races_remaining': races_remaining
                })

        return upcoming_races

    def close(self):
        """セッションを閉じる"""
        self.session.close()


if __name__ == "__main__":
    # テスト実行
    scraper = ScheduleScraper()

    print("="*70)
    print("開催スケジュール取得テスト")
    print("="*70)

    # 2024年10月のスケジュールを取得
    schedule = scraper.get_monthly_schedule(2024, 10)

    print(f"\n2024年10月の開催スケジュール")
    print(f"競艇場数: {len(schedule)}")

    total_days = 0
    for venue_code in sorted(schedule.keys()):
        dates = schedule[venue_code]
        total_days += len(dates)
        print(f"  {venue_code}: {len(dates)}日 ({dates[0]} 〜 {dates[-1]})")

    print(f"\n総開催日数: {total_days}日")

    # 3ヶ月分のスケジュールを取得
    print("\n" + "="*70)
    print("3ヶ月分のスケジュール取得テスト")
    print("="*70)

    start_date = datetime(2024, 10, 1)
    end_date = datetime(2024, 12, 31)

    schedule_3months = scraper.get_schedule_for_period(start_date, end_date)

    print(f"\n2024年10月〜12月の開催スケジュール")
    print(f"競艇場数: {len(schedule_3months)}")

    total_days = scraper.get_total_race_days(schedule_3months)
    print(f"総開催日数: {total_days}日")

    # 推定レース数（1日12レース）
    estimated_races = total_days * 12
    print(f"推定レース数: {estimated_races}レース")

    # 従来方式との比較
    days_in_period = (end_date - start_date).days + 1
    print(f"\n【効率化の効果】")
    print(f"従来方式: {days_in_period * 24}回アクセス（全日×全競艇場）")
    print(f"新方式: {total_days}回アクセス（開催日のみ）")
    print(f"削減率: {(1 - total_days / (days_in_period * 24)) * 100:.1f}%")

    scraper.close()

    print("\n" + "="*70)
    print("テスト完了")
    print("="*70)
