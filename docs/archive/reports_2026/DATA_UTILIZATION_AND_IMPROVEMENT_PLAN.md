# データ活用方法と改善事項の検討レポート

**作成日**: 2026-01-29
**対象**: wave_height補完プロジェクト完了後の次期施策検討
**作成者**: Claude Sonnet 4.5

---

## エグゼクティブサマリー

wave_height補完プロジェクトにより、データ品質が51.6%→97.1%に改善しました。本レポートでは、この成果を踏まえ、データ活用方法と今後の改善事項を提案します。

### 主要提案

| 提案 | 期待効果 | 実装難易度 | 優先度 |
|------|---------|-----------|--------|
| **1. wave_heightの予測スコアリング統合** | ROI +0-1pt（限定的） | 低 | **Medium** |
| **2. CSV方式の標準化** | 効率向上、リスク低減 | 低 | **High** |
| **3. データ品質監視の自動化** | 欠損早期発見 | 中 | **High** |
| **4. chikusen_time補完** | **効果未知数（要検証）** | 中 | **Critical** |

**推奨順序**: 4 → 2 → 3 → 1

**⚠️ 重要な発見**:
- chikusen_timeの現状カバレッジ: **0.2%**（99.8%のレースで全選手に中立点2.0を付与 = 差別化できていない）
- データがない状態での効果予測は不可能
- **補完後に初めて効果測定が可能になる**

---

## 1. wave_heightデータの活用提案

### 1-1. 現在のシステムでの位置づけ

wave_heightデータは**既に予測システムに統合済み**です：

- **取得**: `race_conditions.wave_height`（97.1%補完済み）
- **活用箇所**: `WeatherAdjuster`（環境補正レイヤー）
- **適用会場**: 海水面9場（児島、宮島、徳山、下関、若松、芦屋、福岡、唐津、大村）

```python
# src/analysis/weather_adjuster.py
if venue_code in ['05', '06', '10', ...]:  # 海水面会場
    if wave_height >= 3:  # 高波時
        adjustment = -2.0  # インコース不利補正
```

### 1-2. 活用可能性の分析

#### 現状の活用状況

- ✅ 既にWeatherAdjusterで活用中
- ✅ 海水面9場のみに適用（適切）
- 🟡 補正値が固定（wave_height >= 3で一律-2.0pt）

#### 改善の可能性

| 改善案 | 期待効果 | 理由 |
|--------|---------|------|
| **段階的補正** | ROI +0-0.5pt | 波高1-2cm/3-4cm/5cm+で補正を段階化 |
| **コース別補正** | ROI +0-0.5pt | 1コース vs 2-6コースで異なる補正 |
| **季節別重み** | ROI +0pt | 季節による波高の影響差は限定的 |

**総合評価**: 期待効果は**限定的**（ROI +0-1pt）

#### 不採用理由との比較

過去の不採用案を確認すると、wave_heightと類似の環境要因は効果が限定的でした：

- **motor_second_rate + venue_affinity**（不採用理由0-1）: 2025年で-4.58pt悪化
- **会場攻撃率スコアリング**（不採用理由0-2）: 効果±0pt

**教訓**: 環境要因の追加は、既存特徴量との重複や年度依存性のリスクが高い

### 1-3. 実装提案

#### 提案A: 段階的補正の導入（推奨）

**実装難易度**: 低（1-2時間）
**期待効果**: ROI +0-0.5pt

```python
# WeatherAdjusterに追加
WAVE_ADJUSTMENTS = {
    (0, 2): 0.0,      # 穏やか: 補正なし
    (2, 3): -0.5,     # やや高波: 軽微な補正
    (3, 5): -1.5,     # 高波: 中程度の補正
    (5, 100): -2.5,   # 大波: 強い補正
}
```

**検証手順**:
1. 2020-2025年の海水面9場データで効果検証（300レース）
2. ROI改善が+0.5pt未満なら見送り
3. +0.5pt以上なら採用

#### 提案B: 現状維持（最推奨）

