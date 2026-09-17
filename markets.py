"""평일 22시 경제지표(지수·환율·금값) → 날짜별 JSON 저장 + Discord 전송"""
import json
import os
import sys
import time
from datetime import date, datetime, timedelta
from datetime import time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
import yfinance as yf

KST = ZoneInfo("Asia/Seoul")
NY = ZoneInfo("America/New_York")
DATA_DIR = Path("data")
OLD_LOG = DATA_DIR / "log.jsonl"
NEXT_DAY_UNTIL = 7  # 이 시각(KST) 이전 실행은 전날 22시 몫의 재시도로 취급
GIVE_UP_AT = dtime(5, 0)   # 이 시각까지도 기준일이 안 맞으면 최종 확정(휴장으로 간주)

# (그룹, 표시 이름, Yahoo 티커, Discord 숫자 형식)
TICKERS = [
    ("kr", "코스피", "^KS11", "{:,.0f}"),
    ("kr", "코스닥", "^KQ11", "{:,.0f}"),
    ("us", "나스닥", "^IXIC", "{:,.0f}"),
    ("us", "S&P 500", "^GSPC", "{:,.0f}"),
    ("fx", "원/달러", "KRW=X", "{:,.0f}원"),
    ("fx", "금", "GC=F", "${:,.0f}"),
]
GROUP_OF = {t[2]: t[0] for t in TICKERS}
GROUP_LABEL = {"kr": "🇰🇷 한국", "us": "🇺🇸 미국 (전 거래일)", "fx": "💱 환율 · 금"}


def target_date(now):
    """실행이 지연돼 자정을 넘겼어도, 원래 몫이었던 날짜를 돌려준다."""
    if now.hour < NEXT_DAY_UNTIL:
        return (now - timedelta(days=1)).date()
    return now.date()


def prev_weekday(d):
    d -= timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def expected_as_of(group, today):
    """정상 거래일이라면 기대되는 기준일."""
    if group == "us":
        return prev_weekday(today)
    return today  # 코스피·코스닥·환율·금은 그날 값을 기대함


def all_as_expected(items, target):
    """모든 지표의 기준일이 기대한 날짜와 일치하는가 (재시도 여부 판단용)."""
    return all(
        it["as_of"] == expected_as_of(it["group"], target).isoformat()
        for it in items if it["close"] is not None
    )


# ---------- 수집 ----------
def fetch_one(group, symbol):
    for attempt in range(1, 4):
        try:
            closes = yf.Ticker(symbol).history(period="10d", interval="1d")["Close"].dropna()
            if group == "us":
                # 실행이 늦어져 미국 장이 열린 뒤라도, 마감된 거래일만 사용
                ny_today = datetime.now(NY).date()
                closes = closes[[ts.date() < ny_today for ts in closes.index]]
            if len(closes) >= 2:
                last, prev = float(closes.iloc[-1]), float(closes.iloc[-2])
                return {
                    "close": round(last, 2),
                    "change_pct": round((last - prev) / prev * 100, 2),
                    "as_of": closes.index[-1].date().isoformat(),
                }
        except Exception as e:
            print(f"{symbol} 시도 {attempt} 실패: {e}")
        time.sleep(5)
    return {"close": None, "change_pct": None, "as_of": None}


