# app.py
import datetime as dt
import math
import zoneinfo

import pandas as pd
import streamlit as st
import yfinance as yf
from streamlit_autorefresh import st_autorefresh

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

INDEX_TICKERS = {
    "^GSPC": "S&P 500",
    "^DJI": "Dow Jones",
    "^IXIC": "NASDAQ",
    "^RUT": "Russell 2000",
    "^VIX": "VIX",
}

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

ALLOCATION_MODEL = {
    "US Stocks / Tech": 30,
    "Index Funds (S&P, Total Market)": 25,
    "International / Emerging": 15,
    "Bonds / Fixed Income": 15,
    "Crypto / Alternatives": 10,
    "Cash / Money Market": 5,
}

ALLOCATION_COLORS = [
    "#6366f1", "#22c55e", "#f59e0b",
    "#3b82f6", "#f97316", "#94a3b8",
]

DEFAULT_LOOKBACK_WEEKS = 12

NYSE_TZ = zoneinfo.ZoneInfo("America/New_York")

if "watchlist" not in st.session_state:
    st.session_state.watchlist = []
if "selected_ticker" not in st.session_state:
    st.session_state.selected_ticker = None
if "selected_etf" not in st.session_state:
    st.session_state.selected_etf = None


# ============================================================
# NYSE CLOCK (LIVE TICKING)
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
        return False, "CLOSED (Weekend)", next_open - now

    if now < today_open:
        return False, "PRE-MARKET", today_open - now

    if now < today_close:
        return True, "OPEN", today_close - now

    if weekday == 4:
        next_open = (now + dt.timedelta(days=3)).replace(
            hour=9, minute=30, second=0, microsecond=0
        )
    else:
        next_open = (now + dt.timedelta(days=1)).replace(
            hour=9, minute=30, second=0, microsecond=0
        )
    return False, "AFTER-HOURS", next_open - now


def format_td(td):
    total = int(td.total_seconds())
    if total < 0:
        return "00h 00m 00s"
    h, r = divmod(total, 3600)
    m, s = divmod(r, 60)
    return f"{h:02d}h {m:02d}m {s:02d}s"


