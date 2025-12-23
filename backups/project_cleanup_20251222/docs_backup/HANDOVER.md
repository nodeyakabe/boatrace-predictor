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

### プロジェクト構成最適化（進行中）

**目的**: Claude Codeの認識間違い・誤読を防止

**実施内容**:
1. ✅ Opusによる問題分析完了
   - ルートディレクトリ143ファイル（目標15個）
   - docs/に209ファイル（目標50個+archive）
   - 情報の矛盾・重複・古い情報の混在を確認
2. 🔄 Phase 1: マスタードキュメント一元化（進行中）
   - ✅ 残タスク一覧.mdをDB実測値に修正
   - 🔄 HANDOVER.md新規作成（このファイル）
   - ⏳ README.mdの同期
3. ⏳ Phase 2-4: ディレクトリ整理（未着手）

**詳細**: Opus分析結果は前回セッション参照

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
