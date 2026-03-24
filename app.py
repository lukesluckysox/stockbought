# app.py
import datetime as dt
import math

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

LOOKBACK_MONTHS = 3  # used for returns & sentiment proxy

# init watchlist in session_state
if "watchlist" not in st.session_state:
    st.session_state.watchlist = []  # list of tickers (strings)

# ============================================================
# DATA FETCHING
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
            last_price = info.get("currentPrice") or info.get("regularMarketPrice")
            name = info.get("shortName") or info.get("longName") or t
        except Exception:
            last_price = None
            name = t
        rows.append({"ticker": t, "name": name, "price": last_price})
    return pd.DataFrame(rows)

def compute_return_and_sentiment(hist, tickers):
    rows = []
    for t in tickers:
        try:
            series = hist[t]["Close"] if ("Close" in hist[t]) else hist["Close"][t]
            if len(series) < 2:
                ret_pct = 0.0
            else:
                ret_pct = (series.iloc[-1] / series.iloc[0] - 1) * 100.0
        except Exception:
            ret_pct = 0.0

        # Simple price-based sentiment proxy
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

        rows.append({"ticker": t, "change_pct": ret_pct, "sentiment": sent})
    return pd.DataFrame(rows)

def build_universe_df(extra_watchlist=None):
    if extra_watchlist is None:
        extra_watchlist = []
    tickers = sorted(set(UNIVERSE_TICKERS + extra_watchlist))
    hist = fetch_stock_history(tickers, months=LOOKBACK_MONTHS)
    info_df = fetch_stock_info(tickers)
    perf_df = compute_return_and_sentiment(hist, tickers)
    df = info_df.merge(perf_df, on="ticker", how="left")
    return df

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
    return (mean_sent + 1) * 50.0  # -1..1 -> 0..100

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
# UI HELPERS
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

    price_str = f"${price:.2f}" if price is not None else "N/A"

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
              <div style="font-weight:600;font-size:14px;">{row['ticker']}</div>
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

def render_group(title: str, df_group: pd.DataFrame):
    st.subheader(title)
    if df_group.empty:
        st.write("No data.")
        return
    for _, row in df_group.iterrows():
        render_tile(row)

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

    # Allow user to adjust lookback
    global LOOKBACK_MONTHS
    LOOKBACK_MONTHS = months

    if refresh:
        fetch_stock_history.clear()
        fetch_stock_info.clear()

    with st.spinner("Loading data from Yahoo Finance..."):
        df = build_universe_df(extra_watchlist=st.session_state.watchlist)

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
