# 引継ぎ資料（HANDOVER）

**最終更新**: 2025-12-22 15:50
**目的**: セッション間の引継ぎ情報を一元管理（このファイルは常に最新状態に上書き更新）

---

## 📋 プロジェクト現状（一目でわかる）

### システム構成

```
【戦略B】順位予測
    ↓ ExtendedScorer（スコアリング）
    ↓ hierarchical_predictor（信頼度A-E判定）
【フィルターC】購入判定
    ↓ BetTargetEvaluator（信頼度×オッズで買うか判断）
【パターンH】買い目生成
    ↓ MultiBetGenerator（1-2軸3点買い: 200円/100円/100円）
```

### 2025年実績

| 指標 | 値 |
|------|-----|
| **年間ROI** | **136.0%** |
| **年間収支** | **+119,220円** |
| 購入レース数 | 1,105件 |
| 的中数 | 54回 |
| 的中率 | 4.89% |

> **注意**: この数値は過去のバックテストスクリプト実行結果（BASELINE_PERFORMANCE_20251220.md等より）。
> データベースのrace_predictionsテーブルからの直接集計とは異なる可能性あり。

### 予測データ生成状況（DB実測値・2025-12-22 15:45確認）

| 年度 | 総レース | advance予測 | カバー率 | 状態 |
|------|---------|------------|---------|------|
| 2020 | 9,663 | 9,661 | 99.9% | ✅ 完了 |
| 2021 | 9,538 | 9,490 | 99.5% | ✅ 完了 |
| 2022 | 35,883 | 9,800 | 27.3% | ❌ 不完全（26,083件不足） |
| 2023 | 9,084 | 0 | 0% | ❌ 未生成（9,084件不足） |
| 2024 | 14,014 | 0 | 0% | ❌ 未生成（14,014件不足） |
| 2025 | 18,980 | 0 | 0% | ❌ 未生成（18,980件不足） |

**合計不足**: 68,161件

---

## 🔴 最優先タスク

### 予測データ生成（advance）

2022-2025年のadvance予測が未完了のため、4年間安定条件の探索ができない状態。

**次のアクション**:
1. 予測生成スクリプトの特定（どれがadvanceを生成するか）
2. 2022年の残り26,083件を生成
3. 2023-2025年を生成（合計42,078件）

---

## ⚠️ 重要な注意事項

### 過去ドキュメントの誤情報

以下のドキュメントには**誤った進捗情報**が記載されています：
- `HANDOVER_20251221.md` - 2022年38%と記載（実際27.3%）
- `HANDOVER_20251222.md` - 2022年100%完了と記載（実際27.3%）

**ルール**: 必ず**データベース実測値**を確認すること。

### データベース確認コマンド

```bash
# 年度別予測データ確認
python -c "
import sqlite3
conn = sqlite3.connect('data/boatrace.db')
cur = conn.cursor()
cur.execute('''
    SELECT substr(r.race_date,1,4) as year,
           COUNT(DISTINCT r.id) as total_races,
           COUNT(DISTINCT CASE WHEN rp.prediction_type='advance' THEN rp.race_id END) as advance_races
    FROM races r
    LEFT JOIN race_predictions rp ON r.id = rp.race_id
    WHERE substr(r.race_date,1,4) >= '2020'
    GROUP BY year
    ORDER BY year
''')
for row in cur.fetchall():
    print(f'{row[0]}: {row[2]}/{row[1]} ({row[2]*100/row[1]:.1f}%)')
conn.close()
"
```

---

## 📁 主要ファイル

| ファイル | 役割 |
|---------|------|
| [残タスク一覧.md](残タスク一覧.md) | **唯一の最新状態情報源** |
| [HANDOVER.md](HANDOVER.md) | このファイル（引継ぎ情報） |
| [DATABASE_SCHEMA.md](architecture/DATABASE_SCHEMA.md) | DB構造 |
| [README.md](../README.md) | プロジェクト概要 |

**注意**: 日付付きドキュメント（`*_20251220.md`等）は過去ログ。最新情報は上記4つのみ。

---

## 🎛️ 有効なフィーチャーフラグ

```python
FEATURE_FLAGS = {
    'hierarchical_predictor': True,        # 階層的予測
    'ab_rank_special_betting': True,       # A/Bランク特別条件 (+17.2pt)
    'pairwise_scoring': True,              # ペアワイズスコアリング (+7.3pt/+3.9pt)
    'kimarite_flow_prediction': True,      # 決まり手展開予測 (+4.1pt)
    'makuri_risk_adjustment': True,        # まくりリスク調整 (+4.1pt)
    'negative_pattern_filter': True,       # マイナスパターン除外
    'upset_pattern_filter': True,          # 穴狙いパターン
    # ... その他
}
```

詳細は [config/feature_flags.py](../config/feature_flags.py) 参照

---

## 📝 最近の作業（2025-12-22）

### ✅ プロジェクト構成最適化（完了）

**目的**: Claude Codeの認識間違い・誤読を防止

