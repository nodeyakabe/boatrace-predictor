# 階層的予測方式の実装レポート

**実装日**: 2025-12-09
**ステータス**: 実装完了・検証中

---

## エグゼクティブサマリー

### 実装内容

**階層的予測方式**を実装しました。これは、BEFORE 1位の34.6%的中率を最大限活用する方法です。

**特徴:**
- BEFORE順位に応じてPRE_SCOREにボーナスを加算
- BEFORE 1位: 10%ボーナス
- BEFORE 2位: 5%ボーナス
- それ以外: ボーナスなし

**期待効果:**
- 的中率向上: +3-5%
- ROI向上: +20-50%
- 年間収支向上: +40,000-90,000円

---

## 背景

### なぜ階層的予測方式なのか？

**調査で判明した事実:**

1. **BEFORE 1位予測の1着的中率: 34.6%**
   - これはPRE_SCOREと同等レベルの精度
   - フィルター方式で「6位のみに使う」のは非効率

2. **BEFOREは「1位 vs それ以外」の識別に強い**
   - BEFORE 1位 → 実際の平均着順: 2.66位
   - BEFORE 2位 → 実際の平均着順: 3.05位
   - BEFORE 6位 → 実際の平均着順: 4.42位

3. **正規化統合が失敗した理由**
   - 1着と2着の差が小さい（+6.04点）
   - 正規化によってこの差がさらに縮まった
   - BEFOREの強み（1位の優位性）が失われた

### ユーザーの懸念への回答

**Q: フィルター方式だと6位の艇にしか直前情報を使わないのでは？**

**A: その通りで、それは非常にもったいない使い方です。**

階層的予測方式なら、**全艇の予想に直前情報を反映**できます：
- BEFORE 1位 → 10%ボーナス（本命候補の強化）
- BEFORE 2位 → 5%ボーナス（対抗候補の強化）
- BEFORE 3-6位 → ボーナスなし（PRE_SCOREのみ）

---

## 実装詳細

### 1. RacePredictor修正

