# 選手詳細分析機能 - 設計書

## 目的
各選手の詳細な傾向を分析し、予想精度を向上させる

---

## 分析項目

### 1. 競艇場別成績 ✅ 既存データで可能

**分析内容:**
- 各競艇場での勝率・連対率
- 得意な競艇場、苦手な競艇場

**使用データ:**
- `entries`: racer_number, racer_name
- `races`: venue_code, race_date
- `results`: rank

**実装例:**
```sql
-- 選手4042（例）の競艇場別1着率
SELECT
    v.name as venue_name,
    COUNT(CASE WHEN res.rank = 1 THEN 1 END) as wins,
    COUNT(*) as total_races,
    COUNT(CASE WHEN res.rank = 1 THEN 1 END) * 100.0 / COUNT(*) as win_rate
FROM entries e
JOIN races r ON e.race_id = r.id
JOIN results res ON r.id = res.race_id AND e.pit_number = res.pit_number
JOIN venues v ON r.venue_code = v.code
WHERE e.racer_number = '4042'
GROUP BY v.name
ORDER BY win_rate DESC
```

---

### 2. コース別成績 ✅ 既存データで可能

**分析内容:**
- 各コース（1-6）での勝率
- 得意コース、苦手コース

**ポイント:**
- 基本的にpit_number = コース（スタート位置）
- 1コースからの勝率が高い選手 vs アウトコースが得意な選手

**実装例:**
```sql
-- 選手のコース別1着率
SELECT
    res.pit_number as course,
    COUNT(CASE WHEN res.rank = 1 THEN 1 END) as wins,
    COUNT(*) as total,
    COUNT(CASE WHEN res.rank = 1 THEN 1 END) * 100.0 / COUNT(*) as win_rate
FROM entries e
JOIN races r ON e.race_id = r.id
JOIN results res ON r.id = res.race_id AND e.pit_number = res.pit_number
WHERE e.racer_number = '4042'
GROUP BY res.pit_number
ORDER BY res.pit_number
```

---

### 3. ナイター成績 ⚠️ 追加データ必要

**分析内容:**
- デイレース vs ナイターレースの成績比較

**必要なデータ:**
- レース開始時刻（現在取得していない）
- または、ナイター開催場の情報

**ナイター開催場（参考）:**
- 桐生、蒲郡、住之江、丸亀、下関、若松、大村 など

**対応方法:**
1. **簡易版**: 競艇場でナイター判定
   - ナイター場のリストを作成
   - その競艇場でのレース = ナイターとみなす

2. **正確版**: レース時刻を取得
   - HTMLから時刻情報をスクレイピング
   - 17時以降 = ナイター

---

### 4. 対戦相手による成績変化 ⚠️ 複雑な分析

**分析内容:**
- 特定選手と一緒に走ると成績が下がる
- 例: A選手とB選手が同じレースに出ると、A選手の勝率が下がる

**必要な分析:**
```sql
-- 選手Aが選手Bと同走した時の成績
SELECT
    COUNT(CASE WHEN res_a.rank = 1 THEN 1 END) as wins,
    COUNT(*) as total,
    COUNT(CASE WHEN res_a.rank = 1 THEN 1 END) * 100.0 / COUNT(*) as win_rate_with_b
FROM entries e_a
JOIN entries e_b ON e_a.race_id = e_b.race_id AND e_a.racer_number != e_b.racer_number
JOIN results res_a ON e_a.race_id = res_a.race_id AND e_a.pit_number = res_a.pit_number
WHERE e_a.racer_number = '4042'  -- 選手A
  AND e_b.racer_number = '5257'  -- 選手B
```

**課題:**
- 組み合わせが膨大（全選手 × 全選手）
- サンプル数が少なくなりやすい（同じ相手と何回走るか）
- 統計的に意味のある差を検出するには大量データが必要

**実装優先度: 低**（データが十分溜まってから）

---

### 5. モーター相性 ✅ 既存データで可能

**分析内容:**
- 良いモーター（2連率が高い）を引いた時の成績
- モーター2連率と選手成績の相関

**実装例:**
```sql
-- 選手のモーター2連率別成績
SELECT
    CASE
        WHEN e.motor_second_rate >= 40 THEN '良モーター(40%以上)'
        WHEN e.motor_second_rate >= 30 THEN '普通(30-40%)'
        ELSE '悪モーター(30%未満)'
    END as motor_quality,
    COUNT(CASE WHEN res.rank = 1 THEN 1 END) as wins,
    COUNT(*) as total,
    COUNT(CASE WHEN res.rank = 1 THEN 1 END) * 100.0 / COUNT(*) as win_rate
FROM entries e
JOIN results res ON e.race_id = res.race_id AND e.pit_number = res.pit_number
WHERE e.racer_number = '4042'
GROUP BY motor_quality
```

