-- Market Analyzer — Supabase Initial Migration
-- Run this in the Supabase SQL Editor (Dashboard → SQL Editor → New query)

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================
-- ANALYSES: One record per analysis run
-- ============================================================
CREATE TABLE analyses (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    market_overview TEXT NOT NULL,
    fear_greed_crypto INTEGER,
    fear_greed_label TEXT,
    overall_sentiment TEXT,
    whale_summary TEXT,
    defi_flows TEXT,
    risk_warnings JSONB DEFAULT '[]'::jsonb,
    upcoming_catalysts JSONB DEFAULT '[]'::jsonb,
    portfolio_allocation JSONB,
    raw_response JSONB,
    run_duration_seconds FLOAT,
    errors JSONB DEFAULT '[]'::jsonb
);

CREATE INDEX idx_analyses_created_at ON analyses(created_at DESC);

-- ============================================================
-- SIGNALS: Buy/Sell signals with full PNL tracking
-- ============================================================
CREATE TABLE signals (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    analysis_id UUID REFERENCES analyses(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,

    -- Signal metadata
    type TEXT NOT NULL CHECK (type IN ('BUY', 'SELL', 'HOLD', 'CLOSE')),
    asset TEXT NOT NULL,
    asset_name TEXT NOT NULL,
    market TEXT NOT NULL CHECK (market IN ('crypto', 'gold', 'silver', 'us_stocks', 'egx')),
    shariah_status TEXT DEFAULT 'COMPLIANT' CHECK (shariah_status IN ('COMPLIANT', 'QUESTIONABLE')),

    -- Price levels
    current_price FLOAT NOT NULL,
    entry_zone_low FLOAT,
    entry_zone_high FLOAT,
    stop_loss FLOAT,
    take_profit_1 FLOAT,
    take_profit_2 FLOAT,
    take_profit_3 FLOAT,

    -- Signal quality
    confidence TEXT CHECK (confidence IN ('HIGH', 'MEDIUM', 'LOW')),
    timeframe TEXT CHECK (timeframe IN ('SCALP', 'SWING', 'POSITION')),
    risk_reward_ratio FLOAT,
    position_size_pct FLOAT,
    position_size_usd FLOAT,
    reasoning TEXT NOT NULL,
    urgency TEXT CHECK (urgency IN ('IMMEDIATE', 'TODAY', 'THIS_WEEK', 'WATCH')),

    -- Volatility metrics
    volatility_score INTEGER CHECK (volatility_score BETWEEN 1 AND 10),
    volatility_label TEXT CHECK (volatility_label IN ('LOW', 'MODERATE', 'HIGH', 'EXTREME')),
    atr_pct FLOAT,
    hist_vol_30d FLOAT,

    -- Volume metrics
    volume_ratio FLOAT,
    volume_signal TEXT CHECK (volume_signal IN ('HIGH', 'ELEVATED', 'NORMAL', 'LOW')),
    volume_confirms_price BOOLEAN DEFAULT TRUE,

    -- Status & PNL tracking (updated by PNL tracker)
    status TEXT DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'CLOSED', 'EXPIRED', 'CANCELLED')),
    closed_at TIMESTAMPTZ,
    close_price FLOAT,
    close_reason TEXT CHECK (close_reason IN ('hit_sl', 'hit_tp1', 'hit_tp2', 'hit_tp3', 'signal_sell', 'manual', 'expired')),
    realized_pnl_pct FLOAT,
    realized_pnl_usd FLOAT,
    hold_duration_hours FLOAT
);

CREATE INDEX idx_signals_created_at ON signals(created_at DESC);
CREATE INDEX idx_signals_asset ON signals(asset);
CREATE INDEX idx_signals_market ON signals(market);
CREATE INDEX idx_signals_status ON signals(status);
CREATE INDEX idx_signals_type ON signals(type);
CREATE INDEX idx_signals_confidence ON signals(confidence);

