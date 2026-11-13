"""Prepare and publish a complete ProxyScrape check in GitHub Actions."""

import argparse
import json
import os
import subprocess
from collections import Counter
from datetime import datetime, timezone
from math import ceil
from pathlib import Path

import prox


def prepare(args):
    if args.limit < 0:
        raise ValueError("سقف نمونه باید نامنفی باشد")
    started = datetime.now(timezone.utc)
    prox.require_curl()
    sources = Path(__file__).with_name("sources.json")
    publishers, candidates, stats = prox.collect(prox.load_feeds(sources))
    selected = prox.select_candidates(publishers, candidates, args.limit, started)
    selected.sort(key=lambda proxy: proxy.url)
    count = min(20, ceil(len(selected) / 5000))
    args.plan.mkdir(parents=True, exist_ok=True)
    sizes = []
    for index in range(count):
        proxies = selected[index::count]
        sizes.append(len(proxies))
        (args.plan / f"batch-{index}.txt").write_text(
            "".join(f"{proxy.url}\n" for proxy in proxies), encoding="utf-8"
        )
    prox.json_file(args.plan / "plan.json", {
        "sizes": sizes,
        "started_at_utc": started.isoformat(timespec="seconds"),
        **stats,
    })
    with args.github_output.open("a", encoding="utf-8") as output:
        print(f"batches={json.dumps(list(range(count)))}", file=output)
    print(f"{len(selected):,} آدرس در {count} بسته برای تست آماده شد.")


def merge(args):
    plan = json.loads((args.plan / "plan.json").read_text(encoding="utf-8"))
    failures = Counter()
    durations = []
    working = set()
    tested = 0
    for index, size in enumerate(plan["sizes"]):
        candidates = set((args.plan / f"batch-{index}.txt").read_text(encoding="utf-8").splitlines())
        stats = json.loads((args.reports / f"stats-{index}.json").read_text(encoding="utf-8"))
        found = (args.reports / f"working-{index}.txt").read_text(encoding="utf-8").splitlines()
        if (
            len(candidates) != size
            or stats["checked"] != size
            or stats["statuses"].get("working", 0) + stats["statuses"].get("failed", 0) != size
            or len(found) != stats["exported"]
            or len(found) != len(set(found))
            or not candidates.issuperset(found)
            or not working.isdisjoint(found)
        ):
            raise ValueError(f"Invalid or incomplete result for batch {index}")
        working.update(found)
        tested += size
        failures.update(stats["failure_reasons"])
        durations.append(round(stats["seconds"], 2))

    proxies = []
    for line in sorted(working):
        proxy = prox.parse_proxy(line)
        if proxy is None:
            raise ValueError(f"Invalid proxy in check output: {line}")
        proxies.append(proxy)
    started = datetime.fromisoformat(plan["started_at_utc"])
    prox.require_curl()
    database, source = prox.load_country_database(started, args.country_db)
    prox.publish_snapshot(args.output, proxies, database, {
        "collection_mode": "verified",
        "started_at_utc": plan["started_at_utc"],
        "discovered_candidates": plan["discovered_candidates"],
        "tested_candidates": tested,
        "working_proxies": len(proxies),
        "country_database": {"source": source, "credit": "IP Geolocation by DB-IP"},
        "sources": plan["sources"],
        "check_failure_reasons": dict(failures),
        "check_batch_seconds": durations,
    })
    feeds = Counter(source["status"] for source in plan["sources"])
    print(f"{len(proxies):,} پروکسی تأییدشده از {tested:,} آدرس تست‌شده.")
    if "GITHUB_STEP_SUMMARY" in os.environ:
        with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8") as summary:
            print("## نتیجهٔ تست ProxyScrape", file=summary)
            print(f"- آدرس‌های یکتای گردآوری‌شده: {plan['discovered_candidates']:,}", file=summary)
            print(f"- آدرس‌های تست‌شده: {tested:,}", file=summary)
            print(f"- پروکسی‌های تأییدشده: {len(proxies):,}", file=summary)
            print(f"- بسته‌ها: {len(durations)} | کندترین بسته: {max(durations):.1f} ثانیه", file=summary)
            print(f"- فیدهای دارای آدرس: {feeds['ok']:,}", file=summary)
            print(f"- فیدهای خالی: {feeds['empty']:,}", file=summary)
            print(f"- خطاهای دانلود: {feeds['download_error']:,} | خطاهای قالب: {feeds['parse_error']:,}", file=summary)
            for source in plan["sources"]:
                if source["error"]:
                    print(f"  - {source['publisher']} — {source['url']} — {source['error']}", file=summary)
    print(f"::notice title=Proxy Atlas results::tested={tested}; working={len(proxies)}; "
          f"batches={len(durations)}; slowest_check_seconds={max(durations):.2f}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(required=True)
    prepare_parser = commands.add_parser("prepare")
    prepare_parser.add_argument("plan", type=Path)
    prepare_parser.add_argument("--limit", type=int, default=0)
    prepare_parser.add_argument("--github-output", type=Path, required=True)
    prepare_parser.set_defaults(run=prepare)
    merge_parser = commands.add_parser("merge")
    merge_parser.add_argument("plan", type=Path)
    merge_parser.add_argument("reports", type=Path)
    merge_parser.add_argument("output", type=Path)
    merge_parser.add_argument("--country-db", type=Path)
    merge_parser.set_defaults(run=merge)
    args = parser.parse_args()
    try:
        args.run(args)
    except (ValueError, OSError, EOFError, KeyError, TypeError, subprocess.SubprocessError) as error:
        message = str(error).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        if os.environ.get("GITHUB_ACTIONS") == "true":
            print(f"::error::{message}", flush=True)
        parser.exit(1, f"Proxy Atlas: {error}\n")


if __name__ == "__main__":
    main()
