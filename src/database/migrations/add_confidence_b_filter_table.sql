-- 信頼度Bフィルター結果テーブル
CREATE TABLE IF NOT EXISTS confidence_b_filter_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    race_id INTEGER NOT NULL,
    filter_accept BOOLEAN NOT NULL,  -- フィルター通過したか
    filter_reason TEXT,               -- 判定理由
    expected_hit_rate REAL,          -- 期待的中率（%）
    venue_hit_rate REAL,             -- 会場別的中率（%）
    monthly_hit_rate REAL,           -- 月別的中率（%）
    adjustment_type TEXT,            -- 調整タイプ（NORMAL, EXCLUDED_VENUE, LOW_SEASON_REJECTED等）
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (race_id) REFERENCES races(id)
);

-- インデックス
CREATE INDEX IF NOT EXISTS idx_confidence_b_filter_race_id
    ON confidence_b_filter_results(race_id);

CREATE INDEX IF NOT EXISTS idx_confidence_b_filter_accept
    ON confidence_b_filter_results(filter_accept);