# ---------- 저장 ----------
def write_day(date_str, items, crawled_at):
    DATA_DIR.mkdir(exist_ok=True)
    payload = {"date": date_str, "crawled_at": crawled_at, "items": items}
    (DATA_DIR / f"{date_str}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def update_index(new_dates):
    index_path = DATA_DIR / "index.json"
    dates = json.loads(index_path.read_text()) if index_path.exists() else []
    index_path.write_text(json.dumps(sorted(set(dates) | set(new_dates)), indent=2))


def migrate_old_log():
    """예전 log.jsonl 기록을 날짜별 파일로 한 번만 변환하고 지운다 (주말 기록은 제외)."""
    if not OLD_LOG.exists():
        return
    by_date = {}
    for line in OLD_LOG.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        if date.fromisoformat(entry["date"]).weekday() >= 5:
            continue
        items = []
        for it in entry["items"]:
            d = it.get("data") or {}
            items.append({
                "group": GROUP_OF.get(it["symbol"], "fx"),
                "name": it["name"],
                "symbol": it["symbol"],
                "close": d.get("close"),
                "change_pct": d.get("change_pct"),
                "as_of": d.get("as_of"),
            })
        by_date[entry["date"]] = items  # 같은 날 여러 번 실행했으면 마지막 기록 사용
    for date_str, items in by_date.items():
        write_day(date_str, items, None)
    update_index(by_date.keys())
    OLD_LOG.unlink()
    print(f"예전 기록 {len(by_date)}일치 변환 완료")


# ---------- 전송 ----------
def discord_line(item, fmt, today):
    if item["close"] is None:
        return f"**{item['name']}**  수집 실패"
    pct = item["change_pct"]
    mark = "🔴" if pct > 0 else ("🔵" if pct < 0 else "⚪")
    line = f"{mark} **{item['name']}**  {fmt.format(item['close'])}  ({pct:+.2f}%)"
    expected = expected_as_of(item["group"], today)
    if item["as_of"] != expected.isoformat():
        as_of = date.fromisoformat(item["as_of"])
        line += f"  · 휴장, {as_of.month}/{as_of.day} 기준"
    return line


def send_discord(webhook, now, items):
    target = target_date(now)
    fmts = {t[2]: t[3] for t in TICKERS}
    blocks, current = [], None
    for it in items:
        if it["group"] != current:
            blocks.append(f"\n**{GROUP_LABEL[it['group']]}**")
            current = it["group"]
        blocks.append(discord_line(it, fmts[it["symbol"]], target))

    weekday = "월화수목금토일"[now.weekday()]
    embed = {
        "title": f"📒 오늘의 경제지표 · {now.month}/{now.day}({weekday})",
        "description": "\n".join(blocks).strip(),
        "footer": {"text": "🔴 상승  🔵 하락 · Yahoo Finance"},
        "color": 0x2F6BFF,
    }
    requests.post(webhook, json={"embeds": [embed]}, timeout=20).raise_for_status()


def main():
    migrate_old_log()

    now = datetime.now(KST)
    target = target_date(now)
    manual = os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch"

    if target.weekday() >= 5:
        print(f"[{target}] 주말 몫이라 수집하지 않아요.")
        return

    date_str = target.isoformat()
    if (DATA_DIR / f"{date_str}.json").exists():
        print(f"[{date_str}] 이미 저장됨, 종료")
        return

    items = []
    for group, name, symbol, _ in TICKERS:
        d = fetch_one(group, symbol)
        items.append({"group": group, "name": name, "symbol": symbol, **d})
        print(name, d)

    if all(it["close"] is None for it in items):
        if manual or now.time() >= GIVE_UP_AT:
            sys.exit("모든 지표 수집 실패")
        print(f"[{date_str}] 아직 데이터가 없어요, 30분 뒤 다시 시도해요.")
        return

    if not manual and now.time() < GIVE_UP_AT and not all_as_expected(items, target):
        mismatched = [it["name"] for it in items if it["close"] is not None
                      and it["as_of"] != expected_as_of(it["group"], target).isoformat()]
        print(f"[{date_str}] 기준일이 아직 안 맞아요({mismatched}), 30분 뒤 다시 시도해요.")
        return

    write_day(date_str, items, now.isoformat(timespec="seconds"))
    update_index([date_str])
    print(f"[{date_str}] 저장 완료")

    webhook = os.environ.get("DISCORD_WEBHOOK_URL")
    if webhook:
        send_discord(webhook, now, items)
        print("Discord 전송 완료")


if __name__ == "__main__":
    main()
