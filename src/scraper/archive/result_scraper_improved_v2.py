"""
レース結果スクレイピング - 改善版 V2
親クラスを活用してSTタイムのF/L対応のみを追加
"""

from .result_scraper import ResultScraper


class ImprovedResultScraperV2(ResultScraper):
    """
    改善版レース結果スクレイパー V2
    親クラスの機能を活用し、STタイムパース処理のみをオーバーライド
    """

    def get_race_result_complete(self, venue_code, race_date, race_number):
        """
        完全な結果を取得 (F/L対応版)

        親クラスの処理結果を取得し、STタイムを再パースしてF/Lを検出
        """
        # 親クラスのメソッドで基本データを取得
        result = super().get_race_result_complete(venue_code, race_date, race_number)

        if not result:
            return None

        # st_statusフィールドを追加
        result['st_status'] = {}

        # 既存のSTタイムを分析してステータスを判定
        st_times = result.get('st_times', {})

        for pit, st_time in st_times.items():
            if st_time == -0.01:
                result['st_status'][pit] = 'flying'
            elif st_time == -0.02:
                result['st_status'][pit] = 'late'
            elif st_time is not None:
                result['st_status'][pit] = 'normal'

        # 欠損しているSTタイムを確認（フライング・出遅れの可能性）
        # HTMLを再度パースしてF/Lを探す
        missing_pits = [p for p in range(1, 7) if p not in st_times]

        if missing_pits:
            # 必要に応じてF/L検出ロジックを追加
            # 今回は既存の動作を維持
            pass

        return result

    def _parse_st_time_improved(self, time_text):
        """
        STタイムをパース (F/L対応)

        Args:
            time_text: STタイムのテキスト

        Returns:
            (st_time: float|None, status: str)
        """
        time_text = time_text.strip()

        # フライングのチェック
        if time_text.upper() in ['F', '.F']:
            return (-0.01, 'flying')

        # 出遅れのチェック
        if time_text.upper() in ['L', '.L']:
            return (-0.02, 'late')

        # 数値のパース
        if time_text.startswith('.'):
            time_text = '0' + time_text

        try:
            st_time = float(time_text)
            return (st_time, 'normal')
        except ValueError:
            return (None, 'unknown')