-- ============================================================
-- SIGNAL_SNAPSHOTS: Time-series PNL tracking per active signal
-- ============================================================
CREATE TABLE signal_snapshots (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    signal_id UUID REFERENCES signals(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    current_price FLOAT NOT NULL,
    unrealized_pnl_pct FLOAT,
    unrealized_pnl_usd FLOAT,
    distance_to_sl_pct FLOAT,
    distance_to_tp1_pct FLOAT
);

CREATE INDEX idx_snapshots_signal_id ON signal_snapshots(signal_id);
CREATE INDEX idx_snapshots_created_at ON signal_snapshots(created_at DESC);

-- ============================================================
-- MARKET_DATA: Price snapshots per asset (per run)
-- ============================================================
CREATE TABLE market_data (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    asset TEXT NOT NULL,
    market TEXT NOT NULL,
    price FLOAT NOT NULL,
    change_24h FLOAT,
    change_7d FLOAT,
    volume_24h FLOAT,
    market_cap FLOAT,
    indicators JSONB,
    ohlcv_daily JSONB,
    key_levels JSONB
);

CREATE INDEX idx_market_data_created_at ON market_data(created_at DESC);
CREATE INDEX idx_market_data_asset ON market_data(asset);

-- ============================================================
-- WHALE_ALERTS: DeFiLlama & on-chain flow records
-- ============================================================
CREATE TABLE whale_alerts (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    analysis_id UUID REFERENCES analyses(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    blockchain TEXT,
    asset TEXT NOT NULL,
    amount FLOAT,
    amount_usd FLOAT NOT NULL,
    tx_type TEXT,
    from_owner TEXT,
    to_owner TEXT,
    interpretation TEXT
);

CREATE INDEX idx_whale_alerts_created_at ON whale_alerts(created_at DESC);

-- ============================================================
-- PORTFOLIO_POSITIONS: User-managed positions
-- ============================================================
CREATE TABLE portfolio_positions (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    asset TEXT NOT NULL,
    asset_name TEXT NOT NULL,
    market TEXT NOT NULL,
    entry_price FLOAT NOT NULL,
    current_price FLOAT,
    quantity FLOAT NOT NULL,
    stop_loss FLOAT,
    take_profit FLOAT,
    status TEXT DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'CLOSED', 'PARTIAL')),
    pnl_usd FLOAT,
    pnl_pct FLOAT,
    notes TEXT,
    signal_id UUID REFERENCES signals(id),
    closed_at TIMESTAMPTZ,
    close_price FLOAT,
    close_reason TEXT
);

CREATE INDEX idx_positions_status ON portfolio_positions(status);
CREATE INDEX idx_positions_asset ON portfolio_positions(asset);

-- ============================================================
-- RUN_LOGS: Debugging and monitoring
-- ============================================================
CREATE TABLE run_logs (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    run_type TEXT DEFAULT 'manual',
    status TEXT NOT NULL,
    duration_seconds FLOAT,
    fetchers_status JSONB,
    error_details TEXT
);

CREATE INDEX idx_run_logs_created_at ON run_logs(created_at DESC);

-- ============================================================
-- VIEWS
-- ============================================================

CREATE VIEW latest_analysis AS
SELECT * FROM analyses ORDER BY created_at DESC LIMIT 1;

CREATE VIEW active_signals AS
SELECT * FROM signals WHERE status = 'ACTIVE' ORDER BY created_at DESC;

CREATE VIEW open_positions AS
SELECT * FROM portfolio_positions WHERE status = 'OPEN' ORDER BY created_at DESC;

-- Performance view: closed signals with PNL
CREATE VIEW signal_performance AS
SELECT
    s.id,
    s.asset,
    s.asset_name,
    s.market,
    s.type,
    s.confidence,
    s.timeframe,
    s.current_price AS entry_price,
    s.stop_loss,
    s.take_profit_1,
    s.close_price,
    s.close_reason,
    s.realized_pnl_pct,
    s.realized_pnl_usd,
    s.hold_duration_hours,
    s.volatility_score,
    s.created_at AS signal_date,
    s.closed_at,
    CASE
        WHEN s.close_reason IN ('hit_tp1', 'hit_tp2', 'hit_tp3') THEN 'WIN'
        WHEN s.close_reason = 'hit_sl' THEN 'LOSS'
        ELSE 'NEUTRAL'
    END AS outcome
FROM signals s
WHERE s.type = 'BUY' AND s.status = 'CLOSED'
ORDER BY s.closed_at DESC;

-- Live unrealized PNL for active signals
CREATE VIEW active_signal_pnl AS
SELECT
    s.id,
    s.asset,
    s.asset_name,
    s.market,
    s.confidence,
    s.current_price AS entry_price,
    s.stop_loss,
    s.take_profit_1,
    s.created_at AS signal_date,
    snap.current_price AS latest_price,
    snap.unrealized_pnl_pct,
    snap.distance_to_sl_pct,
    snap.distance_to_tp1_pct,
    snap.created_at AS last_updated
