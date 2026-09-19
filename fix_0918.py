"""[임시] 2026-09-18 기록을 '그날 저녁 22시 기준으로 봤을 값'에 맞게 다시 계산해 덮어쓴다.
날짜가 하루 이상 지난 뒤 실행해도, 미래 시세가 섞이지 않도록 날짜별 시계열에서 골라 쓴다.
실행 후 이 파일은 삭제하세요.
"""
import time
from datetime import date, timedelta

import yfinance as yf

from markets import DATA_DIR, TICKERS, expected_as_of, update_index, write_day

TARGET = date(2026, 9, 18)


def load_series(symbol):
    for attempt in range(1, 4):
        try:
            hist = yf.Ticker(symbol).history(
                start=(TARGET - timedelta(days=20)).isoformat(),
                end=(TARGET + timedelta(days=2)).isoformat(),
                interval="1d",
            )
            s = hist["Close"].dropna()
            if len(s):
                return [(ts.date(), float(v)) for ts, v in s.items()]
        except Exception as e:
            print(f"{symbol} 시도 {attempt} 실패: {e}")
        time.sleep(5)
    return []


def snapshot(series, group):
    """target 시점에 실제로 봤을 값만 골라, close/전일대비/기준일을 계산한다."""
    cutoff = expected_as_of(group, TARGET)  # kr/fx: target 당일, us: target 이전 평일
    past = [(d, v) for d, v in series if d <= cutoff]
    if len(past) < 2:
        return {"close": None, "change_pct": None, "as_of": None}
    (last_d, last), (_, prev) = past[-1], past[-2]
    return {
        "close": round(last, 2),
        "change_pct": round((last - prev) / prev * 100, 2),
        "as_of": last_d.isoformat(),
    }


def main():
    items = []
    for group, name, symbol, _ in TICKERS:
        series = load_series(symbol)
        d = snapshot(series, group)
        items.append({"group": group, "name": name, "symbol": symbol, **d})
        print(name, d)

    date_str = TARGET.isoformat()
    old = DATA_DIR / f"{date_str}.json"
    if old.exists():
        old.unlink()

    write_day(date_str, items, None)
    update_index([date_str])
    print(f"[{date_str}] 다시 저장 완료")


if __name__ == "__main__":
    main()