def render_nyse_clock():
    is_open, status, delta = get_nyse_status()
    now_et = dt.datetime.now(NYSE_TZ).strftime("%I:%M:%S %p ET")
    countdown = format_td(delta)

    dot_color = "#22c55e" if is_open else "#ef4444"
    cd_label = "Closes in" if is_open else "Opens in"

    st.markdown(
        f'<div style="display:flex;align-items:center;gap:24px;padding:10px 16px;'
        f'background:#0f172a;border:1px solid #1e293b;border-radius:12px;'
        f'margin-bottom:12px;flex-wrap:wrap;">'
        f'<div style="display:flex;align-items:center;gap:8px;">'
        f'<span style="display:inline-block;width:10px;height:10px;border-radius:50%;'
        f'background:{dot_color};"></span>'
        f'<span style="font-weight:700;font-size:15px;">NYSE: {status}</span>'
        f'</div>'
        f'<div style="font-size:13px;color:#94a3b8;">'
        f'\U0001f550 {now_et}'
        f'</div>'
        f'<div style="font-size:13px;color:#94a3b8;">'
        f'{cd_label}: <span style="font-weight:600;color:#e2e8f0;">{countdown}</span>'
        f'</div>'
        f'</div>',
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
    cards = ""
    for d in data:
        ps = f"{d['price']:,.2f}" if d["price"] else "N/A"
        chg = d["change_pct"]
        c = "#22c55e" if chg >= 0 else "#ef4444"
        a = "\u25b2" if chg >= 0 else "\u25bc"
        cards += (
            f'<div style="flex:1;min-width:140px;background:#0f172a;border:1px solid #1e293b;'
            f'border-radius:10px;padding:10px 14px;text-align:center;">'
            f'<div style="font-size:11px;color:#94a3b8;font-weight:600;">{d["name"]}</div>'
            f'<div style="font-size:18px;font-weight:700;margin:4px 0;">{ps}</div>'
            f'<div style="font-size:12px;color:{c};font-weight:600;">{a} {chg:+.2f}%</div>'
            f'</div>'
        )
    st.markdown(
        f'<div style="display:flex;gap:10px;margin-bottom:16px;flex-wrap:wrap;">{cards}</div>',
        unsafe_allow_html=True,
    )


# ============================================================
# LEGEND
# ============================================================

def render_legend():
    with st.expander("\U0001f4d6 How to Read This Dashboard", expanded=False):
        c1, c2, c3 = st.columns(3)

        with c1:
            st.markdown("**Sentiment Score (-1.0 to +1.0)**")
            st.markdown(
                "Based on each ticker's price return over the selected lookback "
                "period, used as a proxy for market sentiment."
            )
            st.markdown(
                '<span style="padding:2px 8px;border-radius:999px;background:#16a34a;'
                'color:white;font-size:12px;font-weight:600;">Strong Bullish '
                '(+0.60 to +1.00)</span> &nbsp; Return &ge; +30%',
                unsafe_allow_html=True,
            )
            st.markdown(
                '<span style="padding:2px 8px;border-radius:999px;background:#16a34a;'
                'color:white;font-size:12px;font-weight:600;">Bullish '
                '(+0.20 to +0.59)</span> &nbsp; Return +5% to +29%',
                unsafe_allow_html=True,
            )
            st.markdown(
                '<span style="padding:2px 8px;border-radius:999px;background:#eab308;'
                'color:white;font-size:12px;font-weight:600;">Neutral '
                '(-0.19 to +0.19)</span> &nbsp; Return -5% to +5%',
                unsafe_allow_html=True,
            )
            st.markdown(
                '<span style="padding:2px 8px;border-radius:999px;background:#dc2626;'
                'color:white;font-size:12px;font-weight:600;">Bearish '
                '(-0.20 to -0.59)</span> &nbsp; Return -5% to -29%',
                unsafe_allow_html=True,
            )
            st.markdown(
                '<span style="padding:2px 8px;border-radius:999px;background:#dc2626;'
                'color:white;font-size:12px;font-weight:600;">Strong Bearish '
                '(-0.60 to -1.00)</span> &nbsp; Return &le; -30%',
                unsafe_allow_html=True,
            )

        with c2:
            st.markdown("**Overall Market Sentiment (0 &ndash; 100)**")
            st.markdown(
                "The average sentiment across all tracked tickers, "
                "mapped to a 0&ndash;100 scale."
            )
            st.markdown(
                '\U0001f534 **<span style="color:#ef4444;">0 &ndash; 35</span>** '
                "&mdash; Market leaning bearish",
                unsafe_allow_html=True,
            )
            st.markdown(
                '\U0001f7e1 **<span style="color:#eab308;">35 &ndash; 65</span>** '
                "&mdash; Market neutral / mixed",
                unsafe_allow_html=True,
            )
            st.markdown(
                '\U0001f7e2 **<span style="color:#22c55e;">65 &ndash; 100</span>** '
                "&mdash; Market leaning bullish",
                unsafe_allow_html=True,
            )
            st.caption("The arrow on the gradient bar marks the current position.")

        with c3:
            st.markdown("**Dashboard Columns**")
            st.markdown("**Blue Chips** &mdash; Top 10 large-cap stalwarts")
            st.markdown("**Underperformers** &mdash; 10 worst returns")
            st.markdown("**Most Bullish** &mdash; 10 highest sentiment scores")
            st.markdown("**Most Bearish** &mdash; 10 lowest sentiment scores")
            st.markdown("**Watchlist** &mdash; Your personal tickers (add via sidebar)")
            st.caption("Click the \U0001f4c8 Chart button on any tile to view its price chart.")


# ============================================================
# PIE CHART
# ============================================================

def render_allocation_pie():
    categories = list(ALLOCATION_MODEL.keys())
    values = list(ALLOCATION_MODEL.values())
    colors = ALLOCATION_COLORS
    total = sum(values)

    slices = ""
    legend = ""
    cum = 0

    for i, (cat, val) in enumerate(zip(categories, values)):
        sa = (cum / total) * 360
        ea = ((cum + val) / total) * 360
        cum += val
        la = 1 if (ea - sa) > 180 else 0
        sr = math.radians(sa - 90)
        er = math.radians(ea - 90)
        x1 = 100 + 80 * math.cos(sr)
        y1 = 100 + 80 * math.sin(sr)
        x2 = 100 + 80 * math.cos(er)
        y2 = 100 + 80 * math.sin(er)
        slices += (
            f'<path d="M100,100 L{x1:.1f},{y1:.1f} A80,80 0 {la},1 '
            f'{x2:.1f},{y2:.1f} Z" fill="{colors[i]}" stroke="#1e293b" stroke-width="1"/>'
        )
        legend += (
            f'<div style="display:flex;align-items:center;gap:6px;margin-bottom:4px;">'
            f'<span style="display:inline-block;width:12px;height:12px;border-radius:3px;'
            f'background:{colors[i]};flex-shrink:0;"></span>'
            f'<span style="font-size:12px;color:#e2e8f0;">{cat}</span>'
            f'<span style="font-size:12px;color:#94a3b8;margin-left:auto;'
            f'font-weight:600;">{val}%</span></div>'
        )

    st.markdown(
        f'<div style="background:#0f172a;border:1px solid #1e293b;border-radius:16px;'
        f'padding:16px;margin-bottom:16px;">'
        f'<div style="font-weight:700;font-size:15px;margin-bottom:4px;">'
        f'\U0001f4ca Sample Portfolio Allocation</div>'
        f'<div style="font-size:11px;color:#64748b;margin-bottom:12px;">'
        f'\u26a0\ufe0f Educational reference only \u2014 NOT financial advice. '
        f'Consult a licensed advisor.</div>'
        f'<div style="display:flex;align-items:center;gap:24px;flex-wrap:wrap;">'
        f'<div><svg width="200" height="200" viewBox="0 0 200 200">'
        f'{slices}'
        f'<circle cx="100" cy="100" r="40" fill="#0f172a"/>'
        f'<text x="100" y="96" text-anchor="middle" fill="#e2e8f0" '
        f'font-size="11" font-weight="600">Diversified</text>'
        f'<text x="100" y="112" text-anchor="middle" fill="#94a3b8" '
        f'font-size="10">Portfolio</text></svg></div>'
        f'<div style="flex:1;min-width:180px;">{legend}</div>'
        f'</div></div>',
        unsafe_allow_html=True,
    )


# ============================================================
# TOP 10 INDEXES / ETFs
# ============================================================

@st.cache_data(ttl=120)
def fetch_etf_data():
    rows = []
    tickers_list = list(TOP_INDEX_ETF_TICKERS.keys())
    end = dt.datetime.today()
    start = end - dt.timedelta(days=90)
    hist = yf.download(
        tickers=tickers_list, start=start, end=end,
        auto_adjust=True, progress=False, group_by="ticker", threads=True,
    )
    for sym in tickers_list:
        name = TOP_INDEX_ETF_TICKERS[sym]
        try:
            t = yf.Ticker(sym)
            info = t.info or {}
            price = (
                info.get("currentPrice") or info.get("regularMarketPrice")
                or info.get("regularMarketPreviousClose") or info.get("previousClose")
            )
        except Exception:
            price = None
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
            if price is None and len(series) > 0:
                price = series.iloc[-1]
                if hasattr(price, "item"):
                    price = price.item()
        except Exception:
            change_pct = 0.0
        rows.append({
            "ticker": sym, "name": name, "price": price,
            "change_pct": float(change_pct) if change_pct else 0.0,
        })
    return rows, hist


def render_etf_section():
    st.markdown("### \U0001f3db\ufe0f Top 10 Indexes & ETFs")
    st.caption("Click any ETF to view its 3-month chart.")
    etf_data, etf_hist = fetch_etf_data()

    if st.session_state.selected_etf:
        render_etf_chart(st.session_state.selected_etf, etf_data, etf_hist)

    for row_start in range(0, len(etf_data), 5):
        cols = st.columns(5)
        for i, col in enumerate(cols):
            idx = row_start + i
            if idx >= len(etf_data):
                break
            d = etf_data[idx]
            with col:
                ps = f"${d['price']:.2f}" if d["price"] else "N/A"
                chg = d["change_pct"]
                c = "#22c55e" if chg >= 0 else "#ef4444"
                a = "\u25b2" if chg >= 0 else "\u25bc"
                st.markdown(
                    f'<div style="background:#111827;border:1px solid #1f2937;'
                    f'border-radius:10px;padding:10px;text-align:center;margin-bottom:4px;">'
                    f'<div style="font-weight:700;font-size:14px;">{d["ticker"]}</div>'
                    f'<div style="font-size:11px;color:#94a3b8;margin-bottom:4px;'
                    f'white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">'
                    f'{d["name"]}</div>'
                    f'<div style="font-size:16px;font-weight:700;">{ps}</div>'
                    f'<div style="font-size:12px;color:{c};font-weight:600;">'
                    f'{a} {chg:+.2f}% (3M)</div></div>',
                    unsafe_allow_html=True,
                )
                if st.button("\U0001f4c8 Chart", key=f"etf_chart_{d['ticker']}"):
                    st.session_state.selected_etf = d["ticker"]
                    st.rerun()


def render_etf_chart(ticker, etf_data, etf_hist):
    entry = next((d for d in etf_data if d["ticker"] == ticker), None)
    if not entry:
        st.session_state.selected_etf = None
        return
    ps = f"${entry['price']:.2f}" if entry["price"] else "N/A"
    chg = entry["change_pct"]
    c = "#22c55e" if chg >= 0 else "#ef4444"
    try:
        tl = list(TOP_INDEX_ETF_TICKERS.keys())
        if len(tl) > 1:
            series = etf_hist[ticker]["Close"] if ("Close" in etf_hist[ticker]) else etf_hist["Close"][ticker]
        else:
            series = etf_hist["Close"]
        chart_data = series.dropna().reset_index()
        chart_data.columns = ["Date", "Close"]
    except Exception:
        chart_data = pd.DataFrame()

    st.markdown(
        f'<div style="background:#0f172a;border:1px solid #1e293b;border-radius:16px;'
        f'padding:20px;margin:8px 0;">'
        f'<div style="display:flex;justify-content:space-between;align-items:center;">'
        f'<div><span style="font-size:22px;font-weight:700;">{ticker}</span>'
        f'<span style="font-size:14px;color:#94a3b8;margin-left:8px;">{entry["name"]}</span></div>'
        f'<div style="text-align:right;">'
        f'<div style="font-size:20px;font-weight:700;">{ps}</div>'
        f'<div style="font-size:13px;color:{c};">{chg:+.2f}% (3M)</div>'
        f'</div></div></div>',
        unsafe_allow_html=True,
    )
    if not chart_data.empty:
        st.line_chart(chart_data.set_index("Date")["Close"], use_container_width=True)
    else:
        st.write("No chart data available.")
    if st.button("\u2715 Close chart", key="close_etf_chart"):
        st.session_state.selected_etf = None
        st.rerun()


# ============================================================
# DATA FETCHING - STOCKS
# ============================================================

@st.cache_data(ttl=60)
def fetch_stock_history(tickers, weeks: int = 12):
    end = dt.datetime.today()
    start = end - dt.timedelta(weeks=weeks)
    data = yf.download(
        tickers=tickers, start=start, end=end,
        auto_adjust=True, progress=False, group_by="ticker", threads=True,
    )
    return data


@st.cache_data(ttl=60)
def fetch_stock_info(tickers):
    rows = []
    for t in tickers:
        try:
            tk = yf.Ticker(t)
            info = tk.info or {}
            lp = (
                info.get("currentPrice") or info.get("regularMarketPrice")
                or info.get("regularMarketPreviousClose") or info.get("previousClose")
            )
            name = info.get("shortName") or info.get("longName") or t
        except Exception:
            lp = None
            name = t
        rows.append({"ticker": t, "name": name, "price": lp})
    return pd.DataFrame(rows)


def get_price_from_history(hist, ticker):
    try:
        series = hist[ticker]["Close"] if ("Close" in hist[ticker]) else hist["Close"][ticker]
        if len(series) > 0:
            val = series.iloc[-1]
            return val.item() if hasattr(val, "item") else float(val)
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


def build_universe_df(extra_watchlist=None, weeks=12):
    if extra_watchlist is None:
        extra_watchlist = []
    tickers = sorted(set(UNIVERSE_TICKERS + extra_watchlist))
    hist = fetch_stock_history(tickers, weeks=weeks)
    info_df = fetch_stock_info(tickers)
    perf_df = compute_return_and_sentiment(hist, tickers)
    df = info_df.merge(perf_df, on="ticker", how="left")
    for idx, row in df.iterrows():
        if row["price"] is None or (isinstance(row["price"], float) and math.isnan(row["price"])):
            fb = get_price_from_history(hist, row["ticker"])
            if fb is not None:
                df.at[idx, "price"] = fb
    return df, hist


# ============================================================
# CLASSIFICATION & METRICS
# ============================================================

def classify_groups(df):
    blue = df[df["ticker"].isin(BLUE_CHIP_TICKERS)].copy()
    uni = df[df["ticker"].isin(UNIVERSE_TICKERS)]
    under = uni.sort_values("change_pct").head(10).copy()
    bullish = uni.sort_values("sentiment", ascending=False).head(10).copy()
    bearish = uni.sort_values("sentiment").head(10).copy()
    return blue, under, bullish, bearish


def compute_overall_sentiment(df):
    if df.empty:
        return 50.0
    return (df["sentiment"].mean() + 1) * 50.0


def sentiment_color(score):
    if score >= 0.3:
        return "#16a34a"
    if score <= -0.3:
        return "#dc2626"
    return "#eab308"


def sentiment_label(score):
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
# UI HELPERS - STOCKS
# ============================================================

def overall_bar(sent_0_100, weeks):
    lc, mc, rc = "#dc2626", "#eab308", "#16a34a"
    pos = max(0, min(100, sent_0_100))
    st.markdown(
        f'<div style="width:100%;padding:8px 0;">'
        f'<div style="font-weight:600;margin-bottom:4px;">'
        f'Overall Market Sentiment ({weeks}W, price-based): {pos:.1f}</div>'
        f'<div style="position:relative;height:24px;border-radius:999px;'
        f'background:linear-gradient(90deg,{lc},{mc},{rc});">'
        f'<div style="position:absolute;left:{pos}%;top:-4px;transform:translateX(-50%);'
        f'width:0;height:0;border-left:6px solid transparent;'
        f'border-right:6px solid transparent;border-bottom:8px solid #111;"></div>'
        f'</div></div>',
        unsafe_allow_html=True,
    )


def _format_price(price):
    if price is not None and not (isinstance(price, float) and math.isnan(price)):
        return f"${price:.2f}"
    return "N/A"


def render_clickable_tile(row, weeks, unique_key):
    """Render a ticker tile as a clickable selectbox-style element."""
    score = row["sentiment"]
    bg = sentiment_color(score)
    label = sentiment_label(score)
    change = row["change_pct"]
    ticker = row["ticker"]
    ps = _format_price(row["price"])
    cc = "#22c55e" if change >= 0 else "#ef4444"

    # Use a container + button styled to look like the full tile
    clicked = st.button(
        f"{ticker}  |  {row['name']}  |  {ps}  |  {change:+.2f}% ({weeks}W)  |  {label}",
        key=unique_key,
        use_container_width=True,
    )
    # Also render the styled visual tile above the button area
    st.markdown(
        f'<div style="border-radius:12px;padding:10px 12px;margin-top:-52px;margin-bottom:8px;'
        f'background-color:#111827;border:1px solid #1f2937;pointer-events:none;position:relative;z-index:1;">'
        f'<div style="display:flex;justify-content:space-between;align-items:center;">'
        f'<div>'
        f'<div style="font-weight:600;font-size:14px;">{ticker}</div>'
        f'<div style="font-size:12px;color:#9ca3af;">{row["name"]}</div></div>'
        f'<div style="text-align:right;">'
        f'<div style="font-weight:600;">{ps}</div>'
        f'<div style="font-size:12px;color:{cc};">{change:+.2f}% ({weeks}W)</div>'
        f'</div></div>'
        f'<div style="margin-top:6px;font-size:12px;">'
        f'<span style="padding:2px 6px;border-radius:999px;background-color:{bg};'
        f'color:white;font-size:11px;">{label} ({score:+.2f})</span>'
        f'</div></div>',
        unsafe_allow_html=True,
    )
    return clicked


def render_highlight_tile(row, weeks, category_label):
    """Render a prominent highlight card for the #1 in each category."""
    score = row["sentiment"]
    bg = sentiment_color(score)
    label = sentiment_label(score)
    change = row["change_pct"]
    ticker = row["ticker"]
    ps = _format_price(row["price"])
    cc = "#22c55e" if change >= 0 else "#ef4444"

    st.markdown(
        f'<div style="background:#0f172a;border:1px solid #1e293b;border-radius:12px;'
        f'padding:12px 16px;">'
        f'<div style="font-size:11px;color:#64748b;font-weight:600;'
        f'text-transform:uppercase;letter-spacing:0.5px;margin-bottom:6px;">'
        f'\U0001f3c6 Top {category_label}</div>'
        f'<div style="display:flex;justify-content:space-between;align-items:center;">'
        f'<div>'
        f'<div style="font-weight:700;font-size:18px;">{ticker}</div>'
        f'<div style="font-size:12px;color:#94a3b8;">{row["name"]}</div></div>'
        f'<div style="text-align:right;">'
        f'<div style="font-weight:700;font-size:18px;">{ps}</div>'
        f'<div style="font-size:13px;color:{cc};font-weight:600;">{change:+.2f}% ({weeks}W)</div>'
        f'</div></div>'
        f'<div style="margin-top:6px;">'
        f'<span style="padding:3px 8px;border-radius:999px;background-color:{bg};'
        f'color:white;font-size:12px;font-weight:600;">{label} ({score:+.2f})</span>'
        f'</div></div>',
        unsafe_allow_html=True,
    )


def render_expandable_group(title, df_group, weeks, group_key):
    """Render a group as an expandable section, max 10 tickers, clickable tiles."""
    limited = df_group.head(10)
    count = len(limited)
    with st.expander(f"{title} ({count})", expanded=False):
        if limited.empty:
            st.write("No data.")
            return
        for i, (_, row) in enumerate(limited.iterrows()):
            ukey = f"tile_{group_key}_{row['ticker']}_{i}"
            clicked = render_clickable_tile(row, weeks, ukey)
            if clicked:
                st.session_state.selected_ticker = row["ticker"]
                st.rerun()


def render_chart_dialog(hist, df, weeks):
    ticker = st.session_state.selected_ticker
    if ticker is None:
        return
    r = df[df["ticker"] == ticker]
    if r.empty:
        st.session_state.selected_ticker = None
        return
    r = r.iloc[0]
    ps = _format_price(r["price"])
    cc = "#22c55e" if r["change_pct"] >= 0 else "#ef4444"
    try:
        series = hist[ticker]["Close"] if ("Close" in hist[ticker]) else hist["Close"][ticker]
        chart_data = series.dropna().reset_index()
        chart_data.columns = ["Date", "Close"]
    except Exception:
        chart_data = pd.DataFrame()

    st.markdown("---")
    st.markdown(
        f'<div style="background:#0f172a;border:1px solid #1e293b;border-radius:16px;'
        f'padding:20px;margin:8px 0;">'
        f'<div style="display:flex;justify-content:space-between;align-items:center;">'
        f'<div><span style="font-size:22px;font-weight:700;">{ticker}</span>'
        f'<span style="font-size:14px;color:#94a3b8;margin-left:8px;">{r["name"]}</span></div>'
        f'<div style="text-align:right;">'
        f'<div style="font-size:20px;font-weight:700;">{ps}</div>'
        f'<div style="font-size:13px;color:{cc};">{r["change_pct"]:+.2f}% ({weeks}W)</div>'
        f'</div></div></div>',
        unsafe_allow_html=True,
    )
    if not chart_data.empty:
        st.line_chart(chart_data.set_index("Date")["Close"], use_container_width=True)
    else:
        st.write("No chart data available.")
    if st.button("\u2715 Close chart", key="close_stock_chart"):
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

    # Auto-refresh every 1 second for the live clock
    st_autorefresh(interval=1000, limit=None, key="clock_refresh")

    st.title("\U0001f4ca Bullish / Bearish Stock Dashboard (Live from Yahoo Finance)")
    st.caption("No logins, no API key \u2014 using free yfinance data as a proxy for sentiment.")

    # 1. NYSE Clock (ticks every second)
    render_nyse_clock()

    # 2. Major Indexes row
    render_index_row()

    # 3. Legend
    render_legend()

    # 4. Pie chart + Top 10 ETFs
    pie_col, etf_col = st.columns([1, 2])
    with pie_col:
        render_allocation_pie()
    with etf_col:
        render_etf_section()

    st.markdown("---")

    # Sidebar
    with st.sidebar:
        st.header("Controls")
        weeks = st.slider("Lookback (weeks)", 1, 52, value=DEFAULT_LOOKBACK_WEEKS)
        refresh = st.button("\U0001f501 Refresh data")
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
        df, hist = build_universe_df(
            extra_watchlist=st.session_state.watchlist, weeks=weeks
        )

    blue, under, bullish, bearish = classify_groups(df)
    wl_df = df[df["ticker"].isin(st.session_state.watchlist)].copy()
    overall = compute_overall_sentiment(df)
    overall_bar(overall, weeks)

    # --- Top #1 from each category as permanent highlight cards ---
    st.markdown("#### \U0001f451 Category Leaders")
    h1, h2, h3, h4, h5 = st.columns(5)
    with h1:
        if not blue.empty:
            render_highlight_tile(blue.iloc[0], weeks, "Blue Chip")
    with h2:
        if not under.empty:
            render_highlight_tile(under.iloc[0], weeks, "Underperformer")
    with h3:
        if not bullish.empty:
            render_highlight_tile(bullish.iloc[0], weeks, "Bullish")
    with h4:
        if not bearish.empty:
            render_highlight_tile(bearish.iloc[0], weeks, "Bearish")
    with h5:
        if not wl_df.empty:
            render_highlight_tile(wl_df.iloc[0], weeks, "Watchlist")
        else:
            st.markdown(
                '<div style="background:#0f172a;border:1px solid #1e293b;'
                'border-radius:12px;padding:12px 16px;text-align:center;'
                'color:#64748b;font-size:13px;">'
                'Add tickers to your watchlist via the sidebar</div>',
                unsafe_allow_html=True,
            )

    st.markdown("")

    # --- Chart dialog (if a ticker is selected) ---
    if st.session_state.selected_ticker:
        render_chart_dialog(hist, df, weeks)

    # --- Expandable groups (click any tile to see chart) ---
    render_expandable_group("Blue Chips", blue, weeks, "blue")
    render_expandable_group("Underperformers", under, weeks, "under")
    render_expandable_group("Most Bullish", bullish, weeks, "bullish")
    render_expandable_group("Most Bearish", bearish, weeks, "bearish")
    render_expandable_group("Watchlist", wl_df, weeks, "watchlist")

    with st.expander("Show raw data"):
        st.dataframe(df.sort_values("ticker").reset_index(drop=True))


if __name__ == "__main__":
    main()
