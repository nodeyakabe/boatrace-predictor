"""
レース結果スクレイピング
確定した着順とオッズを取得
"""

from .base_scraper import BaseScraper
from config.settings import BOATRACE_OFFICIAL_URL


class ResultScraper(BaseScraper):
    """レース結果スクレイパー"""

    def __init__(self, read_timeout=25):
        super().__init__(read_timeout=read_timeout)

    def fetch_result(self, venue_code, race_date, race_number):
        """
        fetch_historical_data.pyとの互換性のためのエイリアス
        get_race_result_completeを呼び出す
        """
        return self.get_race_result_complete(venue_code, race_date, race_number)

    def get_race_result(self, venue_code, race_date, race_number):
        """
        指定レースの結果を取得

        Args:
            venue_code: 競艇場コード
            race_date: レース日付（YYYYMMDD形式）
            race_number: レース番号（1-12）

        Returns:
            結果データの辞書 or None
        """
        url = f"{BOATRACE_OFFICIAL_URL}/raceresult"
        params = {
            "rno": race_number,
            "jcd": venue_code,
            "hd": race_date
        }

        soup = self.fetch_page(url, params)
        if not soup:
            return None

        # ページタイトルでレース存在確認
        title = soup.find('title')
        if title and 'エラー' in title.text:
            print(f"レース不存在: {venue_code} {race_date} {race_number}R")
            return None

        result_data = {
            "venue_code": venue_code,
            "race_date": race_date,
            "race_number": race_number,
            "results": [],  # [{'pit_number': 1, 'rank': 3}, ...]
            "trifecta_odds": None,
            "is_invalid": False,  # 返還・不成立フラグ
            "weather_data": None,  # 天気情報
            "winning_technique": None,  # 決まり手（1=逃げ, 2=差し, 3=まくり, 4=まくり差し, 5=抜き, 6=恵まれ）
            "race_status": "unknown"  # レース状態（completed, cancelled, flying, accident, returned）
        }

        # レースステータスを検出
        race_status = self._detect_race_status(soup)
        if race_status:
            result_data["race_status"] = race_status

        # 天気情報を取得
        weather_data = self._extract_weather_data(soup)
        if weather_data:
            result_data["weather_data"] = weather_data

        # 着順情報を解析（全6艇分）
        try:
            # 方法1: 結果テーブルから全艇の着順を取得
            # 新構造: 各tbodyに1行ずつ、着順と艇番が含まれる
            result_table = soup.find('table', class_=lambda x: x and 'is-w495' in str(x))
            if result_table:
                # 複数のtbodyを取得（各艇ごとに1つのtbody）
                tbodies = result_table.find_all('tbody')

                for tbody in tbodies:
                    row = tbody.find('tr')
                    if not row:
                        continue

                    tds = row.find_all('td')
                    if len(tds) < 2:
                        continue

                    # 1番目のtd: 着順（"１", "２", "３" などの日本語数字）
                    rank_td = tds[0]
                    rank = self._parse_japanese_rank(rank_td.text.strip())

                    # 2番目のtd: 艇番（class="is-boatColor{N}"）
                    pit_td = tds[1]
                    pit_number = self._extract_pit_number(pit_td)

                    if pit_number and rank:
                        result_data["results"].append({
                            'pit_number': pit_number,
                            'rank': rank
                        })

            # 方法2: フォールバック - 古い構造の場合
            if len(result_data["results"]) == 0:
                # 全ての行から艇番と着順を探す
                all_rows = soup.find_all('tr')
                for row in all_rows:
                    pit_number = None
                    rank = None

                    # 艇番を探す
                    pit_td = row.find('td', class_=lambda x: x and 'boatColor' in str(x))
                    if pit_td:
                        pit_number = self._extract_pit_number(pit_td)

                    # 着順を探す
                    for td in row.find_all('td'):
                        text = td.text.strip()

                        # パターン1: 日本語数字（"１", "２"）
                        rank = self._parse_japanese_rank(text)
                        if rank:
                            break

                        # パターン2: "1着"形式
                        if '着' in text:
                            import re
                            match = re.search(r'([1-6])着', text)
                            if match:
                                rank = int(match.group(1))
                                break

                    if pit_number and rank:
                        # 重複チェック
                        if not any(r['pit_number'] == pit_number for r in result_data["results"]):
                            result_data["results"].append({
                                'pit_number': pit_number,
                                'rank': rank
                            })

                    # 6艇見つかったら終了
                    if len(result_data["results"]) >= 6:
                        break

            # 三連単オッズ（払戻金）を探す
            # 方法1: 払戻金テーブルから「3連単」行を探す
            for table in soup.find_all('table'):
                table_text = table.get_text()
                if '3連単' in table_text and '払戻金' in table_text:
                    # 3連単の行を探す
                    for tr in table.find_all('tr'):
                        row_text = tr.get_text()
                        if '3連単' in row_text:
                            # 払戻金のspan要素を探す（class="is-payout1"など）
                            payout_span = tr.find('span', class_=lambda x: x and 'payout' in str(x).lower())
                            if payout_span:
                                odds_value = self._parse_odds(payout_span.get_text())
                                if odds_value and odds_value >= 100:  # 払戻金は100円以上
                                    # 払戻金を100円単位のオッズに変換（払戻金/100）
                                    result_data["trifecta_odds"] = odds_value / 100.0
                                    break
                            # spanがない場合はtdから探す
                            if not result_data["trifecta_odds"]:
                                for td in tr.find_all('td'):
                                    td_text = td.get_text(strip=True)
                                    odds_value = self._parse_odds(td_text)
                                    if odds_value and odds_value >= 100:
                                        result_data["trifecta_odds"] = odds_value / 100.0
                                        break
                    if result_data["trifecta_odds"]:
                        break

            # 方法2: 'is-payout'クラスのspan要素から探す（フォールバック）
            if not result_data["trifecta_odds"]:
                payout_spans = soup.find_all('span', class_=lambda x: x and 'payout' in str(x).lower())
                for span in payout_spans:
                    parent = span.find_parent('tr')
                    if parent and '3連単' in parent.get_text():
                        odds_value = self._parse_odds(span.get_text())
                        if odds_value and odds_value >= 100:
                            result_data["trifecta_odds"] = odds_value / 100.0
                            break

            # 返還・不成立の判定（テーブルヘッダーを除外）
            # レース自体が返還の場合、結果テーブルがないか、特定のメッセージが表示される
            invalid_indicators = soup.find_all(string=lambda x: x and ('返還レース' in str(x) or '不成立' in str(x) or 'レース不成立' in str(x)))
            if invalid_indicators:
                result_data["is_invalid"] = True

            # 決まり手を取得（soupを再利用）
            if not result_data["is_invalid"] and len(result_data["results"]) > 0:
                text_content = soup.get_text()

                # 空白・改行を除去して正規化
                import re
                normalized_text = re.sub(r'\s+', '', text_content)

                technique_map = {
                    '逃げ': 1,
                    '差し': 2,
                    'まくり差し': 4,  # 先にチェック（「まくり」より優先）
                    'まくり': 3,
                    '抜き': 5,
                    '恵まれ': 6
                }

                for technique_name, technique_code in technique_map.items():
                    # 正規化されたテキストで「決まり手」+「技名」を検索
                    if f'決まり手{technique_name}' in normalized_text or f'決まり手：{technique_name}' in normalized_text:
                        result_data["winning_technique"] = technique_code
                        break

            # 結果数の検証
            num_results = len(result_data["results"])
            if num_results == 6:
                # 完全なデータ
                sorted_results = sorted(result_data["results"], key=lambda x: x['rank'])
                first = next((r['pit_number'] for r in sorted_results if r['rank'] == 1), None)
                second = next((r['pit_number'] for r in sorted_results if r['rank'] == 2), None)
                third = next((r['pit_number'] for r in sorted_results if r['rank'] == 3), None)

                print(f"結果取得: {venue_code} {race_date} {race_number}R - "
                      f"{first}-{second}-{third}")
            elif num_results >= 3:
                # 部分的なデータ（警告を出力）
                print(f"警告: 結果が不完全: {venue_code} {race_date} {race_number}R (取得艇数: {num_results}/6)")
                result_data["is_incomplete"] = True
                sorted_results = sorted(result_data["results"], key=lambda x: x['rank'])
                first = next((r['pit_number'] for r in sorted_results if r['rank'] == 1), None)
                second = next((r['pit_number'] for r in sorted_results if r['rank'] == 2), None)
                third = next((r['pit_number'] for r in sorted_results if r['rank'] == 3), None)
                print(f"部分的な結果: {first}-{second}-{third}...")
            else:
                # データが不十分
                print(f"エラー: 結果解析失敗: {venue_code} {race_date} {race_number}R (取得艇数: {num_results})")
                result_data["is_invalid"] = True

        except Exception as e:
            print(f"結果解析エラー: {e}")
            import traceback
            traceback.print_exc()

        return result_data

    def get_actual_courses(self, venue_code, race_date, race_number):
        """
        実際の進入コースを取得（スタート情報から）

        Args:
            venue_code: 競艇場コード
            race_date: レース日付（YYYYMMDD形式）
            race_number: レース番号（1-12）

        Returns:
            dict: {pit_number: actual_course}
            例: {1: 1, 2: 2, 3: 3, 4: 4, 5: 6, 6: 5}
                → 5号艇が6コース、6号艇が5コースに進入
        """
        url = f"{BOATRACE_OFFICIAL_URL}/raceresult"
        params = {
            "rno": race_number,
            "jcd": venue_code,
            "hd": race_date
        }

        soup = self.fetch_page(url, params)
        if not soup:
            return None

        actual_courses = {}

        try:
            # スタート情報テーブルを探す
            tables = soup.find_all('table')

            for table in tables:
                table_text = table.get_text()

                # 「スタート情報」を含むテーブルを探す
                if 'スタート情報' in table_text:
                    tbody = table.find('tbody')

                    if tbody:
                        # 各行が1つのコースを表す
                        rows = tbody.find_all('tr', recursive=False)

                        if len(rows) == 6:
                            # 行番号 = コース番号
                            for course, row in enumerate(rows, start=1):
                                # 行内のtable1_boatImage1Number要素から枠番を取得
                                number_elem = row.find(class_='table1_boatImage1Number')

                                if number_elem:
                                    # テキストから枠番を取得（"1", "2", ...）
                                    pit_text = number_elem.get_text(strip=True)
                                    try:
                                        pit_number = int(pit_text)
                                        if 1 <= pit_number <= 6:
                                            actual_courses[pit_number] = course
                                    except ValueError:
                                        pass

                            # 6艇分取得できたら終了
                            if len(actual_courses) == 6:
                                break

        except Exception as e:
            print(f"実際の進入コース抽出エラー: {e}")
            import traceback
            traceback.print_exc()
            return None

        if len(actual_courses) == 6:
            print(f"進入コース取得: {venue_code} {race_date} {race_number}R - {actual_courses}")
            return actual_courses
        else:
            print(f"進入コース取得失敗: {venue_code} {race_date} {race_number}R (取得数: {len(actual_courses)})")
            return None

    def get_st_times(self, venue_code, race_date, race_number):
        """
        スタート展示タイムを取得

        Args:
            venue_code: 競艇場コード
            race_date: レース日付（YYYYMMDD形式）
            race_number: レース番号（1-12）

        Returns:
            dict: {枠番: STタイム(秒)} or None
        """
        url = f"{BOATRACE_OFFICIAL_URL}/raceresult"
        params = {
            "rno": race_number,
            "jcd": venue_code,
            "hd": race_date
        }

        soup = self.fetch_page(url, params)
        if not soup:
            return None

        st_times = {}

        try:
            # table1_boatImage1TimeInner クラスを持つ全要素を取得
            # （これはSTタイム表示用のクラス）
            time_elements = soup.find_all(class_='table1_boatImage1TimeInner')

            for time_elem in time_elements:
                time_text = time_elem.get_text(strip=True)

                # この要素の親行（tr）を取得
                parent_tr = time_elem.find_parent('tr')
                if not parent_tr:
                    continue

                # 同じ行内の枠番を探す
                number_elem = parent_tr.find(class_='table1_boatImage1Number')
                if not number_elem:
                    continue

                pit_text = number_elem.get_text(strip=True)
                try:
                    pit_number = int(pit_text)
                except ValueError:
                    continue

                # STタイムをパース
                # ".17" のような形式（先頭に0が省略されている）
                if time_text.startswith('.'):
                    time_text = '0' + time_text

                try:
                    st_time = float(time_text)
                    st_times[pit_number] = st_time
                except ValueError:
                    pass

        except Exception as e:
            print(f"STタイム抽出エラー: {e}")
            import traceback
            traceback.print_exc()
            return None

        if len(st_times) == 6:
            print(f"STタイム取得: {venue_code} {race_date} {race_number}R - {st_times}")
            return st_times
        else:
            print(f"STタイム取得失敗: {venue_code} {race_date} {race_number}R (取得数: {len(st_times)})")
            return None

    def _parse_japanese_rank(self, text):
        """
        日本語数字の着順をアラビア数字に変換

        Args:
            text: "１", "２", "３" などの文字列

        Returns:
            着順（整数） or None
        """
        # 全角数字 → 半角数字の変換マップ
        japanese_to_arabic = {
            '１': 1, '２': 2, '３': 3, '４': 4, '５': 5, '６': 6,
            '1': 1, '2': 2, '3': 3, '4': 4, '5': 5, '6': 6
        }

        text = text.strip()
        if text in japanese_to_arabic:
            return japanese_to_arabic[text]

        return None

    def _extract_pit_number(self, element):
        """
        要素から艇番を抽出

        Args:
            element: BeautifulSoup要素

        Returns:
            艇番（整数） or None
        """
        try:
            # classから艇番を抽出（例: is-boatColor1 → 1）
            class_list = element.get('class', [])
            for cls in class_list:
                if 'boatColor' in cls:
                    # is-boatColor1, is-boatColor2 などから数字を抽出
                    for char in cls:
                        if char.isdigit():
                            return int(char)

            # テキストから数字を抽出
            text = element.text.strip()

            # パターン1: "1" "2" などの単一数字
            if len(text) == 1 and text.isdigit():
                num = int(text)
                if 1 <= num <= 6:
                    return num

            # パターン2: "1号艇" "2コース" などの形式
            import re
            match = re.search(r'([1-6])', text)
            if match:
                return int(match.group(1))

        except (ValueError, AttributeError, IndexError):
            pass
        return None

    def _parse_odds(self, odds_text):
        """
        オッズテキストを数値に変換

        Args:
            odds_text: オッズの文字列（例: "12.3円", "¥1,800"）

        Returns:
            オッズ（浮動小数点数） or None
        """
        try:
            import re
            # 数字とカンマ、ピリオドのみ抽出
            # "12.3円" → 12.3, "¥1,800" → 1800
            cleaned = re.sub(r'[^\d.,]', '', odds_text)
            cleaned = cleaned.replace(',', '')
            if cleaned:
                return float(cleaned)
            return None
        except (ValueError, AttributeError):
            return None

    def get_winning_technique(self, venue_code, race_date, race_number):
        """
        1着艇の決まり手を取得

        Args:
            venue_code: 競艇場コード
            race_date: レース日付（YYYYMMDD形式）
            race_number: レース番号（1-12）

        Returns:
            決まり手コード（整数） or None
            1=逃げ, 2=差し, 3=まくり, 4=まくり差し, 5=抜き, 6=恵まれ
        """
        url = f"{BOATRACE_OFFICIAL_URL}/raceresult"
        params = {
            "rno": race_number,
            "jcd": venue_code,
            "hd": race_date
        }

        soup = self.fetch_page(url, params)
        if not soup:
            return None

        try:
            # 方法1: 備考欄から「決まり手：まくり」のような記述を探す
            text_content = soup.get_text()

            # 決まり手のマッピング
            technique_map = {
                '逃げ': 1,
                '差し': 2,
                'まくり差し': 4,  # 「まくり差し」を先にチェック（「まくり」の前）
                'まくり': 3,
                '抜き': 5,
                '恵まれ': 6
            }

            for technique_name, technique_code in technique_map.items():
                if f'決まり手：{technique_name}' in text_content or f'決まり手{technique_name}' in text_content:
                    return technique_code

            # 方法2: 備考欄なしで決まり手キーワードを直接探す
            # スタート情報テーブル内を優先的に探す
            for technique_name, technique_code in technique_map.items():
                # 文字列検索（全体から）
                found = soup.find_all(string=lambda x: x and technique_name in str(x))
                if found:
                    # 決まり手として妥当な場所にあるか確認
                    # （「まくり」が選手名やコメントに含まれる可能性を排除）
                    for elem in found:
                        parent_text = elem.parent.get_text(strip=True) if elem.parent else ''
                        # 短いテキストで決まり手単独で出現する場合のみ採用
                        if len(parent_text) < 20 and technique_name == parent_text:
                            return technique_code

            return None

        except Exception as e:
            print(f"決まり手抽出エラー: {e}")
            import traceback
            traceback.print_exc()
            return None

    def check_race_exists(self, venue_code, race_date):
        """
        指定日にレースが存在するか確認

        Args:
            venue_code: 競艇場コード
            race_date: レース日付（YYYYMMDD形式）

        Returns:
            存在する場合True
        """
        # resultlistエンドポイントを使用
        url = f"{BOATRACE_OFFICIAL_URL}/resultlist"
        params = {
            "jcd": venue_code,
            "hd": race_date
        }

        soup = self.fetch_page(url, params)
        if not soup:
            return False

        # データがありませんメッセージをチェック
        no_data = soup.find_all(string=lambda x: x and 'データがありません' in str(x))
        if no_data:
            return False

        # テーブルが存在するか確認
        tables = soup.find_all('table')
        return len(tables) > 0

    def get_all_race_results_by_date(self, venue_code, race_date):
        """
        指定日の全レース結果を一括取得（resultlistエンドポイント使用）

        効率重視: 1リクエストで12レース分取得
        - 通常レース: 1-2-3着のみ取得
        - 返還/不成立/中止: is_invalid=True, results=[]

        注意: 全6艇の詳細（フライング、欠場、転覆等）が必要な場合は
              get_race_result()で個別に取得すること

        Args:
            venue_code: 競艇場コード
            race_date: レース日付（YYYYMMDD形式）

        Returns:
            レース結果のリスト [result_data1, result_data2, ...]
            取得失敗時は空リスト
        """
        url = f"{BOATRACE_OFFICIAL_URL}/resultlist"
        params = {
            "jcd": venue_code,
            "hd": race_date
        }

        soup = self.fetch_page(url, params)
        if not soup:
            return []

        # データがありませんメッセージをチェック（未開催）
        no_data = soup.find_all(string=lambda x: x and 'データがありません' in str(x))
        if no_data:
            return []

        results = []

        # 全てのテーブルを取得
        tables = soup.find_all('table')
        if not tables:
            return []

        # 最初のテーブルに全レース結果が含まれている
        # 各レースは1つのtbodyとして格納
        main_table = tables[0]
        tbodies = main_table.find_all('tbody')

        for tbody in tbodies:
            try:
                tr = tbody.find('tr')
                if not tr:
                    continue

                tds = tr.find_all('td')
                if len(tds) < 2:
                    continue

                # レース番号を抽出 ("1R" -> 1)
                race_link = tds[0].find('a')
                if not race_link:
                    continue

                race_text = race_link.text.strip()
                race_number = int(race_text.replace('R', ''))

                # 返還・不成立チェック
                is_invalid = False
                tbody_text = tbody.get_text()
                if '返還' in tbody_text or '不成立' in tbody_text or '中止' in tbody_text:
                    is_invalid = True

                # 返還・不成立の場合
                if is_invalid:
                    results.append({
                        "venue_code": venue_code,
                        "race_date": race_date,
                        "race_number": race_number,
                        "results": [],
                        "trifecta_odds": None,
                        "is_invalid": True
                    })
                    continue

                # 3連単結果を抽出 (4-5-6 -> [4, 5, 6])
                numberSet = tds[1].find('div', class_='numberSet1')
                if not numberSet:
                    continue

                numbers = numberSet.find_all('span', class_='numberSet1_number')
                if len(numbers) < 3:
                    continue

                first = int(numbers[0].text.strip())
                second = int(numbers[1].text.strip())
                third = int(numbers[2].text.strip())

                # 3連単オッズを抽出（オプション）
                trifecta_odds = None
                if len(tds) > 2:
                    odds_elem = tds[2].find('span', class_='is-payout1')
                    if odds_elem:
                        odds_text = odds_elem.text.strip()
                        trifecta_odds = self._parse_odds(odds_text)

                # 結果データを構築
                result_data = {
                    "venue_code": venue_code,
                    "race_date": race_date,
                    "race_number": race_number,
                    "results": [
                        {"pit_number": first, "rank": 1},
                        {"pit_number": second, "rank": 2},
                        {"pit_number": third, "rank": 3}
                    ],
                    "trifecta_odds": trifecta_odds,
                    "is_invalid": False
                }

                results.append(result_data)

            except Exception as e:
                print(f"  レース結果パースエラー: {e}")
                continue

        return results

    def _get_race_result_detail(self, venue_code, race_date, race_number, tbody_summary):
        """
        個別レースの詳細結果を取得

        Args:
            venue_code: 競艇場コード
            race_date: レース日付
            race_number: レース番号
            tbody_summary: resultlistのtbody要素（サマリー情報）

        Returns:
            詳細結果データ or None
        """
        # まずサマリーから基本情報を取得
        tr = tbody_summary.find('tr')
        tds = tr.find_all('td')

        # 返還・不成立チェック
        is_invalid = False
        invalid_text = tbody_summary.get_text()
        if '返還' in invalid_text or '不成立' in invalid_text or '中止' in invalid_text:
            is_invalid = True

        # 3連単オッズを抽出
        trifecta_odds = None
        if len(tds) > 2:
            odds_elem = tds[2].find('span', class_='is-payout1')
            if odds_elem:
                odds_text = odds_elem.text.strip()
                trifecta_odds = self._parse_odds(odds_text)

        # 返還・不成立の場合は基本情報のみ返す
        if is_invalid:
            return {
                "venue_code": venue_code,
                "race_date": race_date,
                "race_number": race_number,
                "results": [],
                "trifecta_odds": None,
                "is_invalid": True
            }

        # 詳細ページから全6艇の着順を取得
        url = f"{BOATRACE_OFFICIAL_URL}/raceresult"
        params = {
            "rno": race_number,
            "jcd": venue_code,
            "hd": race_date
        }

        soup = self.fetch_page(url, params)
        if not soup:
            # 詳細取得失敗時はサマリーから1-2-3着のみ取得
            return self._parse_summary_results(
                venue_code, race_date, race_number, tbody_summary, trifecta_odds
            )

        # 全6艇の結果を解析
        result_data = {
            "venue_code": venue_code,
            "race_date": race_date,
            "race_number": race_number,
            "results": [],
            "trifecta_odds": trifecta_odds,
            "is_invalid": False
        }

        # 結果テーブルから全艇の着順を取得
        result_table = soup.find('table', class_=lambda x: x and 'is-w495' in str(x))
        if result_table:
            tbodies = result_table.find_all('tbody')

            for tbody in tbodies:
                row = tbody.find('tr')
                if not row:
                    continue

                row_tds = row.find_all('td')
                if len(row_tds) < 2:
                    continue

                # 着順を取得（数字または特殊記号）
                rank_td = row_tds[0]
                rank_text = rank_td.text.strip()
                rank = self._parse_rank_with_irregulars(rank_text)

                # 艇番を取得
                pit_td = row_tds[1]
                pit_number = self._extract_pit_number(pit_td)

                if pit_number and rank:
                    result_data["results"].append({
                        'pit_number': pit_number,
                        'rank': rank
                    })

        # 最低3艇の結果がない場合はサマリーにフォールバック
        if len(result_data["results"]) < 3:
            return self._parse_summary_results(
                venue_code, race_date, race_number, tbody_summary, trifecta_odds
            )

        return result_data

    def _parse_summary_results(self, venue_code, race_date, race_number, tbody, trifecta_odds):
        """
        resultlistのサマリーから1-2-3着のみ取得（フォールバック用）

        Args:
            venue_code: 競艇場コード
            race_date: レース日付
            race_number: レース番号
            tbody: tbodyエレメント
            trifecta_odds: 3連単オッズ

        Returns:
            結果データ
        """
        tr = tbody.find('tr')
        tds = tr.find_all('td')

        # 3連単結果を抽出
        numberSet = tds[1].find('div', class_='numberSet1')
        if not numberSet:
            return None

        numbers = numberSet.find_all('span', class_='numberSet1_number')
        if len(numbers) < 3:
            return None

        first = int(numbers[0].text.strip())
        second = int(numbers[1].text.strip())
        third = int(numbers[2].text.strip())

        return {
            "venue_code": venue_code,
            "race_date": race_date,
            "race_number": race_number,
            "results": [
                {"pit_number": first, "rank": 1},
                {"pit_number": second, "rank": 2},
                {"pit_number": third, "rank": 3}
            ],
            "trifecta_odds": trifecta_odds,
            "is_invalid": False
        }

    def _parse_rank_with_irregulars(self, rank_text):
        """
        着順テキストを解析（イレギュラー対応）

        Args:
            rank_text: 着順テキスト（"１"、"F"、"L"、"K"、"S"など）

        Returns:
            着順（整数またはアルファベット文字列） or None
        """
        rank_text = rank_text.strip()

        # 通常の着順（1-6）
        normal_rank = self._parse_japanese_rank(rank_text)
        if normal_rank:
            return normal_rank

        # イレギュラーケース
        irregular_map = {
            'F': 'F',   # フライング
            'L': 'L',   # 欠場（Late scratch）
            'K': 'K',   # 転覆（Kapsize）
            'S': 'S',   # 失格（Sikkaku）
            '妨': 'S',  # 妨害失格
            '不': 'S',  # 不良航法
            '欠': 'L',  # 欠場
            '落': 'K',  # 落水/転覆
        }

        # 大文字変換してチェック
        rank_upper = rank_text.upper()
        if rank_upper in irregular_map:
            return irregular_map[rank_upper]

        # 日本語の場合
        for key, value in irregular_map.items():
            if key in rank_text:
                return value

        return None

    def _extract_weather_data(self, soup):
        """
        レース結果ページから天気情報を抽出

        Args:
            soup: BeautifulSoupオブジェクト

        Returns:
            天気データの辞書 or None
        """
        try:
            # weather1クラスの要素を探す
            weather_elem = soup.find(class_='weather1')
            if not weather_elem:
                return None

            weather_data = {}

            # weather1_bodyUnit要素を探す（気温、風、水温、波高）
            units = weather_elem.find_all(class_='weather1_bodyUnit')

            for unit in units:
                # タイトルとデータを取得
                label_elem = unit.find(class_='weather1_bodyUnitLabelTitle')
                data_elem = unit.find(class_='weather1_bodyUnitLabelData')

                if not label_elem or not data_elem:
                    continue

                label = label_elem.get_text(strip=True)
                data = data_elem.get_text(strip=True)

                # ラベルに応じてデータを格納
                if '気温' in label:
                    # "17.0度" -> 17.0
                    weather_data['temperature'] = self._parse_float(data)
                elif '風' in label:
                    # "5m" -> 5.0
                    weather_data['wind_speed'] = self._parse_float(data)
                elif '水温' in label:
                    # "20.0度" -> 20.0
                    weather_data['water_temperature'] = self._parse_float(data)
                elif '波高' in label:
                    # "5cm" -> 5.0
                    weather_data['wave_height'] = self._parse_float(data)

            # 天気（晴/曇/雨）を取得
            weather_image = weather_elem.find(class_='is-weather')
            if weather_image:
                # is-weather1, is-weather2, is-weather3 などのクラスから判定
                classes = weather_image.get('class', [])
                for cls in classes:
                    if 'is-weather' in cls and len(cls) > 10:
                        # is-weather1 -> 晴れ, is-weather2 -> 曇り, is-weather3 -> 雨（推測）
                        weather_num = cls.replace('is-weather', '')
                        weather_map = {
                            '1': '晴れ',
                            '2': '曇り',
                            '3': '雨'
                        }
                        weather_data['weather_condition'] = weather_map.get(weather_num, '不明')
                        break

            # 風向を取得
            wind_direction_elem = weather_elem.find(class_='is-windDirection')
            if wind_direction_elem:
                # 子要素の<p>タグを探す
                wind_image = wind_direction_elem.find('p')
                if wind_image:
                    classes = wind_image.get('class', [])
                    for cls in classes:
                        if cls.startswith('is-wind') and len(cls) > 7:
                            # is-wind13 -> 風向13番（16方位）
                            wind_num = cls.replace('is-wind', '')
                            try:
                                wind_deg = int(wind_num) * 22.5  # 16方位を度数に変換
                                weather_data['wind_direction'] = self._degree_to_direction(wind_deg)
                            except (ValueError, KeyError):
                                pass
                            break

            return weather_data if weather_data else None

        except Exception as e:
            print(f"天気情報抽出エラー: {e}")
            return None

    def _parse_float(self, text):
        """
        テキストから数値を抽出

        Args:
            text: "17.0度" や "5m" などの文字列

        Returns:
            浮動小数点数 or None
        """
        import re
        match = re.search(r'(\d+\.?\d*)', text)
        if match:
            try:
                return float(match.group(1))
            except (ValueError, AttributeError):
                return None
        return None

    def _degree_to_direction(self, degree):
        """
        角度を16方位に変換

        Args:
            degree: 角度（0-360）

        Returns:
            方位の文字列
        """
        directions = [
            "北", "北北東", "北東", "東北東",
            "東", "東南東", "南東", "南南東",
            "南", "南南西", "南西", "西南西",
            "西", "西北西", "北西", "北北西"
        ]
        index = int((degree + 11.25) / 22.5) % 16
        return directions[index]

    def get_payouts_and_kimarite(self, venue_code, race_date, race_number):
        """
        払戻金と決まり手を取得

        Args:
            venue_code: 競艇場コード
            race_date: レース日付（YYYYMMDD形式）
            race_number: レース番号（1-12）

        Returns:
            dict: {
                'payouts': {舟券種別: [払戻金データ]},
                'kimarite': '決まり手'
            } or None
        """
        url = f"{BOATRACE_OFFICIAL_URL}/raceresult"
        params = {
            "rno": race_number,
            "jcd": venue_code,
            "hd": race_date
        }

        soup = self.fetch_page(url, params)
        if not soup:
            return None

        result = {
            'payouts': {},
            'kimarite': None
        }

        try:
            tables = soup.find_all('table')

            for table in tables:
                thead = table.find('thead')
                if not thead:
                    continue

                headers = [th.get_text(strip=True) for th in thead.find_all('th')]

                # 払戻金テーブル
                if '勝式' in headers and '払戻金' in headers:
                    tbodies = table.find_all('tbody')

                    for tbody in tbodies:
                        rows = tbody.find_all('tr')
                        if not rows:
                            continue

                        first_row = rows[0]
                        tds = first_row.find_all('td')

                        if len(tds) < 2:
                            continue

                        # 舟券種別取得
                        bet_type = None
                        for td in tds:
                            if td.get('rowspan'):
                                bet_type = td.get_text(strip=True)
                                break

                        if not bet_type:
                            continue

                        bet_type_map = {
                            '3連単': 'trifecta',
                            '3連複': 'trio',
                            '2連単': 'exacta',
                            '2連複': 'quinella',
                            '拡連複': 'quinella_place',
                            '単勝': 'win',
                            '複勝': 'place'
                        }

                        bet_key = bet_type_map.get(bet_type)
                        if not bet_key:
                            continue

                        payouts_list = []

                        for row in rows:
                            tds = row.find_all('td')

                            combination = None
                            number_div = row.find(class_='numberSet1')
                            if number_div:
                                combination = number_div.get_text(strip=True)

                            payout_elem = row.find(class_='is-payout1')
                            if not payout_elem:
                                continue

                            payout_text = payout_elem.get_text(strip=True)

                            if not payout_text or payout_text == ' ' or len(payout_text) == 0:
                                continue

                            payout_text = payout_text.replace('¥', '').replace('円', '').replace(',', '').strip()

                            try:
                                amount = int(payout_text)
                            except ValueError:
                                continue

                            popularity = None
                            if len(tds) >= 4:
                                popularity_text = tds[-1].get_text(strip=True)
                                try:
                                    popularity = int(popularity_text)
                                except:
                                    pass

                            if bet_key in ['win', 'place']:
                                pit_number = None
                                if combination:
                                    try:
                                        pit_number = int(combination)
                                    except:
                                        pass

                                if pit_number:
                                    payouts_list.append({
                                        'pit_number': pit_number,
                                        'amount': amount,
                                        'popularity': popularity
                                    })
                            else:
                                if combination:
                                    payouts_list.append({
                                        'combination': combination,
                                        'amount': amount,
                                        'popularity': popularity
                                    })

                        if payouts_list:
                            result['payouts'][bet_key] = payouts_list

                # 決まり手テーブル
                if '決まり手' in headers:
                    tbody = table.find('tbody')
                    if tbody:
                        td = tbody.find('td')
                        if td:
                            kimarite = td.get_text(strip=True)
                            if kimarite and kimarite not in ['', ' ']:
                                result['kimarite'] = kimarite
                    break

        except Exception as e:
            print(f"払戻金・決まり手抽出エラー: {e}")
            import traceback
            traceback.print_exc()
            return None

        return result

    def get_race_result_complete(self, venue_code, race_date, race_number):
        """
        レース結果ページを1回だけ取得し、全データを抽出（最適化版）

        このメソッドは重複リクエストを防ぐため、1回のHTTPリクエストで以下を取得:
        - レース結果（着順）
        - 実際の進入コース
        - STタイム
        - 払戻金
        - 決まり手
        - 天気情報

        Args:
            venue_code: 競艇場コード
            race_date: レース日付（YYYYMMDD形式）
            race_number: レース番号（1-12）

        Returns:
            dict: {
                'results': [着順データ],
                'trifecta_odds': 三連単オッズ,
                'is_invalid': 返還フラグ,
                'weather_data': 天気情報,
                'actual_courses': {枠番: コース番号},
                'st_times': {枠番: STタイム},
                'payouts': {舟券種別: [払戻金データ]},
                'kimarite': '決まり手'
            } or None
        """
        url = f"{BOATRACE_OFFICIAL_URL}/raceresult"
        params = {
            "rno": race_number,
            "jcd": venue_code,
            "hd": race_date
        }

        soup = self.fetch_page(url, params)
        if not soup:
            return None

        # ページタイトルでレース存在確認
        title = soup.find('title')
        if title and 'エラー' in title.text:
            print(f"レース不存在: {venue_code} {race_date} {race_number}R")
            return None

        result = {
            "venue_code": venue_code,
            "race_date": race_date,
            "race_number": race_number,
            "results": [],
            "trifecta_odds": None,
            "is_invalid": False,
            "weather_data": None,
            "actual_courses": {},
            "st_times": {},
            "payouts": {},
            "kimarite": None
        }

        try:
            # 1. 天気情報を取得
            weather_data = self._extract_weather_data(soup)
            if weather_data:
                result["weather_data"] = weather_data

            # 2. 着順情報を解析
            result_table = soup.find('table', class_=lambda x: x and 'is-w495' in str(x))
            if result_table:
                tbodies = result_table.find_all('tbody')

                for tbody in tbodies:
                    row = tbody.find('tr')
                    if not row:
                        continue

                    tds = row.find_all('td')
                    if len(tds) < 2:
                        continue

                    # 着順
                    rank_td = tds[0]
                    rank = self._parse_japanese_rank(rank_td.text.strip())

                    # 艇番
                    pit_td = tds[1]
                    pit_number = self._extract_pit_number(pit_td)

                    if pit_number and rank:
                        result["results"].append({
                            'pit_number': pit_number,
                            'rank': rank
                        })

            # 3. 三連単オッズを取得
            payoff_table = soup.find('table', class_=lambda x: x and 'is-w243' in str(x))
            if payoff_table:
                tbody = payoff_table.find('tbody')
                if tbody:
                    first_row = tbody.find('tr')
                    if first_row:
                        tds = first_row.find_all('td')
                        for td in tds:
                            odds_value = self._parse_odds(td.text)
                            if odds_value:
                                result["trifecta_odds"] = odds_value
                                break

            # 4. 返還・不成立の判定
            invalid_indicators = soup.find_all(string=lambda x: x and ('返還レース' in str(x) or '不成立' in str(x) or 'レース不成立' in str(x)))
            if invalid_indicators:
                result["is_invalid"] = True

            # 5. 実際の進入コースを取得
            tables = soup.find_all('table')
            for table in tables:
                table_text = table.get_text()

                if 'スタート情報' in table_text:
                    tbody = table.find('tbody')

                    if tbody:
                        rows = tbody.find_all('tr', recursive=False)

                        if len(rows) == 6:
                            for course, row in enumerate(rows, start=1):
                                number_elem = row.find(class_='table1_boatImage1Number')

                                if number_elem:
                                    pit_text = number_elem.get_text(strip=True)
                                    try:
                                        pit_number = int(pit_text)
                                        if 1 <= pit_number <= 6:
                                            result["actual_courses"][pit_number] = course
                                    except ValueError:
                                        pass

                            if len(result["actual_courses"]) == 6:
                                break

            # 6. STタイムを取得
            time_elements = soup.find_all(class_='table1_boatImage1TimeInner')

            for time_elem in time_elements:
                time_text = time_elem.get_text(strip=True)

                parent_tr = time_elem.find_parent('tr')
                if not parent_tr:
                    continue

                number_elem = parent_tr.find(class_='table1_boatImage1Number')
                if not number_elem:
                    continue

                pit_text = number_elem.get_text(strip=True)
                try:
                    pit_number = int(pit_text)
                except ValueError:
                    continue

                if time_text.startswith('.'):
                    time_text = '0' + time_text

                try:
                    st_time = float(time_text)
                    result["st_times"][pit_number] = st_time
                except ValueError:
                    pass

            # 7. 払戻金と決まり手を取得
            for table in tables:
                thead = table.find('thead')
                if not thead:
                    continue

                headers = [th.get_text(strip=True) for th in thead.find_all('th')]

                # 払戻金テーブル
                if '勝式' in headers and '払戻金' in headers:
                    tbodies = table.find_all('tbody')

                    for tbody in tbodies:
                        rows = tbody.find_all('tr')
                        if not rows:
                            continue

                        first_row = rows[0]
                        tds = first_row.find_all('td')

                        if len(tds) < 2:
                            continue

                        # 舟券種別取得
                        bet_type = None
                        for td in tds:
                            if td.get('rowspan'):
                                bet_type = td.get_text(strip=True)
                                break

                        if not bet_type:
                            continue

                        bet_type_map = {
                            '3連単': 'trifecta',
                            '3連複': 'trio',
                            '2連単': 'exacta',
                            '2連複': 'quinella',
                            '拡連複': 'quinella_place',
                            '単勝': 'win',
                            '複勝': 'place'
                        }

                        bet_key = bet_type_map.get(bet_type)
                        if not bet_key:
                            continue

                        payouts_list = []

                        for row in rows:
                            tds = row.find_all('td')

                            combination = None
                            number_div = row.find(class_='numberSet1')
                            if number_div:
                                combination = number_div.get_text(strip=True)

                            payout_elem = row.find(class_='is-payout1')
                            if not payout_elem:
                                continue

                            payout_text = payout_elem.get_text(strip=True)

                            if not payout_text or payout_text == ' ' or len(payout_text) == 0:
                                continue

                            payout_text = payout_text.replace('¥', '').replace('円', '').replace(',', '').strip()

                            try:
                                amount = int(payout_text)
                            except ValueError:
                                continue

                            popularity = None
                            if len(tds) >= 4:
                                popularity_text = tds[-1].get_text(strip=True)
                                try:
                                    popularity = int(popularity_text)
                                except:
                                    pass

                            if bet_key in ['win', 'place']:
                                pit_number = None
                                if combination:
                                    try:
                                        pit_number = int(combination)
                                    except:
                                        pass

                                if pit_number:
                                    payouts_list.append({
                                        'pit_number': pit_number,
                                        'amount': amount,
                                        'popularity': popularity
                                    })
                            else:
                                if combination:
                                    payouts_list.append({
                                        'combination': combination,
                                        'amount': amount,
                                        'popularity': popularity
                                    })

                        if payouts_list:
                            result['payouts'][bet_key] = payouts_list

                # 決まり手テーブル
                if '決まり手' in headers:
                    tbody = table.find('tbody')
                    if tbody:
                        td = tbody.find('td')
                        if td:
                            kimarite = td.get_text(strip=True)
                            if kimarite and kimarite not in ['', ' ']:
                                result['kimarite'] = kimarite
                    break

            # デバッグ出力（コメントアウト）
            # if len(result["results"]) >= 3:
            #     sorted_results = sorted(result["results"], key=lambda x: x['rank'])
            #     first = next((r['pit_number'] for r in sorted_results if r['rank'] == 1), None)
            #     second = next((r['pit_number'] for r in sorted_results if r['rank'] == 2), None)
            #     third = next((r['pit_number'] for r in sorted_results if r['rank'] == 3), None)
            #
            #     print(f"完全データ取得: {venue_code} {race_date} {race_number}R - {first}-{second}-{third}")

        except Exception as e:
            print(f"完全データ取得エラー: {e}")
            import traceback
            traceback.print_exc()
            return None

        return result

    def _detect_race_status(self, soup):
        """
        レースのステータスを検出
        
        Returns:
            str: 'completed', 'cancelled', 'flying', 'accident', 'returned', or None
        """
        try:
            # ページ全体のテキストを取得
            page_text = soup.get_text()
            
            # 開催中止のキーワード
            if '中止' in page_text or '不成立' in page_text:
                return 'cancelled'
            
            # フライングのキーワード
            if 'フライング' in page_text or 'F' in page_text:
                return 'flying'
            
            # 事故のキーワード
            if '事故' in page_text:
                return 'accident'
            
            # 返還のキーワード
            if '返還' in page_text or '払戻なし' in page_text:
                return 'returned'
            
            # 結果テーブルが存在すれば完了と判定
            result_table = soup.find('table', class_=lambda x: x and 'is-w495' in str(x))
            if result_table:
                tbody = result_table.find('tbody')
                if tbody and tbody.find('tr'):
                    return 'completed'
            
            return None
            
        except Exception as e:
            print(f"レースステータス検出エラー: {e}")
            return None
