"""
競艇レース情報スクレイピング v2
selectolax対応版
"""

import logging
from datetime import datetime
from .base_scraper_v2 import BaseScraperV2
from config.settings import BOATRACE_OFFICIAL_URL

logger = logging.getLogger(__name__)


class RaceScraperV2(BaseScraperV2):
    """レース情報スクレイパー v2 (selectolax対応)"""

    def __init__(self):
        super().__init__()

    def get_race_list(self, venue_code, race_date):
        """
        指定日・指定場のレース一覧を取得

        Args:
            venue_code: 競艇場コード（例: "10" = 若松）
            race_date: レース日付（YYYYMMDD形式の文字列）

        Returns:
            レース情報のリスト
        """
        url = f"{BOATRACE_OFFICIAL_URL}/racelist"
        params = {
            "jcd": venue_code,
            "hd": race_date
        }

        tree = self.fetch_page(url, params)
        if not tree:
            return []

        races = []
        print(f"レース一覧取得: 競艇場コード={venue_code}, 日付={race_date}")

        return races

    def get_race_card(self, venue_code, race_date, race_number):
        """
        指定レースの出走表を取得

        Args:
            venue_code: 競艇場コード
            race_date: レース日付（YYYYMMDD形式）
            race_number: レース番号（1-12）

        Returns:
            出走表データの辞書
        """
        url = f"{BOATRACE_OFFICIAL_URL}/racelist"
        params = {
            "rno": race_number,
            "jcd": venue_code,
            "hd": race_date
        }

        tree = self.fetch_page(url, params)
        if not tree:
            return None

        # レース時刻を取得
        race_time = self._extract_race_time(tree, race_number)

        # レースグレードを取得
        race_grade = self._extract_race_grade(tree)

        # レース距離を取得
        race_distance = self._extract_race_distance(tree)

        # ナイター判定（専用会場は全レースナイター）
        is_nighter = 1 if str(venue_code).zfill(2) in self.NIGHTER_VENUES else 0

        # 女子戦・新人戦判定（gradeと同じ combined_text を再利用）
        is_ladies = self._extract_is_ladies(tree)
        is_rookie = self._extract_is_rookie(tree)

        race_data = {
            "venue_code": venue_code,
            "race_date": race_date,
            "race_number": race_number,
            "race_time": race_time,
            "race_grade": race_grade,
            "race_distance": race_distance,
            "is_nighter": is_nighter,
            "is_ladies": is_ladies,
            "is_rookie": is_rookie,
            "entries": []
        }

        # 出走表テーブルをパース
        entries = self.parse_race_card_table(tree)
        race_data["entries"] = entries

        print(f"出走表取得完了: 競艇場={venue_code}, 日付={race_date}, R{race_number}, 選手数={len(entries)}")

        return race_data

    def _extract_race_time(self, tree, race_number):
        """
        レース締切時刻を取得

        Args:
            tree: HTMLParserオブジェクト (selectolax)
            race_number: レース番号

        Returns:
            締切時刻（文字列）
        """
        try:
            # 締切予定時刻のテーブルを探す
            time_table = tree.css_first("table")
            if not time_table:
                return None

            # tbody内のtr要素を取得
            tbody = time_table.css_first("tbody")
            if not tbody:
                return None

            tr = tbody.css_first("tr")
            if not tr:
                return None

            # td要素を全て取得
            tds = tr.css("td")
            # td[0]は「締切予定時刻」ヘッダーなので、レース番号がそのままインデックス
            # 1R = td[1], 2R = td[2], ..., 12R = td[12]
            if len(tds) > race_number:
                time_text = tds[race_number].text().strip()
                return time_text
        except Exception as e:
            print(f"レース時刻抽出エラー: {e}")
            return None

    def _extract_racer_basic_info(self, racer_info_td):
        """選手基本情報を抽出"""
        info = {}

        # 登録番号と級別
        racer_num_div = racer_info_td.css_first("div.is-fs11")
        if racer_num_div:
            racer_text = racer_num_div.text().strip()
            parts = racer_text.split("/")
            if len(parts) >= 2:
                info["racer_number"] = parts[0].strip()
                info["racer_rank"] = parts[1].strip()

        # 選手名
        racer_name_div = racer_info_td.css_first("div.is-fs18.is-fBold")
        if racer_name_div:
            racer_link = racer_name_div.css_first("a")
            if racer_link:
                info["racer_name"] = racer_link.text().strip()

        return info

    def _extract_racer_details(self, racer_info_td):
        """選手詳細情報（支部、年齢、体重）を抽出"""
        info = {}

        details_divs = racer_info_td.css("div.is-fs11")
        if len(details_divs) >= 2:
            details_full_text = details_divs[1].text(deep=True)
            lines = [line.strip() for line in details_full_text.split('\n') if line.strip()]
            if len(lines) >= 2:
                # 支部/出身地
                home_parts = lines[0].split("/")
                if len(home_parts) >= 1:
                    info["racer_home"] = home_parts[0].strip()

                # 年齢/体重
                age_weight = lines[1].strip()
                age_weight_parts = age_weight.split("/")
                if len(age_weight_parts) >= 2:
                    try:
                        age = int(age_weight_parts[0].replace("歳", "").strip())
                        if 15 <= age <= 70:  # 妥当な年齢範囲
                            info["racer_age"] = age
                        else:
                            logger.warning(f"年齢が範囲外: {age}")
                            info["racer_age"] = None
                    except (ValueError, AttributeError) as e:
                        logger.error(f"年齢パースエラー: '{age_weight_parts[0]}' - {e}")
                        info["racer_age"] = None

                    try:
                        weight = float(age_weight_parts[1].replace("kg", "").strip())
                        if 40.0 <= weight <= 80.0:  # 妥当な体重範囲
                            info["racer_weight"] = weight
                        else:
                            logger.warning(f"体重が範囲外: {weight}")
                            info["racer_weight"] = None
                    except (ValueError, AttributeError) as e:
                        logger.error(f"体重パースエラー: '{age_weight_parts[1]}' - {e}")
                        info["racer_weight"] = None

        return info

    def _extract_fls_stats(self, fls_td):
        """F数/L数/平均ST統計を抽出"""
        info = {}

        fls_full_text = fls_td.text(deep=True)
        fls_lines = [line.strip() for line in fls_full_text.split('\n') if line.strip()]
        if len(fls_lines) >= 3:
            f_str = fls_lines[0].replace("F", "").strip()
            l_str = fls_lines[1].replace("L", "").strip()
            st_str = fls_lines[2].strip()

            # F数の安全なパース
            if f_str and f_str != '-':
                try:
                    info["f_count"] = int(f_str)
                except (ValueError, AttributeError) as e:
                    logger.error(f"F数パースエラー: '{f_str}' - {e}")
                    info["f_count"] = 0
            else:
                info["f_count"] = 0

            # L数の安全なパース
            if l_str and l_str != '-':
                try:
                    info["l_count"] = int(l_str)
                except (ValueError, AttributeError) as e:
                    logger.error(f"L数パースエラー: '{l_str}' - {e}")
                    info["l_count"] = 0
            else:
                info["l_count"] = 0

            # 平均STの安全なパース（0.10〜0.20が通常範囲）
            if st_str and st_str != '-':
                try:
                    avg_st = float(st_str)
                    if 0.0 <= avg_st <= 1.0:
                        info["avg_st"] = avg_st
                    else:
                        logger.warning(f"平均STが範囲外: {avg_st}")
                        info["avg_st"] = 0.0
                except (ValueError, AttributeError) as e:
                    logger.error(f"平均STパースエラー: '{st_str}' - {e}")
                    info["avg_st"] = 0.0
            else:
                info["avg_st"] = 0.0

        return info

    def _extract_performance_stats(self, td, prefix=""):
        """成績統計（全国/当地）を抽出"""
        info = {}

        full_text = td.text(deep=True)
        lines = [line.strip() for line in full_text.split('\n') if line.strip()]
        if len(lines) >= 3:
            win_str = lines[0].strip()
            second_str = lines[1].strip()
            third_str = lines[2].strip()

            # 勝率（通常0〜10の範囲）
            if win_str and win_str != '-':
                try:
                    win_rate = float(win_str)
                    if 0.0 <= win_rate <= 10.0:
                        info[f"{prefix}win_rate"] = win_rate
                    else:
                        logger.warning(f"勝率が範囲外: {win_rate}")
                        info[f"{prefix}win_rate"] = max(0.0, min(win_rate, 10.0))
                except (ValueError, AttributeError) as e:
                    logger.error(f"勝率パースエラー: '{win_str}' - {e}")
                    info[f"{prefix}win_rate"] = 0.0
            else:
                info[f"{prefix}win_rate"] = 0.0

            # 2連率（通常0〜100の範囲）
            if second_str and second_str != '-':
                try:
                    second_rate = float(second_str)
                    if 0.0 <= second_rate <= 100.0:
                        info[f"{prefix}second_rate"] = second_rate
                    else:
                        logger.warning(f"2連率が範囲外: {second_rate}")
                        info[f"{prefix}second_rate"] = max(0.0, min(second_rate, 100.0))
                except (ValueError, AttributeError) as e:
                    logger.error(f"2連率パースエラー: '{second_str}' - {e}")
                    info[f"{prefix}second_rate"] = 0.0
            else:
                info[f"{prefix}second_rate"] = 0.0

            # 3連率（通常0〜100の範囲）
            if third_str and third_str != '-':
                try:
                    third_rate = float(third_str)
                    if 0.0 <= third_rate <= 100.0:
                        info[f"{prefix}third_rate"] = third_rate
                    else:
                        logger.warning(f"3連率が範囲外: {third_rate}")
                        info[f"{prefix}third_rate"] = max(0.0, min(third_rate, 100.0))
                except (ValueError, AttributeError) as e:
                    logger.error(f"3連率パースエラー: '{third_str}' - {e}")
                    info[f"{prefix}third_rate"] = 0.0
            else:
                info[f"{prefix}third_rate"] = 0.0

        return info

    def _extract_equipment_stats(self, td, equipment_type):
        """モーター/ボート統計を抽出"""
        info = {}

        full_text = td.text(deep=True)
        lines = [line.strip() for line in full_text.split('\n') if line.strip()]
        if len(lines) >= 3:
            num_str = lines[0].strip()
            second_str = lines[1].strip()
            third_str = lines[2].strip()

            # モーター/ボート番号の安全なパース
            if num_str and num_str != '-':
                try:
                    number = int(num_str)
                    if 1 <= number <= 999:  # 妥当な範囲
                        info[f"{equipment_type}_number"] = number
                    else:
                        logger.warning(f"{equipment_type}番号が範囲外: {number}")
                        info[f"{equipment_type}_number"] = 0
                except (ValueError, AttributeError) as e:
                    logger.error(f"{equipment_type}番号パースエラー: '{num_str}' - {e}")
                    info[f"{equipment_type}_number"] = 0
            else:
                info[f"{equipment_type}_number"] = 0

            # 2連率の安全なパース
            if second_str and second_str != '-':
                try:
                    second_rate = float(second_str)
                    if 0.0 <= second_rate <= 100.0:
                        info[f"{equipment_type}_second_rate"] = second_rate
                    else:
                        logger.warning(f"{equipment_type} 2連率が範囲外: {second_rate}")
                        info[f"{equipment_type}_second_rate"] = max(0.0, min(second_rate, 100.0))
                except (ValueError, AttributeError) as e:
                    logger.error(f"{equipment_type} 2連率パースエラー: '{second_str}' - {e}")
                    info[f"{equipment_type}_second_rate"] = 0.0
            else:
                info[f"{equipment_type}_second_rate"] = 0.0

            # 3連率の安全なパース
            if third_str and third_str != '-':
                try:
                    third_rate = float(third_str)
                    if 0.0 <= third_rate <= 100.0:
                        info[f"{equipment_type}_third_rate"] = third_rate
                    else:
                        logger.warning(f"{equipment_type} 3連率が範囲外: {third_rate}")
                        info[f"{equipment_type}_third_rate"] = max(0.0, min(third_rate, 100.0))
                except (ValueError, AttributeError) as e:
                    logger.error(f"{equipment_type} 3連率パースエラー: '{third_str}' - {e}")
                    info[f"{equipment_type}_third_rate"] = 0.0
            else:
                info[f"{equipment_type}_third_rate"] = 0.0

        return info

    def parse_race_card_table(self, tree):
        """
        出走表のHTMLテーブルをパース (selectolax版)

        Args:
            tree: HTMLParserオブジェクト

        Returns:
            選手情報のリスト
        """
        entries = []

        try:
            # 出走表テーブルを探す
            table_div = tree.css_first("div.table1.is-tableFixed__3rdadd")
            if not table_div:
                print("出走表テーブルが見つかりません")
                return entries

            table = table_div.css_first("table")
            if not table:
                return entries

            # 各選手のデータは別々のtbodyタグで囲まれている
            tbodies = table.css("tbody.is-fs12")
            if not tbodies:
                print("選手データのtbodyが見つかりません")
                return entries

            # 各tbodyごとに処理（各選手）
            for tbody in tbodies:
                rows = tbody.css("tr")
                if len(rows) < 4:
                    continue

                # 最初の行から主要データを取得
                first_row = rows[0]
                tds = first_row.css("td")

                if len(tds) < 7:
                    continue

                # 枠番（1-6）の安全なパース
                try:
                    pit_number = int(tds[0].text().strip())
                    if not 1 <= pit_number <= 6:
                        logger.error(f"枠番が範囲外: {pit_number}")
                        continue
                    entry = {"pit_number": pit_number}
                except (ValueError, AttributeError) as e:
                    logger.error(f"枠番パースエラー: '{tds[0].text()}' - {e}")
                    continue

                # 選手情報（3番目のtd）
                racer_info_td = tds[2]
                entry.update(self._extract_racer_basic_info(racer_info_td))
                entry.update(self._extract_racer_details(racer_info_td))

                # F数/L数/平均ST（4番目のtd）
                entry.update(self._extract_fls_stats(tds[3]))

                # 全国成績（5番目のtd）
                entry.update(self._extract_performance_stats(tds[4], prefix=""))

                # 当地成績（6番目のtd、存在する場合）
                if len(tds) >= 6:
                    entry.update(self._extract_performance_stats(tds[5], prefix="local_"))

                # モーター情報（7番目のtd）
                if len(tds) >= 7:
                    entry.update(self._extract_equipment_stats(tds[6], equipment_type="motor"))

                # ボート情報（8番目のtd）
                if len(tds) >= 8:
                    entry.update(self._extract_equipment_stats(tds[7], equipment_type="boat"))

                entries.append(entry)

        except Exception as e:
            print(f"出走表パースエラー: {e}")
            import traceback
            traceback.print_exc()

        return entries

    def _get_text_with_separator(self, node, separator):
        """
        ノードの全テキストを取得（子要素含む）

        Args:
            node: HTMLノード
            separator: セパレータ文字

        Returns:
            結合したテキスト
        """
        if not node:
            return ""

        # selectolaxの場合、text(deep=True)で全テキストを取得
        # 改行を区切り文字に置換
        full_text = node.text(deep=True)
        if not full_text:
            return ""

        # 改行をセパレータに置換
        lines = [line.strip() for line in full_text.split('\n') if line.strip()]
        return separator.join(lines)

    # ナイター専用会場コード（2桁）
    NIGHTER_VENUES = {'01', '02', '06', '07', '12', '17', '20', '21', '24'}

    def _extract_race_grade(self, tree):
        """
        レースグレードを抽出

        Args:
            tree: HTMLParserオブジェクト (selectolax)

        Returns:
            レースグレード文字列 or None
            例: 'SG', 'G1', 'G2', 'G3', '一般', 'ルーキーシリーズ'
        """
        try:
            # Step 1: CSSクラスベースの検出（最優先・確実）
            # 公式サイトは is-SG / is-G1 / is-G2 / is-G3 クラスを使用
            for css_class, grade in [
                ('.is-SG', 'SG'), ('.is-G1', 'G1'), ('.is-G2', 'G2'), ('.is-G3', 'G3'),
            ]:
                if tree.css_first(css_class):
                    return grade

            # Step 2: テキストベースの検出（複数セレクタ）
            # h1, h2, h3, title, .heading1_title 等を対象にテキスト全体を結合して検索
            candidate_selectors = ['h1', 'h2', 'h3', '.heading1_title', '.titleTop', '.is-title1']
            combined_text = ''
            for sel in candidate_selectors:
                elem = tree.css_first(sel)
                if elem:
                    combined_text += elem.text(strip=True)

            # 半角・全角両方対応（優先度順）
            if not combined_text and tree.body:
                # 上記で取れない場合はbody全体から短い範囲で取得
                combined_text = tree.body.text(deep=True)[:500]

            grade_patterns = [
                # SG
                (['SG', 'ＳＧ', 'スペシャルグレード'], 'SG'),
                # G1（全角・旧表記含む）
                (['G1', 'Ｇ１', 'ＧⅠ', 'プレミアムＧⅠ', 'グレードワン'], 'G1'),
                # G2
                (['G2', 'Ｇ２', 'ＧⅡ'], 'G2'),
                # G3
                (['G3', 'Ｇ３', 'ＧⅢ'], 'G3'),
                # ルーキー
                (['ルーキーシリーズ'], 'ルーキーシリーズ'),
            ]
            for patterns, grade in grade_patterns:
                if any(p in combined_text for p in patterns):
                    return grade

            return '一般'  # デフォルト

        except Exception as e:
            print(f"グレード抽出エラー: {e}")
            return '一般'

    def _extract_is_ladies(self, tree) -> int:
        """女子戦かを判定（レース一覧ページのタイトルから）"""
        try:
            combined_text = ''
            for sel in ['h1', 'h2', 'h3', '.heading1_title', '.heading2_titleName']:
                elem = tree.css_first(sel)
                if elem:
                    combined_text += elem.text(strip=True)
            if not combined_text and tree.body:
                combined_text = tree.body.text(deep=True)[:500]
            ladies_patterns = ['女子', 'レディース', 'LADIES', 'オールレディース', 'ヴィーナスシリーズ']
            return 1 if any(p in combined_text for p in ladies_patterns) else 0
        except Exception:
            return 0

    def _extract_is_rookie(self, tree) -> int:
        """新人戦かを判定"""
        try:
            combined_text = ''
            for sel in ['h1', 'h2', 'h3', '.heading1_title', '.heading2_titleName']:
                elem = tree.css_first(sel)
                if elem:
                    combined_text += elem.text(strip=True)
            if not combined_text and tree.body:
                combined_text = tree.body.text(deep=True)[:500]
            rookie_patterns = ['新人', 'ルーキー', 'フレッシュ', 'ジュニア']
            return 1 if any(p in combined_text for p in rookie_patterns) else 0
        except Exception:
            return 0

    def _extract_race_distance(self, tree):
        """
        レース距離を抽出

        Args:
            tree: HTMLParserオブジェクト (selectolax)

        Returns:
            レース距離（整数・メートル） or None
            例: 1800
        """
        try:
            # 「予選 1800m」のようなテキストを探す
            all_text = tree.body.text(deep=True) if tree.body else ""

            import re
            # 「1800m」のようなパターンを探す
            match = re.search(r'(\d{4})m', all_text)
            if match:
                distance = int(match.group(1))
                return distance

            return None

        except Exception as e:
            print(f"距離抽出エラー: {e}")
            return None
