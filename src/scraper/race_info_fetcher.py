"""
レース情報フェッチャー
番組表ページからレース種別情報（進入固定、グレード、女子戦、新人戦等）を取得
"""

import requests
from bs4 import BeautifulSoup
import time
import re
from typing import Dict, Optional, Tuple


class RaceInfoFetcher:
    """
    レース種別情報を取得するフェッチャー

    取得情報:
    - グレード（SG/G1/G2/G3/一般）
    - 進入固定レースか
    - 女子戦か
    - 新人戦か
    - ナイターレースか
    """

    def __init__(self, delay: float = 0.5):
        """
        初期化

        Args:
            delay: リクエスト間の待機時間（秒）
        """
        self.base_url = "https://www.boatrace.jp/owpc/pc/race/racelist"
        self.delay = delay
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })

        # ナイター開催場（夕方以降に開催）
        self.nighter_venues = ['01', '02', '06', '07', '12', '17', '20', '21', '24']

    def get_race_info(self, venue_code: str, date_str: str, race_number: int) -> Optional[Dict]:
        """
        レースの種別情報を取得

        Args:
            venue_code: 競艇場コード（例: "01"）
            date_str: 日付文字列（例: "20251130"）
            race_number: レース番号（1-12）

        Returns:
            dict: {
                'grade': グレード（SG/G1/G2/G3/一般）,
                'is_shinnyuu_kotei': 進入固定レースか（True/False）,
                'is_ladies': 女子戦か,
                'is_rookie': 新人戦か,
                'is_nighter': ナイターレースか,
                'race_title': レースタイトル
            }
            エラー時はNone
        """
        params = {
            "jcd": venue_code,
            "hd": date_str,
            "rno": race_number
        }

        try:
            response = self.session.get(
                self.base_url,
                params=params,
                timeout=15
            )
            response.raise_for_status()
            time.sleep(self.delay)

            soup = BeautifulSoup(response.text, 'html.parser')

            # レース情報を抽出
            race_info = self._extract_race_info(soup, venue_code)

            return race_info

        except Exception as e:
            print(f"レース情報取得エラー ({venue_code}, {date_str}, R{race_number}): {e}")
            return None

    def _extract_race_info(self, soup: BeautifulSoup, venue_code: str) -> Dict:
        """
        ページからレース情報を抽出

        Args:
            soup: BeautifulSoupオブジェクト
            venue_code: 会場コード

        Returns:
            レース情報の辞書
        """
        info = {
            'grade': '一般',
            'is_shinnyuu_kotei': False,
            'is_ladies': False,
            'is_rookie': False,
            'is_nighter': venue_code in self.nighter_venues,
            'race_title': ''
        }

        try:
            # レースタイトル/大会名を取得
            # 複数のセレクタで試行
            title_selectors = [
                'h2.heading2_titleName',
                'h2',
                '.heading2_titleName',
                '.race_title'
            ]

            title_text = ''
            for selector in title_selectors:
                elem = soup.select_one(selector)
                if elem:
                    title_text = elem.get_text(strip=True)
                    if title_text:
                        break

            info['race_title'] = title_text

            # ページ全体のテキストも取得（進入固定判定用）
            page_text = soup.get_text()

            # グレード判定
            info['grade'] = self._detect_grade(title_text, page_text)

            # 進入固定レース判定
            info['is_shinnyuu_kotei'] = self._detect_shinnyuu_kotei(title_text, page_text)

            # 女子戦判定
            info['is_ladies'] = self._detect_ladies(title_text, page_text)

            # 新人戦判定
            info['is_rookie'] = self._detect_rookie(title_text, page_text)

        except Exception as e:
            print(f"レース情報抽出エラー: {e}")

        return info

    def _detect_grade(self, title_text: str, page_text: str) -> str:
        """
        グレードを判定

        Args:
            title_text: タイトルテキスト
            page_text: ページ全体のテキスト

        Returns:
            グレード文字列
        """
        combined_text = f"{title_text} {page_text}"

        # SG判定（最優先）
        sg_patterns = ['SG', 'スペシャルグレード', 'グランプリ', 'クラシック', 'オールスター',
                       'オーシャンカップ', 'メモリアル', 'チャレンジカップ', 'ダービー']
        for pattern in sg_patterns:
            if pattern in combined_text:
                return 'SG'

        # G1判定
        g1_patterns = ['G1', 'GⅠ', 'G１', 'プレミアムG1']
        for pattern in g1_patterns:
            if pattern in combined_text:
                return 'G1'

        # G2判定
        g2_patterns = ['G2', 'GⅡ', 'G２']
        for pattern in g2_patterns:
            if pattern in combined_text:
                return 'G2'

        # G3判定
        g3_patterns = ['G3', 'GⅢ', 'G３']
        for pattern in g3_patterns:
            if pattern in combined_text:
                return 'G3'

        return '一般'

    def _detect_shinnyuu_kotei(self, title_text: str, page_text: str) -> bool:
        """
        進入固定レースかを判定

        進入固定レースは番組表に「進入固定」または「枠なり進入」などの
        表記がある場合に判定される

        Args:
            title_text: タイトルテキスト
            page_text: ページ全体のテキスト

        Returns:
            進入固定レースならTrue
        """
        combined_text = f"{title_text} {page_text}"

        # 進入固定のパターン
        kotei_patterns = [
            '進入固定',
            '枠なり進入',
            '枠番進入',
            '進入規制',
            '選抜戦',  # 選抜戦は進入固定のことが多い
            'シード戦'  # シード戦も進入固定のことがある
        ]

        for pattern in kotei_patterns:
            if pattern in combined_text:
                return True

        # 追加のパターンマッチ（正規表現）
        kotei_regex_patterns = [
            r'枠[番な]り',
            r'進入[固規]',
        ]

        for pattern in kotei_regex_patterns:
            if re.search(pattern, combined_text):
                return True

        return False

    def _detect_ladies(self, title_text: str, page_text: str) -> bool:
        """
        女子戦かを判定

        Args:
            title_text: タイトルテキスト
            page_text: ページ全体のテキスト

        Returns:
            女子戦ならTrue
        """
        combined_text = f"{title_text} {page_text}"

        ladies_patterns = [
            '女子',
            'レディース',
            'LADIES',
            'オールレディース',
            'ヴィーナスシリーズ',
        ]

        for pattern in ladies_patterns:
            if pattern in combined_text:
                return True

        return False

    def _detect_rookie(self, title_text: str, page_text: str) -> bool:
        """
        新人戦かを判定

        Args:
            title_text: タイトルテキスト
            page_text: ページ全体のテキスト

        Returns:
            新人戦ならTrue
        """
        combined_text = f"{title_text} {page_text}"

        rookie_patterns = [
            '新人',
            'ルーキー',
            'ROOKIE',
            'フレッシュ',
            'ルーキーシリーズ',
        ]

        for pattern in rookie_patterns:
            if pattern in combined_text:
                return True

        return False

    def get_day_race_info(self, venue_code: str, date_str: str) -> Dict[int, Dict]:
        """
        指定日の全レース（1-12R）の種別情報を一括取得

        Args:
            venue_code: 競艇場コード
            date_str: 日付文字列（YYYYMMDD）

        Returns:
            dict: {レース番号: レース情報} の辞書
        """
        all_info = {}

        for race_number in range(1, 13):
            info = self.get_race_info(venue_code, date_str, race_number)
            if info:
                all_info[race_number] = info

        return all_info

    def get_day_summary(self, venue_code: str, date_str: str) -> Dict:
        """
        指定日のレース種別サマリーを取得

        1レース目の情報からその日の開催情報を判定

        Args:
            venue_code: 競艇場コード
            date_str: 日付文字列

        Returns:
            開催サマリー情報
        """
        # 1Rの情報を取得（多くの場合、1Rの情報が開催全体を代表する）
        info = self.get_race_info(venue_code, date_str, 1)

        if not info:
            return {
                'grade': '一般',
                'is_ladies': False,
                'is_rookie': False,
                'is_nighter': venue_code in self.nighter_venues,
                'has_shinnyuu_kotei': False
            }

        return {
            'grade': info['grade'],
            'is_ladies': info['is_ladies'],
            'is_rookie': info['is_rookie'],
            'is_nighter': info['is_nighter'],
            'has_shinnyuu_kotei': info['is_shinnyuu_kotei'],
            'race_title': info['race_title']
        }

    def close(self):
        """セッションを閉じる"""
        self.session.close()


