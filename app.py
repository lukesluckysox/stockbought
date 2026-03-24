# app.py
import datetime as dt
import math
import zoneinfo

import pandas as pd
import streamlit as st
import yfinance as yf

# ============================================================
# CONFIG
# ============================================================

UNIVERSE_TICKERS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "META",
    "NVDA", "BRK-B", "JPM", "JNJ", "V",
    "TSLA", "NFLX", "AMD", "INTC", "CRM",
    "DIS", "BAC", "PFE", "KO", "PEP",
    "SQ", "ROKU", "SHOP", "ABNB", "PLTR",
    "SOFI", "F", "GM", "NIO", "RIVN",
]

BLUE_CHIP_TICKERS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "META",
    "NVDA", "BRK-B", "JPM", "JNJ", "V",
]

# Major indexes for the ticker row
INDEX_TICKERS = {
    "^GSPC": "S&P 500",
    "^DJI": "Dow Jones",
    "^IXIC": "NASDAQ",
    "^RUT": "Russell 2000",
    "^VIX": "VIX",
}

# Top 10 Indexes / ETFs (clickable section)
TOP_INDEX_ETF_TICKERS = {
    "SPY": "SPDR S&P 500 ETF",
    "QQQ": "Invesco QQQ (NASDAQ-100)",
    "DIA": "SPDR Dow Jones ETF",
    "IWM": "iShares Russell 2000",
    "VTI": "Vanguard Total Stock Market",
    "VOO": "Vanguard S&P 500",
    "ARKK": "ARK Innovation ETF",
    "XLF": "Financial Select Sector SPDR",
    "XLK": "Technology Select Sector SPDR",
    "GLD": "SPDR Gold Shares",
}

# Educational allocation model (NOT financial advice)
ALLOCATION_MODEL = {
    "US Stocks / Tech": 30,
    "Index Funds (S&P, Total Market)": 25,
    "International / Emerging": 15,
    "Bonds / Fixed Income": 15,
    "Crypto / Alternatives": 10,
    "Cash / Money Market": 5,
}

ALLOCATION_COLORS = [
    "#6366f1",  # indigo
    "#22c55e",  # green
    "#f59e0b",  # amber
    "#3b82f6",  # blue
    "#f97316",  # orange
    "#94a3b8",  # slate
]

LOOKBACK_MONTHS = 3

NYSE_TZ = zoneinfo.ZoneInfo("America/New_York")

# init session_state
if "watchlist" not in st.session_state:
    st.session_state.watchlist = []
if "selected_ticker" not in st.session_state:
    st.session_state.selected_ticker = None
if "selected_etf" not in st.session_state:
    st.session_state.selected_etf = None


# ============================================================
# NYSE CLOCK
# ============================================================

def get_nyse_status():
    now = dt.datetime.now(NYSE_TZ)
    today_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
    today_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
    weekday = now.weekday()

    if weekday >= 5:
        days_ahead = 7 - weekday
        next_open = (now + dt.timedelta(days=days_ahead)).replace(
            hour=9, minute=30, second=0, microsecond=0
        )
        delta = next_open - now
        return False, "CLOSED (Weekend)", format_timedelta(delta)

    if now < today_open:
        delta = today_open - now
        return False, "PRE-MARKET", format_timedelta(delta)

    if now < today_close:
        delta = today_close - now
        return True, "OPEN", format_timedelta(delta)

    if weekday == 4:
        next_open = (now + dt.timedelta(days=3)).replace(
            hour=9, minute=30, second=0, microsecond=0
        )
    else:
        next_open = (now + dt.timedelta(days=1)).replace(
            hour=9, minute=30, second=0, microsecond=0
        )
    delta = next_open - now
    return False, "AFTER-HOURS", format_timedelta(delta)


def format_timedelta(td):
    total_seconds = int(td.total_seconds())
    if total_seconds < 0:
        return "00h 00m 00s"
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}h {minutes:02d}m {seconds:02d}s"