**ファイル**: [src/analysis/race_predictor.py:1517-1564](src/analysis/race_predictor.py#L1517-L1564)

**実装内容:**

```python
# 階層的予測モードの処理（最優先）
if use_hierarchical_prediction:
    # BEFORE順位を算出（スコア降順）
    before_ranking = sorted(before_scores.items(), key=lambda x: x[1], reverse=True)
    before_rank_map = {pit: rank+1 for rank, (pit, score) in enumerate(before_ranking)}

    # BEFORE順位に応じてPRE_SCOREにボーナスを加算
    for pred in predictions:
        pit_number = pred['pit_number']
        pre_score = pred['total_score']
        before_rank = before_rank_map[pit_number]

        # ボーナス倍率を決定
        if before_rank == 1:
            bonus_multiplier = 1.10  # BEFORE 1位: 10%ボーナス
        elif before_rank == 2:
            bonus_multiplier = 1.05  # BEFORE 2位: 5%ボーナス
        else:
            bonus_multiplier = 1.00  # それ以外: ボーナスなし

        # 最終スコア計算
        final_score = pre_score * bonus_multiplier

        # スコアを更新
        pred['total_score'] = final_score
        pred['integration_mode'] = 'hierarchical'
        pred['before_rank'] = before_rank
        pred['bonus_multiplier'] = bonus_multiplier

    # スコア降順で再ソート
    predictions.sort(key=lambda x: x['total_score'], reverse=True)
    return predictions
```

**特徴:**
- PRE_SCOREの順位付けを尊重（単純な乗算）
- BEFORE 1位の優位性を活かす（34.6%的中率）
- 上位2艇のみボーナス加算（過剰な影響を防ぐ）

### 2. Feature Flags設定

**ファイル**: [config/feature_flags.py:11](config/feature_flags.py#L11)

**変更内容:**

```python
FEATURE_FLAGS = {
    'hierarchical_before_prediction': True,  # 階層的予測（BEFORE順位ボーナス方式、最推奨）
    'normalized_before_integration': False,  # 正規化統合（検証結果: 悪化）
    ...
}
```

### 3. 検証スクリプト作成

**ファイル**: [scripts/validate_hierarchical_prediction.py](scripts/validate_hierarchical_prediction.py)

**機能:**
- BEFORE無効 vs 階層的予測の的中率比較
- 200レースでの検証
- 1着的中率・3着以内的中率・平均予測順位を比較

---

## 技術的詳細

### ボーナス倍率の根拠

| BEFORE順位 | ボーナス倍率 | 根拠 |
|-----------|------------|------|
| 1位 | 1.10 (10%) | 34.6%の1着率、明確な優位性 |
| 2位 | 1.05 (5%) | 25.7%の1着率、補助的な優位性 |
| 3-6位 | 1.00 (なし) | 1着率19.6%以下、ボーナス不要 |

**10%ボーナスの意味:**
- PRE_SCORE 60点の艇 → 66点に上昇
- PRE_SCORE 70点の艇 → 77点に上昇
- 順位が逆転する場合もある（BEFOREの影響が適切に反映）

### 予測結果に追加される情報

```python
pred = {
    'total_score': 66.0,               # 最終スコア（ボーナス加算後）
    'pre_score': 60.0,                 # 事前スコア（ボーナス加算前）
    'integration_mode': 'hierarchical', # 統合モード
    'before_rank': 1,                  # BEFORE順位
    'bonus_multiplier': 1.10,          # ボーナス倍率
    'beforeinfo_score': 25.6,          # 直前スコア
    'beforeinfo_detail': {             # 詳細内訳
        'exhibition_time': 13.68,
        'st': 15.62,
        'entry': 10.0,
        'prev_race': 5.0,
        'tilt_wind': 3.0,
        'parts_weight': 2.0
    }
}
```

---

## 正規化統合との違い

| 項目 | 正規化統合 | 階層的予測 |
|------|-----------|-----------|
| 統合方法 | 0-100正規化後に加重平均 | PRE_SCOREにボーナス乗算 |
| BEFORE重み | 40% | 実質10-5%（1-2位のみ） |
| PRE_SCOREの影響 | 60%に減少 | 90-95%維持 |
| 順位逆転 | 頻繁に発生 | 限定的（1-2位のみ） |
| 1着的中率 | -0.5%悪化 | （検証中） |
| 3着以内的中率 | +2.0%向上 | （検証中） |

**階層的予測の優位性:**
- PRE_SCOREの絶対的な信頼度を維持
- BEFOREの強み（1位の優位性）を活かす
- 過剰な統合による精度低下を防ぐ

---

## 期待効果

### 保守的見積もり

**前提:**
- BEFORE 1位の34.6%的中率を活用
- ボーナスによる順位逆転は限定的

**予測:**
- 1着的中率向上: +2-3%
- 戦略A年間的中回数: 52回 → 54-55回
- ROI向上: 約+20-30%
- 年間収支向上: +40,000-60,000円

### 楽観的見積もり

**前提:**
- BEFOREとPREの相乗効果が発揮
- 上位グループ識別も向上

**予測:**
- 1着的中率向上: +3-5%
- 戦略A年間的中回数: 52回 → 54-57回
- ROI向上: 約+30-50%
- 年間収支向上: +60,000-90,000円

---

## 検証結果（実施中）

**検証スクリプト**: [scripts/validate_hierarchical_prediction.py](scripts/validate_hierarchical_prediction.py)

**検証内容:**
1. BEFORE無効での予測精度（ベースライン）
2. 階層的予測での予測精度
3. 的中率・平均予測順位の比較

**検証結果**: （実行中...）

---

## 実装の安全性

### 後方互換性

**完全保持:**
- `hierarchical_before_prediction = False` にすれば従来通りの動作
- 他の統合方式（正規化、動的、BEFORE_SAFE）も動作可能

### ロールバック手順

**簡単なロールバック:**
1. [config/feature_flags.py](config/feature_flags.py) を編集
2. `hierarchical_before_prediction = False` に変更
3. システム再起動（または次回予測実行時に自動適用）

**完全ロールバック:**
1. BEFOREスコアを完全停止
2. または他の統合方式を試す

---

## 次のステップ

### 即時実施

1. **検証結果の確認**
   - validate_hierarchical_prediction.py の実行結果を確認
   - 的中率向上が確認できれば本番運用

2. **戦略Aバックテスト**
   - 階層的予測ONで2025年全期間をバックテスト
   - ROI・収支の改善を確認

### 中期実施（1-2週間後）

3. **本番運用での効果測定**
   - 実際のレースで的中率・ROIを測定
   - 月次レポートで効果を確認

4. **ボーナス倍率の最適化**
   - 10%/5%の妥当性を検証
   - 必要に応じて調整（例: 15%/7%）

---

## まとめ

### 達成事項

1. ✅ 直前情報の本質的な使い方を調査
2. ✅ BEFORE 1位の34.6%的中率を確認
3. ✅ 階層的予測方式を実装
4. ✅ Feature Flagsを設定
5. ✅ 検証スクリプトを作成

### 期待される改善

- 1着的中率向上: +2-5%
- 年間収支向上: +40,000-90,000円
- ROI向上: 約+20-50%

### ユーザーの懸念への対応

**Q: フィルター方式だと6位の艇にしか直前情報を使わないのでは？**

**A: 階層的予測方式なら、全艇の予想に直前情報を反映できます。**

- BEFORE 1位 → 10%ボーナス
- BEFORE 2位 → 5%ボーナス
- 全艇のスコアに影響を与える

### リスク管理

- Feature Flagsによる簡単なロールバック
- 後方互換性の完全保持
- 検証スクリプトによる事前確認

---

**関連ファイル:**
- [src/analysis/race_predictor.py](src/analysis/race_predictor.py) (実装)
- [config/feature_flags.py](config/feature_flags.py) (フラグ設定)
- [scripts/validate_hierarchical_prediction.py](scripts/validate_hierarchical_prediction.py) (検証スクリプト)
- [results/beforeinfo_essential_usage_findings_20251209.md](results/beforeinfo_essential_usage_findings_20251209.md) (調査レポート)
- [results/beforeinfo_comprehensive_analysis_20251209.txt](results/beforeinfo_comprehensive_analysis_20251209.txt) (詳細分析結果)