**理由**:
- 既に適切な補正が適用されている
- 改善の余地が限定的（+0-1pt）
- **他の施策（chikusen_time補完: +2-5pt）を優先すべき**

**推奨**: 現状維持とし、**Phase 4（Week 5-6）で他施策完了後に再検討**

### 1-4. リスクと注意点

#### リスク

1. **既存特徴量との重複**: WeatherAdjusterが既に風速・風向き・波高を統合的に評価
2. **年度依存性**: 2025年の環境変化（モーター性能均質化）で過去の傾向が無効化される可能性
3. **サンプル数不足**: 高波（wave_height >= 5）は希少（年間10-20レース程度）

#### 注意点

- **最新年度を重視**: 3年平均より2025年のトレンドを優先
- **効果が逆転する場合は不採用**: 不採用理由0-1の教訓を適用
- **必ずバックテストで検証**: 分析スクリプトの結果は参考値

---

## 2. システム改善提案

### 2-1. CSV方式の標準化

#### 背景

wave_height補完プロジェクトでCSV方式が**大成功**:
- 109,595件のrace_conditionsを新規投入
- DB負荷ゼロで71.4時間の長時間収集を完遂
- 50タスクごとの自動保存で途中失敗時のリカバリが容易

#### 提案: CSV方式を今後のデータ収集標準とする

**適用対象**:
- ✅ 大量データ収集（1ヶ月以上、10,000レース以上）
- ✅ 長時間作業（8時間以上）
- ❌ 少量データ（1日分、100-150レース）→ 直接DB投入で問題なし

**標準化の内容**:

1. **スクリプトテンプレート整備**
   - `fetch_to_csv_parallel_improved.py`をベースに他データ種別用テンプレート作成
   - `import_xxx_from_csv.py`のテンプレート化

2. **ドキュメント整備**
   - `docs/guides/CSV_DATA_COLLECTION_GUIDE.md`に成功事例としてwave_height補完を追記
   - 推奨ワークフロー（月単位分割実行）を明記

3. **チェックリスト作成**
   - CSV方式採用判断チェックリスト
   - データ投入前の検証チェックリスト

**実装難易度**: 低（2-3時間）
**期待効果**:
- 今後の大規模データ収集の効率向上（20-30%時間短縮）
- リスク低減（途中失敗時のリカバリ容易）

**優先度**: **High**（今後の全データ収集作業に影響）

### 2-2. データ収集フローの改善

#### 現状の課題

1. **データ種別ごとにスクリプトが乱立**
   - `fetch_race_conditions_to_csv.py`
   - `fetch_to_csv_parallel.py`
   - `fetch_to_csv_parallel_improved.py`
   - ...etc

2. **統一されたインターフェースがない**
   - 各スクリプトで引数名・形式が異なる
   - 共通処理（並列化、CSV保存）が重複実装

#### 提案: 統一データ収集フレームワーク

**アーキテクチャ**:

```
UnifiedDataCollector (基底クラス)
  ├─ ParallelCSVCollector（並列CSV収集）
  │   ├─ RaceConditionsCollector
  │   ├─ RaceDetailsCollector
  │   └─ OddsCollector
  ├─ DirectDBCollector（小規模・直接DB投入）
  └─ BatchCSVImporter（CSV一括投入）
```

**メリット**:
- コード重複削減（保守性向上）
- 統一されたログ形式・エラーハンドリング
- 新規データ種別追加が容易

**実装難易度**: 中（8-12時間）
**期待効果**: 保守性向上、新規施策の実装コスト削減
**優先度**: Medium（Phase 4完了後に実施）

### 2-3. race_conditionsテーブル設計の見直し

#### 現状の課題

現在の`race_conditions`テーブル設計は良好ですが、将来の拡張性を考慮した改善余地があります：

| 課題 | 影響 |
|------|------|
| wave_heightが整数型 | 精度不足（実際は0.5cm刻み） |
| 中止レースの識別が困難 | NULLが「欠損」か「中止」か不明 |
| 収集元の記録がない | データ品質の追跡困難 |