def render_nyse_clock():
    is_open, status, countdown = get_nyse_status()
    now_et = dt.datetime.now(NYSE_TZ).strftime("%I:%M:%S %p ET")

    if is_open:
        dot_color = "#22c55e"
        countdown_label = "Closes in"
    else:
        dot_color = "#ef4444"
        countdown_label = "Opens in"

    st.markdown(
        f"""
        <div style="display:flex;align-items:center;gap:24px;padding:10px 16px;
                    background:#0f172a;border:1px solid #1e293b;border-radius:12px;
                    margin-bottom:12px;flex-wrap:wrap;">
          <div style="display:flex;align-items:center;gap:8px;">
            <span style="display:inline-block;width:10px;height:10px;border-radius:50%;
                         background:{dot_color};"></span>
            <span style="font-weight:700;font-size:15px;">NYSE: {status}</span>
          </div>
          <div style="font-size:13px;color:#94a3b8;">
            🕐 {now_et}
          </div>
          <div style="font-size:13px;color:#94a3b8;">
            {countdown_label}: <span style="font-weight:600;color:#e2e8f0;">{countdown}</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ============================================================
# INDEX TICKER ROW
# ============================================================

@st.cache_data(ttl=120)
def fetch_index_data():
    rows = []
    for sym, name in INDEX_TICKERS.items():
        try:
            t = yf.Ticker(sym)
            info = t.info or {}
            price = (
                info.get("regularMarketPrice")
                or info.get("currentPrice")
                or info.get("previousClose")
            )
            prev = info.get("regularMarketPreviousClose") or info.get("previousClose")
            if price and prev and prev != 0:
                change_pct = ((price - prev) / prev) * 100
            else:
                change_pct = 0.0
        except Exception:
            price = None
            change_pct = 0.0
        rows.append({"symbol": sym, "name": name, "price": price, "change_pct": change_pct})
    return rows


def render_index_row():
    data = fetch_index_data()

    cards_html = ""
    for d in data:
        price_str = f"{d['price']:,.2f}" if d["price"] else "N/A"
        chg = d["change_pct"]
        color = "#22c55e" if chg >= 0 else "#ef4444"
        arrow = "▲" if chg >= 0 else "▼"

        cards_html += f"""
        <div style="flex:1;min-width:140px;background:#0f172a;border:1px solid #1e293b;
                    border-radius:10px;padding:10px 14px;text-align:center;">
          <div style="font-size:11px;color:#94a3b8;font-weight:600;">{d['name']}</div>
          <div style="font-size:18px;font-weight:700;margin:4px 0;">{price_str}</div>
          <div style="font-size:12px;color:{color};font-weight:600;">
            {arrow} {chg:+.2f}%
          </div>
        </div>
        """

    st.markdown(
        f"""
        <div style="display:flex;gap:10px;margin-bottom:16px;flex-wrap:wrap;">
          {cards_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


# ============================================================
# LEGEND
# ============================================================

def render_legend():
    st.markdown(
        """
        <div style="background:#0f172a;border:1px solid #1e293b;border-radius:12px;
                    padding:16px 20px;margin-bottom:16px;">
          <div style="font-weight:700;font-size:15px;margin-bottom:10px;">
            📖 How to Read This Dashboard
          </div>

          <div style="display:flex;gap:24px;flex-wrap:wrap;">

            <!-- Sentiment Score -->
            <div style="flex:1;min-width:220px;">
              <div style="font-weight:600;font-size:13px;color:#e2e8f0;margin-bottom:6px;">Sentiment Score (-1.0 to +1.0)</div>
              <div style="font-size:12px;color:#94a3b8;margin-bottom:8px;">
                Based on each ticker's 3-month price return as a proxy for market sentiment.
              </div>
              <div style="display:flex;flex-direction:column;gap:4px;">
                <div style="display:flex;align-items:center;gap:6px;">
                  <span style="padding:2px 8px;border-radius:999px;background:#16a34a;color:white;font-size:11px;font-weight:600;">Strong Bullish (+0.60 to +1.00)</span>
                  <span style="font-size:11px;color:#94a3b8;">Return ≥ +30%</span>
                </div>
                <div style="display:flex;align-items:center;gap:6px;">
                  <span style="padding:2px 8px;border-radius:999px;background:#16a34a;color:white;font-size:11px;font-weight:600;">Bullish (+0.20 to +0.59)</span>
                  <span style="font-size:11px;color:#94a3b8;">Return +5% to +29%</span>
                </div>
                <div style="display:flex;align-items:center;gap:6px;">
                  <span style="padding:2px 8px;border-radius:999px;background:#eab308;color:white;font-size:11px;font-weight:600;">Neutral (-0.19 to +0.19)</span>
                  <span style="font-size:11px;color:#94a3b8;">Return -5% to +5%</span>
                </div>
                <div style="display:flex;align-items:center;gap:6px;">
                  <span style="padding:2px 8px;border-radius:999px;background:#dc2626;color:white;font-size:11px;font-weight:600;">Bearish (-0.20 to -0.59)</span>
                  <span style="font-size:11px;color:#94a3b8;">Return -5% to -29%</span>
                </div>
                <div style="display:flex;align-items:center;gap:6px;">
                  <span style="padding:2px 8px;border-radius:999px;background:#dc2626;color:white;font-size:11px;font-weight:600;">Strong Bearish (-0.60 to -1.00)</span>
                  <span style="font-size:11px;color:#94a3b8;">Return ≤ -30%</span>
                </div>
              </div>
            </div>

            <!-- Overall Sentiment Bar -->
            <div style="flex:1;min-width:220px;">
              <div style="font-weight:600;font-size:13px;color:#e2e8f0;margin-bottom:6px;">Overall Market Sentiment (0–100)</div>
              <div style="font-size:12px;color:#94a3b8;margin-bottom:8px;">
                The average sentiment across all tracked tickers, mapped to a 0–100 scale.
              </div>
              <div style="display:flex;flex-direction:column;gap:4px;font-size:12px;color:#94a3b8;">
                <div>🔴 <strong style="color:#ef4444;">0–35</strong> — Market leaning bearish</div>
                <div>🟡 <strong style="color:#eab308;">35–65</strong> — Market neutral / mixed</div>
                <div>🟢 <strong style="color:#22c55e;">65–100</strong> — Market leaning bullish</div>
              </div>
              <div style="font-size:11px;color:#64748b;margin-top:8px;">
                The arrow on the gradient bar shows where the market sits right now.
              </div>
            </div>

            <!-- Column Definitions -->
            <div style="flex:1;min-width:220px;">
              <div style="font-weight:600;font-size:13px;color:#e2e8f0;margin-bottom:6px;">Dashboard Columns</div>
              <div style="display:flex;flex-direction:column;gap:4px;font-size:12px;color:#94a3b8;">
                <div><strong style="color:#e2e8f0;">Blue Chips</strong> — Top 10 large-cap stalwarts</div>
                <div><strong style="color:#e2e8f0;">Underperformers</strong> — 10 worst 3M returns</div>
                <div><strong style="color:#e2e8f0;">Most Bullish</strong> — 10 highest sentiment scores</div>
                <div><strong style="color:#e2e8f0;">Most Bearish</strong> — 10 lowest sentiment scores</div>
                <div><strong style="color:#e2e8f0;">Watchlist</strong> — Your personal tickers (add via sidebar)</div>
              </div>
              <div style="font-size:11px;color:#64748b;margin-top:8px;">
                Click 📈 Chart on any tile to view a price chart.
              </div>
            </div>

          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ============================================================
# PIE CHART — EDUCATIONAL ALLOCATION
# ============================================================

def render_allocation_pie():
    # Build SVG pie chart
    categories = list(ALLOCATION_MODEL.keys())
    values = list(ALLOCATION_MODEL.values())
    colors = ALLOCATION_COLORS
    total = sum(values)

    slices_svg = ""
    legend_html = ""
    cumulative = 0

    for i, (cat, val) in enumerate(zip(categories, values)):
        start_angle = (cumulative / total) * 360
        end_angle = ((cumulative + val) / total) * 360
        cumulative += val

        # SVG arc path
        large_arc = 1 if (end_angle - start_angle) > 180 else 0
        start_rad = math.radians(start_angle - 90)
        end_rad = math.radians(end_angle - 90)

        x1 = 100 + 80 * math.cos(start_rad)
        y1 = 100 + 80 * math.sin(start_rad)
        x2 = 100 + 80 * math.cos(end_rad)
        y2 = 100 + 80 * math.sin(end_rad)

        slices_svg += f"""<path d="M100,100 L{x1:.1f},{y1:.1f} A80,80 0 {large_arc},1 {x2:.1f},{y2:.1f} Z"
                          fill="{colors[i]}" stroke="#1e293b" stroke-width="1"/>"""

        legend_html += f"""
        <div style="display:flex;align-items:center;gap:6px;margin-bottom:4px;">
          <span style="display:inline-block;width:12px;height:12px;border-radius:3px;
                       background:{colors[i]};flex-shrink:0;"></span>
          <span style="font-size:12px;color:#e2e8f0;">{cat}</span>
          <span style="font-size:12px;color:#94a3b8;margin-left:auto;font-weight:600;">{val}%</span>
        </div>
        """

    st.markdown(
        f"""
        <div style="background:#0f172a;border:1px solid #1e293b;border-radius:16px;
                    padding:16px;margin-bottom:16px;">
          <div style="font-weight:700;font-size:15px;margin-bottom:4px;">
            📊 Sample Portfolio Allocation
          </div>
          <div style="font-size:11px;color:#64748b;margin-bottom:12px;">
            ⚠️ Educational reference only — NOT financial advice. Consult a licensed advisor.
          </div>
          <div style="display:flex;align-items:center;gap:24px;flex-wrap:wrap;">
            <div>
              <svg width="200" height="200" viewBox="0 0 200 200">
                {slices_svg}
                <circle cx="100" cy="100" r="40" fill="#0f172a"/>
                <text x="100" y="96" text-anchor="middle" fill="#e2e8f0"
                      font-size="11" font-weight="600">Diversified</text>
                <text x="100" y="112" text-anchor="middle" fill="#94a3b8"
                      font-size="10">Portfolio</text>
              </svg>
            </div>
            <div style="flex:1;min-width:180px;">
              {legend_html}
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ============================================================
# TOP 10 INDEXES / ETFs (CLICKABLE)
# ============================================================

@st.cache_data(ttl=120)
def fetch_etf_data():
    rows = []
    tickers_list = list(TOP_INDEX_ETF_TICKERS.keys())

    # Fetch history for charts
    end = dt.datetime.today()
    start = end - dt.timedelta(days=90)
    hist = yf.download(
        tickers=tickers_list,
        start=start,
        end=end,
        auto_adjust=True,
        progress=False,
        group_by="ticker",
        threads=True,
    )

    for sym in tickers_list:
        name = TOP_INDEX_ETF_TICKERS[sym]
        try:
            t = yf.Ticker(sym)
            info = t.info or {}
            price = (
                info.get("currentPrice")
                or info.get("regularMarketPrice")
                or info.get("regularMarketPreviousClose")
                or info.get("previousClose")
            )
        except Exception:
            price = None

        # Get return from history
        try:
            if len(tickers_list) > 1:
                series = hist[sym]["Close"] if ("Close" in hist[sym]) else hist["Close"][sym]
            else:
                series = hist["Close"]
            if len(series) >= 2:
                change_pct = (series.iloc[-1] / series.iloc[0] - 1) * 100
                if hasattr(change_pct, "item"):
                    change_pct = change_pct.item()
            else:
                change_pct = 0.0
            # Fallback price from history
            if price is None and len(series) > 0:
                price = series.iloc[-1]
                if hasattr(price, "item"):
                    price = price.item()
        except Exception:
            change_pct = 0.0

        rows.append({
            "ticker": sym,
            "name": name,
            "price": price,
            "change_pct": float(change_pct) if change_pct else 0.0,
        })

    return rows, hist


def render_etf_section():
    st.markdown("### 🏛️ Top 10 Indexes & ETFs")
    st.caption("Click any ETF to view its 3-month chart.")

    etf_data, etf_hist = fetch_etf_data()

    # If an ETF is selected, show its chart first
    if st.session_state.selected_etf:
        render_etf_chart(st.session_state.selected_etf, etf_data, etf_hist)

    # Render as 2 rows of 5
    for row_start in range(0, len(etf_data), 5):
        cols = st.columns(5)
        for i, col in enumerate(cols):
            idx = row_start + i
            if idx >= len(etf_data):
                break
            d = etf_data[idx]
            with col:
                price_str = f"${d['price']:.2f}" if d["price"] else "N/A"
                chg = d["change_pct"]
                color = "#22c55e" if chg >= 0 else "#ef4444"
                arrow = "▲" if chg >= 0 else "▼"

                st.markdown(
                    f"""
                    <div style="background:#111827;border:1px solid #1f2937;border-radius:10px;
                                padding:10px;text-align:center;margin-bottom:4px;">
                      <div style="font-weight:700;font-size:14px;">{d['ticker']}</div>
                      <div style="font-size:11px;color:#94a3b8;margin-bottom:4px;
                                  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">
                        {d['name']}
                      </div>
                      <div style="font-size:16px;font-weight:700;">{price_str}</div>
                      <div style="font-size:12px;color:{color};font-weight:600;">
                        {arrow} {chg:+.2f}% (3M)
                      </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                if st.button(f"📈 Chart", key=f"etf_chart_{d['ticker']}"):
                    st.session_state.selected_etf = d["ticker"]
                    st.rerun()


def render_etf_chart(ticker, etf_data, etf_hist):
    entry = None
    for d in etf_data:
        if d["ticker"] == ticker:
            entry = d
            break

    if not entry:
        st.session_state.selected_etf = None
        return

    price_str = f"${entry['price']:.2f}" if entry["price"] else "N/A"
    chg = entry["change_pct"]
    color = "#22c55e" if chg >= 0 else "#ef4444"

    try:
        tickers_list = list(TOP_INDEX_ETF_TICKERS.keys())
        if len(tickers_list) > 1:
            series = etf_hist[ticker]["Close"] if ("Close" in etf_hist[ticker]) else etf_hist["Close"][ticker]
        else:
            series = etf_hist["Close"]
        chart_data = series.dropna().reset_index()
        chart_data.columns = ["Date", "Close"]
    except Exception:
        chart_data = pd.DataFrame()

    st.markdown(
        f"""
        <div style="background:#0f172a;border:1px solid #1e293b;border-radius:16px;
                    padding:20px;margin:8px 0;">
          <div style="display:flex;justify-content:space-between;align-items:center;">
            <div>
              <span style="font-size:22px;font-weight:700;">{ticker}</span>
              <span style="font-size:14px;color:#94a3b8;margin-left:8px;">{entry['name']}</span>
            </div>
            <div style="text-align:right;">
              <div style="font-size:20px;font-weight:700;">{price_str}</div>
              <div style="font-size:13px;color:{color};">{chg:+.2f}% (3M)</div>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not chart_data.empty:
        st.line_chart(chart_data.set_index("Date")["Close"], use_container_width=True)
    else:
        st.write("No chart data available.")

    if st.button("✕ Close chart", key="close_etf_chart"):
        st.session_state.selected_etf = None
        st.rerun()


# ============================================================
# DATA FETCHING — STOCKS
# ============================================================

@st.cache_data(ttl=60)
def fetch_stock_history(tickers, months: int = 3):
    end = dt.datetime.today()
    start = end - dt.timedelta(days=months * 30)
    data = yf.download(
        tickers=tickers,
        start=start,
        end=end,
        auto_adjust=True,
        progress=False,
        group_by="ticker",
        threads=True,
    )
    return data


@st.cache_data(ttl=60)
def fetch_stock_info(tickers):
    rows = []
    for t in tickers:
        try:
            ticker = yf.Ticker(t)
            info = ticker.info or {}
            last_price = (
                info.get("currentPrice")
                or info.get("regularMarketPrice")
                or info.get("regularMarketPreviousClose")
                or info.get("previousClose")
            )
            name = info.get("shortName") or info.get("longName") or t
        except Exception:
            last_price = None
            name = t
        rows.append({"ticker": t, "name": name, "price": last_price})
    return pd.DataFrame(rows)


def get_price_from_history(hist, ticker):
    try:
        series = hist[ticker]["Close"] if ("Close" in hist[ticker]) else hist["Close"][ticker]
        if len(series) > 0:
            val = series.iloc[-1]
            if hasattr(val, "item"):
                return val.item()
            return float(val)
    except Exception:
        pass
    return None


def compute_return_and_sentiment(hist, tickers):
    rows = []
    for t in tickers:
        try:
            series = hist[t]["Close"] if ("Close" in hist[t]) else hist["Close"][t]
            if len(series) < 2:
                ret_pct = 0.0
            else:
                ret_pct = (series.iloc[-1] / series.iloc[0] - 1) * 100.0
                if hasattr(ret_pct, "item"):
                    ret_pct = ret_pct.item()
        except Exception:
            ret_pct = 0.0

        if ret_pct >= 30:
            sent = 1.0
        elif ret_pct >= 15:
            sent = 0.7
        elif ret_pct >= 5:
            sent = 0.4
        elif ret_pct >= -5:
            sent = 0.0
        elif ret_pct >= -15:
            sent = -0.4
        elif ret_pct >= -30:
            sent = -0.7
        else:
            sent = -1.0

        rows.append({"ticker": t, "change_pct": float(ret_pct), "sentiment": sent})
    return pd.DataFrame(rows)


def build_universe_df(extra_watchlist=None, months=3):
    if extra_watchlist is None:
        extra_watchlist = []
    tickers = sorted(set(UNIVERSE_TICKERS + extra_watchlist))
    hist = fetch_stock_history(tickers, months=months)
    info_df = fetch_stock_info(tickers)
    perf_df = compute_return_and_sentiment(hist, tickers)
    df = info_df.merge(perf_df, on="ticker", how="left")

    for idx, row in df.iterrows():
        if row["price"] is None or (isinstance(row["price"], float) and math.isnan(row["price"])):
            fallback = get_price_from_history(hist, row["ticker"])
            if fallback is not None:
                df.at[idx, "price"] = fallback

    return df, hist


# ============================================================
# CLASSIFICATION & METRICS
# ============================================================

def classify_groups(df: pd.DataFrame):
    blue = df[df["ticker"].isin(BLUE_CHIP_TICKERS)].copy()
    universe_only = df[df["ticker"].isin(UNIVERSE_TICKERS)]
    under = universe_only.sort_values("change_pct").head(10).copy()
    bullish = universe_only.sort_values("sentiment", ascending=False).head(10).copy()
    bearish = universe_only.sort_values("sentiment").head(10).copy()
    return blue, under, bullish, bearish


def compute_overall_sentiment(df: pd.DataFrame) -> float:
    if df.empty:
        return 50.0
    mean_sent = df["sentiment"].mean()
    return (mean_sent + 1) * 50.0


def sentiment_color(score: float) -> str:
    if score >= 0.3:
        return "#16a34a"
    if score <= -0.3:
        return "#dc2626"
    return "#eab308"


def sentiment_label(score: float) -> str:
    if score >= 0.6:
        return "Strong Bullish"
    if score >= 0.2:
        return "Bullish"
    if score <= -0.6:
        return "Strong Bearish"
    if score <= -0.2:
        return "Bearish"
    return "Neutral"


# ============================================================
# UI HELPERS — STOCKS
# ============================================================

def overall_bar(sent_0_100: float):
    left_color = "#dc2626"
    mid_color = "#eab308"
    right_color = "#16a34a"
    pos = max(0, min(100, sent_0_100))

    st.markdown(
        f"""
        <div style="width:100%;padding:8px 0;">
          <div style="font-weight:600;margin-bottom:4px;">
            Overall Market Sentiment (3M, price-based): {pos:.1f}
          </div>
          <div style="position:relative;height:24px;border-radius:999px;
                      background: linear-gradient(90deg,{left_color}, {mid_color}, {right_color});">
            <div style="position:absolute;left:{pos}%;top:-4px;
                        transform:translateX(-50%);
                        width:0;height:0;border-left:6px solid transparent;
                        border-right:6px solid transparent;border-bottom:8px solid #111;">
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_tile(row):
    score = row["sentiment"]
    bg = sentiment_color(score)
    label = sentiment_label(score)
    change = row["change_pct"]
    price = row["price"]
    ticker = row["ticker"]

    price_str = f"${price:.2f}" if price is not None and not (isinstance(price, float) and math.isnan(price)) else "N/A"

    st.markdown(
        f"""
        <div style="
            border-radius:12px;
            padding:10px 12px;
            margin-bottom:8px;
            background-color:#111827;
            border:1px solid #1f2937;
        ">
          <div style="display:flex;justify-content:space-between;align-items:center;">
            <div>
              <div style="font-weight:600;font-size:14px;">{ticker}</div>
              <div style="font-size:12px;color:#9ca3af;">{row['name']}</div>
            </div>
            <div style="text-align:right;">
              <div style="font-weight:600;">{price_str}</div>
              <div style="font-size:12px;color:{'#22c55e' if change >=0 else '#ef4444'};">
                {change:+.2f}% (3M)
              </div>
            </div>
          </div>
          <div style="margin-top:6px;font-size:12px;">
            <span style="padding:2px 6px;border-radius:999px;
                         background-color:{bg};color:white;font-size:11px;">
              {label} ({score:+.2f})
            </span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.button(f"📈 Chart", key=f"chart_{ticker}"):
        st.session_state.selected_ticker = ticker
        st.rerun()


def render_group(title: str, df_group: pd.DataFrame):
    st.subheader(title)
    if df_group.empty:
        st.write("No data.")
        return
    for _, row in df_group.iterrows():
        render_tile(row)


def render_chart_dialog(hist, df):
    ticker = st.session_state.selected_ticker
    if ticker is None:
        return

    row = df[df["ticker"] == ticker]
    if row.empty:
        st.session_state.selected_ticker = None
        return

    row = row.iloc[0]
    price = row["price"]
    price_str = f"${price:.2f}" if price is not None and not (isinstance(price, float) and math.isnan(price)) else "N/A"

    try:
        series = hist[ticker]["Close"] if ("Close" in hist[ticker]) else hist["Close"][ticker]
        chart_data = series.dropna().reset_index()
        chart_data.columns = ["Date", "Close"]
    except Exception:
        chart_data = pd.DataFrame()

    st.markdown("---")
    st.markdown(
        f"""
        <div style="background:#0f172a;border:1px solid #1e293b;border-radius:16px;
                    padding:20px;margin:8px 0;">
          <div style="display:flex;justify-content:space-between;align-items:center;">
            <div>
              <span style="font-size:22px;font-weight:700;">{ticker}</span>
              <span style="font-size:14px;color:#94a3b8;margin-left:8px;">{row['name']}</span>
            </div>
            <div style="text-align:right;">
              <div style="font-size:20px;font-weight:700;">{price_str}</div>
              <div style="font-size:13px;color:{'#22c55e' if row['change_pct'] >=0 else '#ef4444'};">
                {row['change_pct']:+.2f}% (3M)
              </div>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not chart_data.empty:
        st.line_chart(chart_data.set_index("Date")["Close"], use_container_width=True)
    else:
        st.write("No chart data available.")

    if st.button("✕ Close chart", key="close_stock_chart"):
        st.session_state.selected_ticker = None
        st.rerun()

    st.markdown("---")


# ============================================================
# STREAMLIT APP
# ============================================================

def main():
    st.set_page_config(
        page_title="Bullish/Bearish Stock Dashboard (Live)",
        layout="wide",
        initial_sidebar_state="collapsed",
    )

    st.title("📊 Bullish / Bearish Stock Dashboard (Live from Yahoo Finance)")
    st.caption(
        "No logins, no API key — using free yfinance data as a proxy for sentiment."
    )

    # 1. NYSE Clock
    render_nyse_clock()

    # 2. Major Indexes row
    render_index_row()

    # 3. Legend explaining sentiment values
    render_legend()

    # 4. Pie chart + Top 10 ETFs side by side
    pie_col, etf_col = st.columns([1, 2])
    with pie_col:
        render_allocation_pie()
    with etf_col:
        render_etf_section()

    st.markdown("---")

    # Sidebar controls + watchlist input
    with st.sidebar:
        st.header("Controls")
        months = st.slider("Lookback (months)", 1, 12, value=LOOKBACK_MONTHS)
        refresh = st.button("🔁 Refresh data")

        st.markdown("---")
        st.subheader("Personal Watchlist")
        new_symbol = st.text_input("Add ticker (e.g., AAPL)", value="")
        add_btn = st.button("Add to watchlist")

        if add_btn and new_symbol:
            sym = new_symbol.strip().upper()
            if sym and sym not in st.session_state.watchlist:
                st.session_state.watchlist.append(sym)

        if st.session_state.watchlist:
            st.write("Current watchlist:")
            st.write(", ".join(st.session_state.watchlist))
            remove_sym = st.selectbox(
                "Remove ticker", [""] + st.session_state.watchlist, index=0
            )
            if remove_sym:
                if st.button("Remove selected"):
                    st.session_state.watchlist = [
                        x for x in st.session_state.watchlist if x != remove_sym
                    ]

    if refresh:
        fetch_stock_history.clear()
        fetch_stock_info.clear()
        fetch_index_data.clear()
        fetch_etf_data.clear()

    with st.spinner("Loading stock data from Yahoo Finance..."):
        df, hist = build_universe_df(extra_watchlist=st.session_state.watchlist, months=months)

    # Stock chart popup
    if st.session_state.selected_ticker:
        render_chart_dialog(hist, df)

    blue, under, bullish, bearish = classify_groups(df)
    overall = compute_overall_sentiment(df)
    overall_bar(overall)

    # Main layout: 4 standard groups + personal watchlist
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        render_group("Blue Chips (10)", blue)
    with col2:
        render_group("Underperformers", under)
    with col3:
        render_group("Most Bullish", bullish)
    with col4:
        render_group("Most Bearish", bearish)
    with col5:
        wl_df = df[df["ticker"].isin(st.session_state.watchlist)].copy()
        render_group("Watchlist", wl_df)

    with st.expander("Show raw data"):
        st.dataframe(df.sort_values("ticker").reset_index(drop=True))


if __name__ == "__main__":
    main()
