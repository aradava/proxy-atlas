import argparse
import json
import subprocess
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from math import ceil
from pathlib import Path
from uuid import uuid4

import prox


TARGET_SHARD_SIZE = 15_000
MAX_MATRIX_JOBS = 256
COUNTRY_FILE = "country.csv.gz"


def prepare(args):
    if args.limit < 0:
        raise ValueError("مقدار limit باید نامنفی باشد")
    prox.require_curl()
    started = datetime.now(timezone.utc)
    publishers, candidates, collection_stats = prox.collect(prox.load_feeds(args.sources), args.previous)
    selected = prox.select_candidates(publishers, candidates, args.limit, started)
    shard_count = min(ceil(len(selected) / TARGET_SHARD_SIZE), MAX_MATRIX_JOBS)

    args.plan.mkdir(parents=True)
    _, database_source = prox.load_country_database(started, None, save_to=args.plan / COUNTRY_FILE)
    sizes = []
    for shard in range(shard_count):
        proxies = selected[shard::shard_count]
        sizes.append(len(proxies))
        with (args.plan / f"{shard}.txt").open("w", encoding="utf-8", newline="\n") as file:
            file.writelines(f"{proxy.url}\n" for proxy in proxies)
    prox.json_file(args.plan / "plan.json", {
        "id": uuid4().hex,
        "shard_sizes": sizes,
        "manifest": {
            "started_at_utc": started.isoformat(timespec="seconds"),
            "country_database": {"source": database_source, "credit": "IP Geolocation by DB-IP"},
            **collection_stats,
        },
    })
    with args.github_output.open("a", encoding="utf-8") as file:
        print(f"shards={json.dumps(list(range(shard_count)))}", file=file)
    print(f"{len(selected):,} نامزد یکتا در {shard_count:,} بخش آماده شد", flush=True)


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def check(args):
    prox.require_curl()
    plan = read_json(args.plan / "plan.json")
    if not 0 <= args.shard < len(plan["shard_sizes"]):
        raise ValueError(f"Invalid shard: {args.shard}")
    with (args.plan / f"{args.shard}.txt").open(encoding="utf-8") as file:
        proxies = [prox.parse_proxy(line.rstrip("\n")) for line in file]
    if None in proxies or len(set(proxies)) != len(proxies) or len(proxies) != plan["shard_sizes"][args.shard]:
        raise ValueError(f"Invalid candidate list for shard {args.shard}")

    prox.check_targets(prox.DEFAULT_TIMEOUT)
    started = datetime.fromisoformat(plan["manifest"]["started_at_utc"])
    database, _ = prox.load_country_database(started, args.plan / COUNTRY_FILE)
    checks = prox.check_all(proxies, prox.DEFAULT_WORKERS, prox.DEFAULT_TIMEOUT, database)
    if not checks:
        prox.check_targets(prox.DEFAULT_TIMEOUT)
    prox.json_file(args.report, {
        "plan_id": plan["id"], "shard": args.shard, "tested_candidates": len(proxies),
        "checks": [asdict(item) for item in checks],
    })


def merge(args):
    plan = read_json(args.plan / "plan.json")
    checks = []
    tested = 0
    for shard, size in enumerate(plan["shard_sizes"]):
        report = read_json(args.reports / f"check-{shard}.json")
        if report["plan_id"] != plan["id"] or report["shard"] != shard or report["tested_candidates"] != size:
            raise ValueError(f"Incomplete or mismatched report for shard {shard}")
        tested += report["tested_candidates"]
        for row in report["checks"]:
            proxy = prox.Proxy(**row.pop("proxy"))
            modes = ("connect", "forward") if proxy.scheme in prox.WEB_PROXIES else ("tunnel",)
            if proxy.scheme not in prox.PROTOCOLS or row["mode"] not in modes or not prox.COUNTRY_CODE.fullmatch(row["country"]):
                raise ValueError(f"Invalid check in report for shard {shard}")
            checks.append(prox.Check(proxy=proxy, **row))
    prox.publish_snapshot(args.output, checks, {
        **plan["manifest"],
        "finished_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tested_candidates": tested,
    })


def main():
    parser = argparse.ArgumentParser(description="مراحل گردآوری و تست موازی در GitHub Actions")
    stages = parser.add_subparsers(required=True)

    prepare_parser = stages.add_parser("prepare")
    prepare_parser.add_argument("plan", type=Path)
    prepare_parser.add_argument("--sources", type=Path, default=Path(__file__).with_name("sources.json"))
    prepare_parser.add_argument("--previous", type=Path)
    prepare_parser.add_argument("--limit", type=int, default=0)
    prepare_parser.add_argument("--github-output", required=True, type=Path)
    prepare_parser.set_defaults(stage=prepare)

    check_parser = stages.add_parser("check")
    check_parser.add_argument("plan", type=Path)
    check_parser.add_argument("shard", type=int)
    check_parser.add_argument("report", type=Path)
    check_parser.set_defaults(stage=check)

    merge_parser = stages.add_parser("merge")
    merge_parser.add_argument("plan", type=Path)
    merge_parser.add_argument("reports", type=Path)
    merge_parser.add_argument("output", type=Path)
    merge_parser.set_defaults(stage=merge)

    args = parser.parse_args()
    try:
        args.stage(args)
    except (ValueError, OSError, EOFError, KeyError, TypeError, subprocess.SubprocessError) as error:
        parser.exit(1, f"Prox: {error}\n")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    main()