#### 提案: スキーマ改善（Phase 4後に実施）

```sql
-- 改善案（参考）
ALTER TABLE race_conditions ADD COLUMN wave_height_cm REAL;  -- 0.5cm刻み
ALTER TABLE race_conditions ADD COLUMN is_cancelled INTEGER DEFAULT 0;
ALTER TABLE race_conditions ADD COLUMN data_source TEXT;  -- 'api', 'csv', 'manual'
```

**実装難易度**: 中（既存データ移行が必要）
**期待効果**: データ品質向上、将来の拡張性確保
**優先度**: Low（急ぎではない、Phase 4後に検討）

### 2-4. 中止レース管理の改善

#### 現状

wave_height補完プロジェクトで発見：
- 残存欠損3,339件（1.5%）は**全て中止レース**
- 現在、中止レースは「データ欠損」と見分けがつかない

#### 提案: 中止レースフラグの導入

**実装案**:

```sql
-- racesテーブルに追加
ALTER TABLE races ADD COLUMN is_cancelled INTEGER DEFAULT 0;

-- 中止レース判定ロジック
UPDATE races SET is_cancelled = 1
WHERE id IN (
    SELECT r.id FROM races r
    LEFT JOIN results res ON r.id = res.race_id
    WHERE res.race_id IS NULL
);
```

**メリット**:
- データ品質レポートの精度向上（「欠損」と「中止」を区別）
- 予測対象レースの明確化（中止レースを除外）

**実装難易度**: 低（1-2時間）
**期待効果**: データ品質監視の精度向上
**優先度**: Medium

---

## 3. メンテナンス計画

### 3-1. 自動化可能な部分

#### 既に実装済みの自動化

| タスク | スクリプト | スケジュール | 状態 |
|--------|-----------|-------------|------|
| オリジナル展示データ収集 | `daily_tenji_collector.py` | 毎朝7:10 | ✅ 実装済み |
| 直前情報収集 | `fetch_yesterday_beforeinfo.py` | 毎朝6:10 | ✅ 実装済み |
| オッズ収集 | `fetch_today_odds.py` | 毎朝7:40 | ✅ 実装済み |
| レース結果収集 | `fetch_yesterday_results.py` | 毎朝5:00 | ✅ 実装済み |

**現状**: daily_schedulerが未起動（残タスク一覧のC-1-4参照）

#### 追加すべき自動化

**1. データ品質監視の自動化**

**目的**: データ欠損を早期発見

**実装案**:

```python
# scripts/maintenance/daily_data_quality_check.py
def check_data_quality(date):
    """指定日のデータ品質をチェック"""
    checks = {
        'races': check_race_count(date),
        'race_conditions': check_wave_height_coverage(date),
        'race_details': check_chikusen_time_coverage(date),
        'results': check_results_coverage(date),
    }

    # 基準未達の場合、Discordに通知
    if any(check['status'] == 'NG' for check in checks.values()):
        notify_discord(f"データ品質警告: {date}")
```

**スケジュール**: 毎朝8:00（全データ収集完了後）

**実装難易度**: 中（4-6時間）
**優先度**: **High**（Phase 2で実施）

**2. 週次データ補完チェック**

**目的**: 欠損データの補完忘れを防止

**実装案**:

```python
# scripts/maintenance/weekly_backfill_check.py
def suggest_backfill():
    """補完が必要なデータを検出して提案"""
    # 過去7日間のデータ品質を確認
    # 欠損率が10%以上の項目を列挙
    # 補完コマンドを生成
```

**スケジュール**: 毎週日曜 9:00

**実装難易度**: 低（2-3時間）
**優先度**: Medium

### 3-2. 定期監視項目

#### 日次監視（自動化）

