"""[임시] 과거 경제지표 채우기 — 실행 후 이 파일과 .github/workflows/backfill.yml은 삭제하세요.

매일 22시(KST)에 markets.py가 돌았다면 저장됐을 값을 과거 일별 종가로 재구성한다.
- 한국: 그날(휴장이면 직전 거래일) 종가
- 미국: 그날 이전의 마지막 마감 거래일 종가
- 환율·금: 그날 일봉 종가
"""
import time
from datetime import date, timedelta
from pathlib import Path

import yfinance as yf

from markets import DATA_DIR, TICKERS, update_index, write_day

START = date(2026, 9, 1)
END = date(2026, 9, 16)
OVERWRITE = False  # True면 이미 있는 날짜 파일도 다시 씀


def load_series(symbol):
    for attempt in range(1, 4):
        try:
            hist = yf.Ticker(symbol).history(
                start=(START - timedelta(days=20)).isoformat(),
                end=(END + timedelta(days=2)).isoformat(),
                interval="1d",
            )
            s = hist["Close"].dropna()
            if len(s):
                return [(ts.date(), float(v)) for ts, v in s.items()]
        except Exception as e:
            print(f"{symbol} 시도 {attempt} 실패: {e}")
        time.sleep(5)
    return []


def snapshot(series, group, d):
    if group == "us":
        past = [(x, v) for x, v in series if x < d]
    else:
        past = [(x, v) for x, v in series if x <= d]
    if len(past) < 2:
        return {"close": None, "change_pct": None, "as_of": None}
    (last_d, last), (_, prev) = past[-1], past[-2]
    return {
        "close": round(last, 2),
        "change_pct": round((last - prev) / prev * 100, 2),
        "as_of": last_d.isoformat(),
    }


def main():
    series = {}
    for _, name, symbol, _ in TICKERS:
        series[symbol] = load_series(symbol)
        print(f"{name}: 일봉 {len(series[symbol])}개")

    written, skipped = [], []
    d = START
    while d <= END:
        date_str = d.isoformat()
        if d.weekday() >= 5:
            d += timedelta(days=1)
            continue
        if not OVERWRITE and (DATA_DIR / f"{date_str}.json").exists():
            skipped.append(date_str)
            d += timedelta(days=1)
            continue

        items = [
            {"group": g, "name": n, "symbol": s, **snapshot(series[s], g, d)}
            for g, n, s, _ in TICKERS
        ]
        write_day(date_str, items, None)
        written.append(date_str)
        d += timedelta(days=1)

    update_index(written)
    print(f"새로 저장: {len(written)}일 {written}")
    print(f"이미 있어서 건너뜀: {skipped}")


if __name__ == "__main__":
    main()
