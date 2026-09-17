"""매일 경제지표(지수·환율·금값)를 Discord로 전송 — 플래너 기록용"""
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
import yfinance as yf

KST = ZoneInfo("Asia/Seoul")
LOG_DIR = Path("data")

# (그룹, 표시 이름, Yahoo 티커, 숫자 형식)
TICKERS = [
    ("🇰🇷 한국 (오늘)", "코스피", "^KS11", "{:,.0f}"),
    ("🇰🇷 한국 (오늘)", "코스닥", "^KQ11", "{:,.0f}"),
    ("🇺🇸 미국 (전일)", "나스닥", "^IXIC", "{:,.0f}"),
    ("🇺🇸 미국 (전일)", "S&P 500", "^GSPC", "{:,.0f}"),
    ("💱 환율 · 금", "원/달러", "KRW=X", "{:,.0f}원"),
    ("💱 환율 · 금", "금", "GC=F", "${:,.0f}"),
]


def fetch_one(symbol):
    for attempt in range(3):
        try:
            closes = yf.Ticker(symbol).history(period="10d", interval="1d")["Close"].dropna()
            if len(closes) >= 2:
                last, prev = float(closes.iloc[-1]), float(closes.iloc[-2])
                return {
                    "close": round(last, 2),
                    "change_pct": round((last - prev) / prev * 100, 2),
                    "as_of": closes.index[-1].date().isoformat(),
                }
        except Exception as e:
            print(f"{symbol} 시도 {attempt + 1} 실패: {e}")
        time.sleep(5)
    return None


def format_line(name, fmt, d):
    if d is None:
        return f"**{name}**  수집 실패"
    pct = d["change_pct"]
    mark = "🔴" if pct > 0 else ("🔵" if pct < 0 else "⚪")
    return f"{mark} **{name}**  {fmt.format(d['close'])}  ({pct:+.2f}%)"


def main():
    now = datetime.now(KST)
    today = now.strftime("%Y-%m-%d")

    results = []
    for group, name, symbol, fmt in TICKERS:
        d = fetch_one(symbol)
        results.append((group, name, symbol, fmt, d))
        print(name, d)

    if all(r[4] is None for r in results):
        sys.exit("모든 지표 수집 실패")

    # Discord 메시지: 그룹별로 묶어서 짧게
    blocks, current = [], None
    for group, name, _, fmt, d in results:
        if group != current:
            blocks.append(f"\n**{group}**")
            current = group
        blocks.append(format_line(name, fmt, d))

    weekday = "월화수목금토일"[now.weekday()]
    embed = {
        "title": f"📒 오늘의 경제지표 · {now.month}/{now.day}({weekday})",
        "description": "\n".join(blocks).strip(),
        "footer": {"text": "🔴 상승  🔵 하락 · Yahoo Finance"},
        "color": 0x2F6BFF,
    }

    webhook = os.environ.get("DISCORD_WEBHOOK_URL")
    if webhook:
        requests.post(webhook, json={"embeds": [embed]}, timeout=20).raise_for_status()
        print("Discord 전송 완료")

    # 가벼운 실행 기록 (저장소가 60일 이상 비활성이면 GitHub이 예약 실행을 멈추기 때문)
    LOG_DIR.mkdir(exist_ok=True)
    log = {"date": today, "items": [
        {"name": n, "symbol": s, "data": d} for _, n, s, _, d in results]}
    with open(LOG_DIR / "log.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(log, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