| 項目 | 基準 | アクション |
|------|------|-----------|
| レース数 | 100-200レース/日 | 基準外ならDiscord通知 |
| wave_height補完率 | 95%以上 | 95%未満ならDiscord通知 |
| オッズ収集率 | 90%以上 | 90%未満ならDiscord通知 |
| 結果収集率 | 98%以上 | 98%未満ならDiscord通知 |

#### 週次監視（手動確認）

```sql
-- 過去1週間のデータ品質確認
SELECT
    r.race_date,
    COUNT(DISTINCT r.id) as total_races,
    SUM(CASE WHEN rc.wave_height IS NOT NULL THEN 1 ELSE 0 END) as with_wave,
    SUM(CASE WHEN rd.chikusen_time IS NOT NULL THEN 1 ELSE 0 END) as with_chikusen,
    SUM(CASE WHEN res.race_id IS NOT NULL THEN 1 ELSE 0 END) as with_result
FROM races r
LEFT JOIN race_conditions rc ON r.id = rc.race_id
LEFT JOIN race_details rd ON r.id = rd.race_id AND rd.pit_number = 1
LEFT JOIN results res ON r.id = res.race_id
WHERE r.race_date >= date('now', '-7 days')
GROUP BY r.race_date
ORDER BY r.race_date DESC;
```

#### 月次監視（手動確認）

- データベースサイズ増加率
- インデックス効率（ANALYZE実行）
- 外部キー制約違反チェック

### 3-3. トラブル時の対処フロー

#### 1. データ収集失敗

**検出**: Discord通知、または手動確認

**対処手順**:
1. 失敗原因の確認（ログファイル参照）
2. ネットワークエラー→ 再実行
3. API仕様変更→ スクリプト修正
4. その他→ エスカレーション

**再実行コマンド**:
```bash
# 特定日のデータ再収集
python scripts/data_collection/daily_tenji_collector.py --date 2026-01-29
```

#### 2. データ品質低下

**検出**: 週次監視で発見

**対処手順**:
1. SQL_QUERY_SAMPLES.mdのクエリで原因特定
2. 補完可能なら補完スクリプト実行
3. 補完不可（中止レース）なら記録のみ

#### 3. データベース肥大化

**検出**: 月次監視で発見

**対処手順**:
1. 古いログデータの削除（1年以上前）
2. VACUUM実行
3. インデックス再構築（REINDEX）

---

## 4. 優先度付き次期施策リスト

### Critical（即座に実施）

#### 施策4-1: chikusen_time補完

| 項目 | 内容 |
|------|------|
| **期待効果** | **未知数（データ不足により効果測定不可）** |
| **実装コスト** | 中（wave_height補完と同じ手法で実施可能） |
| **所要時間** | 30-40時間（244,245レース） |
| **優先度** | **Critical** |
| **実施時期** | Week 2-3（2026-02-02 ～ 2026-02-15） |

**⚠️ 現状の問題**:
- **カバレッジ: 0.2%**（708/303,576レース）← 上位AIが誤認した0.6%は2025年のみ
- **99.8%のレースで全選手に中立点2.0を付与** = スコア差別化できない
- 予測ロジックでは「使用」されているが、実質的に**無意味**
- データがないため効果測定が不可能（ROI改善効果は未知数）

**補完の真の目的**:
1. **効果測定のためのデータ基盤構築**（補完後に初めて有用性判定が可能）
2. 差別化できる特徴量として活用開始
3. 補完後のバックテストで最適な重み（現在4.0点）を決定
4. **有効性が低ければ重みをゼロに**（現状維持ではない）

**実施手順**:
1. CSV方式でrace_details収集（月単位で実施）
2. DB投入後、**必ず効果検証**（6年間バックテスト）
3. **ROI改善が+1pt未満なら使用中止を検討**

**関連ドキュメント**:
- 残タスク一覧 Week 2-3: chikusen_timeデータ補完

---

### High（Phase 1-2で実施）

#### 施策4-2: CSV方式の標準化