def detect_shinnyuu_kotei_from_entries(entries: list) -> bool:
    """
    出走表から進入固定レースを推定

    進入固定レースでは通常、枠番通りの進入（枠なり）になるため、
    過去の進入傾向と枠番が一致しているかどうかで推定する

    Args:
        entries: 出走表データのリスト

    Returns:
        進入固定と推定される場合True
    """
    # 出走表データから直接判定するのは難しいため、
    # ここでは番組表ページの情報を優先する
    # この関数は追加の補助的な判定として使用
    return False


if __name__ == "__main__":
    # テスト実行
    fetcher = RaceInfoFetcher()

    print("=" * 70)
    print("レース情報フェッチャーテスト")
    print("=" * 70)

    # テスト: 本日のレース情報を取得
    from datetime import datetime
    today = datetime.now().strftime('%Y%m%d')

    # 大村(24)の1Rをテスト
    print(f"\n大村 {today} 1R:")
    info = fetcher.get_race_info("24", today, 1)
    if info:
        print(f"  グレード: {info['grade']}")
        print(f"  進入固定: {info['is_shinnyuu_kotei']}")
        print(f"  女子戦: {info['is_ladies']}")
        print(f"  新人戦: {info['is_rookie']}")
        print(f"  ナイター: {info['is_nighter']}")
        print(f"  タイトル: {info['race_title']}")

    # 住之江(12)のサマリーをテスト
    print(f"\n住之江 {today} サマリー:")
    summary = fetcher.get_day_summary("12", today)
    print(f"  グレード: {summary['grade']}")
    print(f"  女子戦: {summary['is_ladies']}")
    print(f"  新人戦: {summary['is_rookie']}")
    print(f"  ナイター: {summary['is_nighter']}")
    print(f"  進入固定あり: {summary['has_shinnyuu_kotei']}")

    fetcher.close()

    print("\n" + "=" * 70)
    print("テスト完了")
    print("=" * 70)
