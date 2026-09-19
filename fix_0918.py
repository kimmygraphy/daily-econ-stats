"""[임시] 2026-09-18 기록을 다시 받아와 덮어쓴다. 실행 후 이 파일은 삭제하세요."""
from datetime import date

from markets import DATA_DIR, TICKERS, fetch_one, update_index, write_day

TARGET = date(2026, 9, 18)


def main():
    items = []
    for group, name, symbol, _ in TICKERS:
        d = fetch_one(group, symbol)
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
