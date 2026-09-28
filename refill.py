"""[임시] 지정한 날짜들의 경제지표를 '그날 22시에 봤을 값'으로 다시 계산해 덮어쓴다.
실행 후 이 파일과 .github/workflows/refill.yml은 삭제하세요.
"""
import time
from datetime import date, timedelta

import yfinance as yf

from markets import DATA_DIR, TICKERS, expected_as_of, update_index, write_day

DATES = [
    date(2026, 9, 19),  # 토
    date(2026, 9, 20),  # 일
    date(2026, 9, 23),  # 수 (미국 값 정정)
    date(2026, 9, 26),  # 토
    date(2026, 9, 27),  # 일
]


def load_series(symbol):
    start = min(DATES) - timedelta(days=20)
    end = max(DATES) + timedelta(days=2)
    for attempt in range(1, 4):
        try:
            s = yf.Ticker(symbol).history(
                start=start.isoformat(), end=end.isoformat(), interval="1d")["Close"].dropna()
            if len(s):
                return [(ts.date(), float(v)) for ts, v in s.items()]
        except Exception as e:
            print(f"{symbol} 시도 {attempt} 실패: {e}")
        time.sleep(5)
    return []


def snapshot(series, group, target):
    cutoff = expected_as_of(group, target)
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
    series = {s: load_series(s) for _, _, s, _ in TICKERS}
    for target in DATES:
        items = [{"group": g, "name": n, "symbol": s, **snapshot(series[s], g, target)}
                 for g, n, s, _ in TICKERS]
        path = DATA_DIR / f"{target.isoformat()}.json"
        if path.exists():
            path.unlink()
        write_day(target.isoformat(), items, None)
        print(f"\n[{target}]")
        for it in items:
            print(f"  {it['name']}: {it['close']} ({it['change_pct']}%) as_of {it['as_of']}")
    update_index([d.isoformat() for d in DATES])
    print("\n완료")


if __name__ == "__main__":
    main()