| 項目 | 内容 |
|------|------|
| **期待効果** | 今後の全データ収集作業の効率向上（20-30%短縮） |
| **実装コスト** | 低（2-3時間） |
| **所要時間** | 2-3時間 |
| **優先度** | **High** |
| **実施時期** | Week 1-2（2026-01-29 ～ 2026-02-01） |

**実施内容**:
1. `docs/guides/CSV_DATA_COLLECTION_GUIDE.md`にwave_height補完事例を追記
2. チェックリスト作成（CSV方式採用判断、投入前検証）
3. テンプレートスクリプト整備

**成果物**:
- 更新版CSV_DATA_COLLECTION_GUIDE.md
- CSV方式採用判断チェックリスト（Markdown）
- データ投入前検証チェックリスト（Markdown）

---

#### 施策4-3: データ品質監視の自動化

| 項目 | 内容 |
|------|------|
| **期待効果** | データ欠損の早期発見、手動確認作業の削減 |
| **実装コスト** | 中（4-6時間） |
| **所要時間** | 4-6時間 |
| **優先度** | **High** |
| **実施時期** | Week 3-4（2026-02-02 ～ 2026-02-15） |

**実施内容**:
1. `scripts/maintenance/daily_data_quality_check.py`作成
2. daily_schedulerに統合（毎朝8:00実行）
3. Discord通知機能追加

**監視項目**:
- レース数（100-200レース/日）
- wave_height補完率（95%以上）
- chikusen_time補完率（95%以上）
- オッズ収集率（90%以上）
- 結果収集率（98%以上）

---

### Medium（Phase 3-4で実施）

#### 施策4-4: wave_height段階的補正の導入

| 項目 | 内容 |
|------|------|
| **期待効果** | ROI +0-0.5pt（限定的） |
| **実装コスト** | 低（1-2時間） |
| **所要時間** | 1-2時間（実装）+ 2-3時間（検証） |
| **優先度** | **Medium** |
| **実施時期** | Week 5-6（2026-02-16 ～ 2026-02-28） |

**実施条件**: chikusen_time補完完了後

**実施内容**:
1. WeatherAdjusterに段階的補正を追加
2. 2020-2025年の海水面9場データで効果検証（300レース）
3. ROI改善が+0.5pt未満なら見送り

**検証基準**:
- ROI改善: +0.5pt以上で採用
- 年度安定性: 6年中4年以上で改善
- 効果の方向性: 年度間で逆転しないこと

---

#### 施策4-5: 中止レース管理の改善

| 項目 | 内容 |
|------|------|
| **期待効果** | データ品質監視の精度向上 |
| **実装コスト** | 低（1-2時間） |
| **所要時間** | 1-2時間 |
| **優先度** | **Medium** |
| **実施時期** | Week 3-4（2026-02-02 ～ 2026-02-15） |

**実施内容**:
1. `races`テーブルに`is_cancelled`フラグ追加
2. 中止レース判定ロジック実装
3. データ品質レポートに反映

---

#### 施策4-6: 統一データ収集フレームワーク

| 項目 | 内容 |
|------|------|
| **期待効果** | 保守性向上、新規施策の実装コスト削減 |
| **実装コスト** | 中（8-12時間） |
| **所要時間** | 8-12時間 |
| **優先度** | **Medium** |
| **実施時期** | Phase 4完了後（2026-03-01以降） |

**実施条件**: Phase 4（独自数値算出）完了後

---

### Low（Phase 4後に検討）

#### 施策4-7: race_conditionsスキーマ改善

| 項目 | 内容 |
|------|------|
| **期待効果** | 将来の拡張性確保 |
| **実装コスト** | 中（既存データ移行が必要） |
| **所要時間** | 4-6時間 |
| **優先度** | **Low** |
| **実施時期** | 2026年3月以降（急ぎではない） |

**実施条件**: 他の全施策完了後

---

## 5. 実施ロードマップ

### Week 1-2（2026-01-29 ～ 2026-02-01）

```
✅ daily_scheduler起動（C-1-4）
✅ CSV方式標準化（施策4-2）
```