FROM signals s
LEFT JOIN LATERAL (
    SELECT * FROM signal_snapshots
    WHERE signal_id = s.id
    ORDER BY created_at DESC
    LIMIT 1
) snap ON true
WHERE s.status = 'ACTIVE' AND s.type = 'BUY'
ORDER BY s.created_at DESC;

-- Monthly PNL aggregation for equity curve
CREATE VIEW monthly_pnl AS
SELECT
    DATE_TRUNC('month', closed_at) AS month,
    COUNT(*) FILTER (WHERE close_reason IN ('hit_tp1', 'hit_tp2', 'hit_tp3')) AS wins,
    COUNT(*) FILTER (WHERE close_reason = 'hit_sl') AS losses,
    COUNT(*) AS total_closed,
    ROUND(AVG(realized_pnl_pct)::numeric, 2) AS avg_pnl_pct,
    ROUND(SUM(realized_pnl_pct)::numeric, 2) AS total_pnl_pct,
    market
FROM signals
WHERE type = 'BUY' AND status = 'CLOSED' AND closed_at IS NOT NULL
GROUP BY DATE_TRUNC('month', closed_at), market
ORDER BY month DESC;

-- ============================================================
-- ROW LEVEL SECURITY
-- ============================================================
ALTER TABLE analyses ENABLE ROW LEVEL SECURITY;
ALTER TABLE signals ENABLE ROW LEVEL SECURITY;
ALTER TABLE signal_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE market_data ENABLE ROW LEVEL SECURITY;
ALTER TABLE whale_alerts ENABLE ROW LEVEL SECURITY;
ALTER TABLE portfolio_positions ENABLE ROW LEVEL SECURITY;
ALTER TABLE run_logs ENABLE ROW LEVEL SECURITY;

-- Anon (frontend) read-only
CREATE POLICY "anon_read_analyses" ON analyses FOR SELECT USING (true);
CREATE POLICY "anon_read_signals" ON signals FOR SELECT USING (true);
CREATE POLICY "anon_read_snapshots" ON signal_snapshots FOR SELECT USING (true);
CREATE POLICY "anon_read_market_data" ON market_data FOR SELECT USING (true);
CREATE POLICY "anon_read_whale_alerts" ON whale_alerts FOR SELECT USING (true);
CREATE POLICY "anon_read_positions" ON portfolio_positions FOR SELECT USING (true);
CREATE POLICY "anon_read_run_logs" ON run_logs FOR SELECT USING (true);

-- Service role (Python analyzer) full access
CREATE POLICY "service_all_analyses" ON analyses FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "service_all_signals" ON signals FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "service_all_snapshots" ON signal_snapshots FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "service_all_market_data" ON market_data FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "service_all_whale_alerts" ON whale_alerts FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "service_all_positions" ON portfolio_positions FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "service_all_run_logs" ON run_logs FOR ALL USING (true) WITH CHECK (true);

-- Anon can manage their own portfolio positions from the dashboard
CREATE POLICY "anon_insert_positions" ON portfolio_positions FOR INSERT WITH CHECK (true);
CREATE POLICY "anon_update_positions" ON portfolio_positions FOR UPDATE USING (true);

-- ============================================================
-- CLEANUP FUNCTION (run periodically or via Supabase Edge Function)
-- ============================================================
CREATE OR REPLACE FUNCTION cleanup_old_data() RETURNS void AS $$
BEGIN
    -- Keep market_data for 30 days
    DELETE FROM market_data WHERE created_at < NOW() - INTERVAL '30 days';
    -- Keep whale_alerts for 60 days
    DELETE FROM whale_alerts WHERE created_at < NOW() - INTERVAL '60 days';
    -- Keep run_logs for 30 days
    DELETE FROM run_logs WHERE created_at < NOW() - INTERVAL '30 days';
    -- Keep signal_snapshots for 180 days
    DELETE FROM signal_snapshots WHERE created_at < NOW() - INTERVAL '180 days';
    -- Keep analyses for 90 days (signals referenced by analysis_id use ON DELETE SET NULL)
    DELETE FROM analyses WHERE created_at < NOW() - INTERVAL '90 days';
END;
$$ LANGUAGE plpgsql;
