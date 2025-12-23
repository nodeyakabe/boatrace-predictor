# 環境要因減点システム 予測段階適用プラン

## 概要

信頼度Bの予測に対して環境要因減点を適用し、調整後の信頼度（B/C/D）をデータベースに保存する。
ダウングレードされた予測は、既存の戦略AのC/D条件で自動的に購入対象になる。

## 実装方針

### 1. 予測保存時に環境要因減点を適用

**対象ファイル**: [src/database/data_manager.py](../src/database/data_manager.py:921)

`save_race_predictions()`メソッドを拡張：
- 信頼度Bの予測に対してのみ環境要因減点を適用
- 調整後の信頼度（B/C/D）をデータベースに保存
- 元の信頼度と減点情報はログに記録（トレーサビリティ確保）

### 2. 環境情報の取得

予測保存時に以下の環境情報を取得：
- 会場コード（races.venue_code）
- レース時刻（races.race_time）
- 風向（race_conditions.wind_direction）
- 風速（race_conditions.wind_speed）
- 波高（race_conditions.wave_height）
- 天候（race_conditions.weather）

### 3. 実装の流れ

```python
def save_race_predictions(self, race_id, predictions, prediction_type='advance'):
    # 1. 環境情報を取得
    env_info = self._get_race_environment(race_id)

    # 2. 環境要因減点システムを初期化
    from analysis.environmental_penalty import EnvironmentalPenaltySystem
    penalty_system = EnvironmentalPenaltySystem()

    # 3. 各予測に対して処理
    for pred in predictions:
        if pred.get('confidence') == 'B':
            # 環境要因減点を適用
            result = penalty_system.should_accept_bet(
                venue_code=env_info['venue_code'],
                race_time=env_info['race_time'],
                wind_direction=env_info['wind_direction'],
                wind_speed=env_info['wind_speed'],
                wave_height=env_info['wave_height'],
                weather=env_info['weather'],
                original_score=pred.get('total_score', 100),
                min_threshold=0  # 閾値チェックはしない（信頼度のみ調整）
            )

            # 調整後の信頼度を適用
            pred['confidence'] = result['adjusted_confidence']
            pred['environmental_penalty'] = result['penalty']

            # ログに記録
            logger.info(f"環境要因減点適用: race_id={race_id}, "
                       f"pit={pred['pit_number']}, "
                       f"元信頼度=B, 調整後={result['adjusted_confidence']}, "
                       f"減点={result['penalty']}pt")

    # 4. 通常通りDB保存
    # （既存の保存ロジック）
```

## メリット

### 1. シンプルな実装
- 既存の予測ロジックを変更不要
- 既存の戦略Aをそのまま使用可能
- データベーススキーマの変更不要

### 2. 自動的な購入対象化
- B→Cにダウングレード → 既存のC条件で購入される
- B→Dにダウングレード → 既存のD条件で購入される
- B維持 → 購入対象外（現状通り）

### 3. トレーサビリティ
- ログに元の信頼度と減点情報を記録
- 後から検証・分析が可能

## 期待効果

### 検証済みデータ（2025年BEFORE予測）

| 元信頼度 | 調整後B | 調整後C | 調整後D |
|---------|---------|---------|---------|
| B (5,537) | 2,830 (51.1%) | 2,472 (44.7%) | 235 (4.2%) |

### 期待される購入戦略

**調整後C（2,472レース）**:
- 既存のC条件で購入: C×B1×150-200倍
- 期待ROI: 369.2%

**調整後D（235レース）**:
- 既存のD条件で購入: 3層すべて
- 期待ROI: 304.6%（戦略A全体）

### 最終的な効果
- 信頼度Bの約49%（C+D）が購入対象に追加される
- 環境要因で不利な条件は除外される（B維持のみ）
- 戦略Aの購入機会が増加

## 実装スケジュール

1. **Phase 1**: data_manager.pyに実装（本日）
2. **Phase 2**: テスト実行（本日）
3. **Phase 3**: 本番運用開始（明日以降）

## テスト計画

### 1. ユニットテスト
- 環境情報取得の正常動作確認
- 減点計算の正確性確認
- 信頼度調整の正確性確認

### 2. 統合テスト
- 既存の予測保存処理との整合性確認
- ログ出力の確認
- データベース保存の確認

### 3. 本番前検証
- 過去データで再予測して結果を確認
- 調整後の信頼度分布が期待通りか確認

## ロールバック計画

問題が発生した場合：
1. `config/environmental_penalty_rules.yaml`の`system.enabled`を`false`に設定
2. または`data_manager.py`で環境要因減点処理をコメントアウト

## 注意事項

1. **予測タイプ**: BEFOREのみに適用（ADVANCEは環境情報が不完全な可能性）
2. **NULL処理**: 環境情報が欠損している場合の処理を実装
3. **パフォーマンス**: 大量の予測保存時のパフォーマンス影響を監視

## 成功基準

1. 信頼度Bの予測が適切にC/Dに調整される
2. 調整後の予測が既存の戦略Aで購入される
3. システムエラーが発生しない
4. ログが正しく記録される

---

*作成日: 2025-12-11*
*作成者: Claude Code*