### Week 2-3（2026-02-02 ～ 2026-02-15）

```
🔧 chikusen_time補完実施（施策4-1）
🔧 データ品質監視自動化（施策4-3）
🔧 中止レース管理改善（施策4-5）
```

### Week 4-5（2026-02-16 ～ 2026-03-01）

```
🔬 chikusen_time効果検証（6年間バックテスト）
🔬 wave_height段階的補正検証（施策4-4）
📊 効果測定・報告書作成
```

### Week 6以降（2026-03-01以降）

```
📚 統一データ収集フレームワーク（施策4-6）
📚 race_conditionsスキーマ改善（施策4-7）
```

---

## 6. 期待される成果

### 短期（2ヶ月後: 2026-03-31）

| 指標 | 現状 | 目標 | 改善幅 |
|------|------|------|--------|
| **chikusen_time補完率** | 0.6% | 100% | +99.4% |
| **wave_height補完率** | 97.1% | 97.1% | 維持 |
| **自動収集稼働率** | 不明 | 95%以上 | - |
| **データ品質監視** | 手動 | 自動化 | - |

### 中期（6ヶ月後: 2026-07-31）

| 指標 | 現状 | 目標 | 改善幅 |
|------|------|------|--------|
| **年間ROI** | 160.5% | 165-170% | +5-10pt |
| **年間収支** | +331,980円 | +353,000-380,000円 | +21,000-48,000円 |
| **未活用カラム活用率** | 20% | 100% | +80% |

**主な貢献施策**:
- chikusen_time補完・活用: ROI +2-5pt
- その他の未活用データ活用: ROI +3-5pt
- 合計: ROI +5-10pt

---

## 7. リスクと対策

### リスク1: chikusen_time補完の失敗

**発生確率**: 低（wave_height補完と同じ手法）
**影響度**: 高（ROI +2-5pt機会損失）

**対策**:
- 月単位で分割実行（失敗時のリトライが容易）
- 先行して1ヶ月分をテスト実施
- 成功確認後に残り期間を実施

### リスク2: 効果が期待以下

**発生確率**: 中（不採用案の前例多数）
**影響度**: 中（工数の無駄）

**対策**:
- 小規模検証（300レース）を先行実施
- ROI改善が+0.5pt未満なら早期に見送り
- 必ずバックテストで検証

### リスク3: 年度依存性

**発生確率**: 中（不採用理由0-1の前例）
**影響度**: 高（2025年で効果消失の可能性）

**対策**:
- 最新年度（2025年）のトレンドを重視
- 3年平均より直近1年の効果を優先
- 年度間で効果が逆転する場合は不採用

---

## 8. 結論

### 主要推奨事項

1. **chikusen_time補完を最優先で実施**（ROI +2-5pt期待）
2. **CSV方式を標準化**（今後の効率向上）
3. **データ品質監視を自動化**（欠損早期発見）
4. **wave_heightは現状維持**（Phase 4後に再検討）

### 実施順序

```
Priority 1: chikusen_time補完（Week 2-3）
Priority 2: CSV方式標準化（Week 1-2）
Priority 3: データ品質監視自動化（Week 3-4）
Priority 4: wave_height段階的補正（Week 5-6、条件付き）
```

### 期待成果

- **短期（2ヶ月）**: データ補完完了、自動化確立
- **中期（6ヶ月）**: ROI +5-10pt、収支 +21,000-48,000円

### 次のアクション

```bash
# 1. daily_scheduler起動（自動化システム稼働）
python scripts/automation/daily_scheduler.py

# 2. CSV方式標準化（ドキュメント更新）
# docs/guides/CSV_DATA_COLLECTION_GUIDE.md を更新

# 3. chikusen_time補完開始（Week 2-3）
python scripts/data_collection/fetch_to_csv_parallel_improved.py \
  --start 2020-01-01 --end 2020-01-31 \
  --output data/csv/race_details/2020_01 \
  --workers 12
```

---