**実施内容**:
1. ✅ **Phase 1: マスタードキュメント一元化**
   - ✅ 残タスク一覧.mdをDB実測値に修正（2022年27.3%, 2023-2025年0%）
   - ✅ HANDOVER.md新規作成（古いHANDOVER_*.mdをarchive）
   - ✅ CLAUDE.mdを簡素化（参照先を3つに限定）

2. ✅ **Phase 2: docs/ディレクトリ階層化**
   - ✅ 199個 → 4個（残タスク一覧.md, HANDOVER.md, README.md, LOG）
   - ✅ 階層化: architecture/, guides/, implementation/, analysis/, archive/
   - ✅ docs/README.md作成（索引として機能）

3. ✅ **Phase 3: scripts/ディレクトリ整理**
   - ✅ 296個 → 4個（知見管理ツールのみルート直下）
   - ✅ 階層化: prediction/, backtest/, analysis/, data_collection/, maintenance/, _deprecated/
   - ✅ scripts/README.md作成（推奨スクリプト明記）

4. ✅ **Phase 4: ルートディレクトリ整理**
   - ✅ 173ファイル → 3ファイル（README.md, CLAUDE.md, START_HERE.md）
   - ✅ すべての.mdをdocs/へ、すべての.pyをscripts/へ移動

**成果**:
- **ルート**: 173 → 3（-98%）
- **docs/直下**: 199 → 4（-98%）
- **scripts/直下**: 296 → 4（-99%）
- **バックアップ作成済み**: `backups/project_cleanup_20251222/`
- **移動ログ**: [docs/PROJECT_CLEANUP_LOG_20251222.md](PROJECT_CLEANUP_LOG_20251222.md)

**詳細**: [docs/PROJECT_CLEANUP_LOG_20251222.md](PROJECT_CLEANUP_LOG_20251222.md)

### ✅ 予測ロジック管理システム構築（完了）

**目的**: 予測ロジック改善時の「現状把握→変更→再テスト→比較」を効率化

**実施内容**:
1. ✅ **現状把握ドキュメント作成**
   - [docs/guides/PREDICTION_SYSTEM_STATUS.md](guides/PREDICTION_SYSTEM_STATUS.md)
   - 現在の性能指標（信頼度別の1-3着・三連単的中率）
   - 有効なフィーチャーフラグ一覧（16個ON、11個OFF）
   - 性能推移履歴

2. ✅ **ベンチマークスクリプト作成**
   - `scripts/benchmark_prediction_system.py`
   - 標準テストセット（2025年before予測、17,459レース）で性能測定
   - 結果をJSON自動保存（`data/benchmark_results/`）
   - ベースラインとの差分表示

3. ✅ **設定抽出スクリプト作成**
   - `scripts/maintenance/extract_current_config.py`
   - feature_flags.pyから有効フラグを自動抽出
   - PREDICTION_SYSTEM_STATUS.mdを自動更新

4. ✅ **変更追跡スクリプト作成**
   - `scripts/maintenance/track_performance_change.py`
   - 変更前後の性能差分を計算
   - 変更履歴をJSONで保存
   - PREDICTION_SYSTEM_STATUS.mdの履歴セクションに追記

**標準ワークフロー**:
```bash
# 1. ベースライン保存（変更前）
python scripts/benchmark_prediction_system.py --save-baseline

# 2. フラグ変更（config/feature_flags.py編集）

# 3. 再測定・比較
python scripts/benchmark_prediction_system.py --compare

# 4. 履歴記録
python scripts/maintenance/track_performance_change.py \
    --description "変更内容の説明"
```

**現在のベースライン**（2025年before予測）:
- 信頼度A: 1着72.99%, 2着29.69%, 3着23.10%, 三連単10.18%
- 信頼度B: 1着65.60%, 2着27.24%, 3着22.51%, 三連単9.07%
- 信頼度C: 1着46.01%, 2着23.33%, 3着20.22%, 三連単5.86%

**詳細**: [docs/guides/PREDICTION_SYSTEM_STATUS.md](guides/PREDICTION_SYSTEM_STATUS.md)

---

## 📚 関連ドキュメント（過去ログ・参考用）

以下は過去の分析・検証レポートです。最新情報ではありません。

| ドキュメント | 内容 | 日付 |
|-------------|------|------|
| BASELINE_PERFORMANCE_20251220.md | ROI 136.0%の根拠 | 2025-12-20 |
| HANDOVER_20251221.md | 古い引継ぎ情報（誤情報含む） | 2025-12-21 |
| HANDOVER_20251222.md | 古い引継ぎ情報（誤情報含む） | 2025-12-22朝 |

---

**更新ルール**:
- セッション終了時に必ずこのファイルを更新
- 古いHANDOVER_YYYYMMDD.mdは作成しない（このファイルを上書き）
- 重要な分析結果は `docs/analysis/YYYYMMDD_*.md` に保存

---

*作成日: 2025-12-22*
*最終更新: 2025-12-22 15:50*