---

### 6. 枠番（進入コース）別成績 ✅ 既存データで可能

**分析内容:**
- 枠番（抽選で決まる番号）とコース（実際のスタート位置）の関係
- 「枠なり進入」する選手 vs コースを変える選手

**注意:**
現在の実装では pit_number がコース（進入）を表している
枠番情報は明示的に保存していないため、精密な分析は難しい

---

## 実装優先順位

### Phase 1: すぐ実装可能（既存データのみ）

1. **競艇場別成績** - 得意場・苦手場の判定
2. **コース別成績** - 得意コース・苦手コース
3. **モーター相性** - モーター2連率と成績の相関

### Phase 2: 軽微な追加データで実装

4. **ナイター成績** - 競艇場ベースの簡易判定

### Phase 3: 大量データ蓄積後

5. **対戦相手分析** - サンプル数が必要

---

## データベース設計の追加検討

### 必要なテーブル・カラム

#### racesテーブルへの追加（検討）
```sql
ALTER TABLE races ADD COLUMN race_time TEXT;  -- レース時刻 "15:30"
ALTER TABLE races ADD COLUMN is_night INTEGER DEFAULT 0;  -- ナイターフラグ
```

#### 新規テーブル: racer_statistics（選手統計）
```sql
CREATE TABLE racer_statistics (
    racer_number TEXT NOT NULL,
    venue_code TEXT NOT NULL,
    course INTEGER NOT NULL,  -- 1-6
    total_races INTEGER DEFAULT 0,
    wins INTEGER DEFAULT 0,
    win_rate REAL,
    place_2_rate REAL,
    place_3_rate REAL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (racer_number, venue_code, course)
);
```

**メリット:**
- 毎回集計する必要がない（高速化）
- 定期的に更新する仕組みが必要

**デメリット:**
- メンテナンスが必要
- データ不整合の可能性

**判断:** まずは動的集計で実装、遅くなったら統計テーブル化

---

## 実装イメージ

### RacerAnalyzer クラス

```python
class RacerAnalyzer:
    """選手の詳細分析クラス"""

    def analyze_racer_by_venue(self, racer_number, days=365):
        """競艇場別成績を分析"""
        # 各競艇場での勝率・連対率
        pass

    def analyze_racer_by_course(self, racer_number, days=365):
        """コース別成績を分析"""
        # 1-6コースごとの勝率
        pass

    def analyze_racer_motor_affinity(self, racer_number, days=365):
        """モーター相性を分析"""
        # モーター2連率と選手成績の相関
        pass

    def get_racer_characteristics(self, racer_number, days=365):
        """選手の特徴を抽出"""
        # 得意場、得意コース、モーター依存度などを判定
        pass

    def generate_racer_insights(self, racer_number, days=365):
        """選手分析を言語化"""
        # 「この選手は三国競艇場が得意で、1コースからの勝率が高い」
        pass
```

---

## UIへの統合

### 新規タブ: 「🏃 選手分析」

**機能:**
1. 選手番号・名前で検索
2. 競艇場別成績の表示（棒グラフ）
3. コース別成績の表示（レーダーチャート）
4. モーター相性の表示
5. 総合評価と特徴の言語化

---

## 予想への活用方法

### スコアリングへの統合

**現在のスコア配分:**
- コース: 40点
- 選手: 40点
- モーター: 20点

**選手スコアの詳細化:**
- 基礎勝率: 15点
- **競艇場相性: 10点** ← 新規
- **コース相性: 10点** ← 新規
- ST・F/L: 5点

**例:**
- 選手A: 三国が得意（+5点）、1コースが得意（+5点）
- → 三国・1コースでの信頼度アップ

---

## 実装スケジュール

### 今セッション（可能なら）
- RacerAnalyzer の基本クラス作成
- 競艇場別・コース別分析の実装

### 次回以降
- ナイター判定の実装
- UI統合
- スコアリングへの反映

---

## 注意事項

1. **サンプル数の考慮**
   - 10レース未満のデータは参考値
   - 30レース以上で信頼性が上がる

2. **過学習の防止**
   - 過去の成績が必ずしも未来を予測しない
   - 直近の調子も重要

3. **データの鮮度**
   - 選手の成長・衰え
   - 半年前と今では状況が違う

---

**作成日**: 2024-10-29
**最終更新**: 2024-10-29