**報告書作成日**: 2026-01-29
**作成者**: Claude Sonnet 4.5
**承認**: （ユーザー承認待ち）

---

## 付録A: 不採用案から学ぶ教訓

wave_height活用を検討する上で、過去の不採用案から以下の教訓を抽出しました：

### 教訓1: 既存特徴量との重複を確認

- **逃げ率スコアリング**（不採用理由0-1）: 級別スコアと重複 → ±0pt
- **会場攻撃率スコアリング**（不採用理由0-2）: venue_affinityと重複 → ±0pt

**適用**: wave_heightは既にWeatherAdjusterで活用中 → 改善余地は限定的

### 教訓2: 最新年度を重視

- **motor_second_rate + venue_affinity**（不採用理由0-1）: 2025年で-4.58pt悪化

**適用**: 効果検証は3年平均より2025年のトレンドを優先

### 教訓3: サンプル数の重要性

- **連帯率フィルター（Motor40%+）**（不採用理由0-0）: サンプル数27件で過学習

**適用**: wave_heightの高波（>= 5cm）は希少 → サンプル数不足に注意

### 教訓4: 精度改善 ≠ ROI改善

- **コース強制化**（不採用理由7）: 精度+5.6pt、ROI-51pt

**適用**: wave_height補正で精度が向上してもROIが悪化する可能性あり

---

## 付録B: SQL_QUERY_SAMPLES.md 追加推奨クエリ

以下のクエリを`docs/guides/SQL_QUERY_SAMPLES.md`に追加することを推奨します：

### B-1. wave_height補完状況の確認

```sql
-- 年度別のwave_height補完率
SELECT
    strftime('%Y', r.race_date) as year,
    COUNT(DISTINCT r.id) as total_races,
    SUM(CASE WHEN rc.wave_height IS NOT NULL THEN 1 ELSE 0 END) as with_wave,
    ROUND(SUM(CASE WHEN rc.wave_height IS NOT NULL THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) as coverage_rate
FROM races r
LEFT JOIN race_conditions rc ON r.id = rc.race_id
WHERE r.venue_code IN ('05', '06', '10', '15', '17', '18', '19', '22', '23', '24')  -- 海水面9場
GROUP BY year
ORDER BY year DESC;
```

### B-2. 中止レースの検出

```sql
-- 結果データがないレース（中止レース候補）
SELECT
    r.race_date,
    r.venue_code,
    r.race_number,
    r.race_time,
    rc.weather,
    rc.wind_speed
FROM races r
LEFT JOIN results res ON r.id = res.race_id
LEFT JOIN race_conditions rc ON r.id = rc.race_id
WHERE res.race_id IS NULL
  AND r.race_date >= '2020-01-01'
ORDER BY r.race_date DESC, r.venue_code, r.race_number
LIMIT 100;
```

### B-3. データ品質ダッシュボード

```sql
-- 過去1週間のデータ品質サマリー
SELECT
    r.race_date,
    COUNT(DISTINCT r.id) as total_races,
    ROUND(AVG(CASE WHEN rc.wave_height IS NOT NULL THEN 100.0 ELSE 0.0 END), 1) as wave_coverage,
    ROUND(AVG(CASE WHEN rd.chikusen_time IS NOT NULL THEN 100.0 ELSE 0.0 END), 1) as chikusen_coverage,
    ROUND(AVG(CASE WHEN rd.st_time IS NOT NULL THEN 100.0 ELSE 0.0 END), 1) as st_coverage,
    ROUND(AVG(CASE WHEN res.race_id IS NOT NULL THEN 100.0 ELSE 0.0 END), 1) as result_coverage
FROM races r
LEFT JOIN race_conditions rc ON r.id = rc.race_id
LEFT JOIN race_details rd ON r.id = rd.race_id AND rd.pit_number = 1
LEFT JOIN results res ON r.id = res.race_id
WHERE r.race_date >= date('now', '-7 days')
GROUP BY r.race_date
ORDER BY r.race_date DESC;
```

---

**レポート終了**
