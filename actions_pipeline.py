import argparse
import json
import os
import subprocess
import sys
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from hashlib import file_digest
from math import ceil
from pathlib import Path
from shutil import copyfile
from uuid import uuid4

import prox


TARGET_SHARD_SIZE = 10_000
RECHECK_SHARD_SIZE = 3_000
MAX_MATRIX_JOBS = 256
COUNTRY_FILE = "country.csv.gz"
FULL_SCAN_LIST = Path("full-scan/all.txt")
PUBLISHED_LIST = Path("results/all.txt")
PUBLISHED_MANIFEST = Path("results/manifest.json")
FRESH_WINDOW = timedelta(minutes=3)


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def full_scan_list(repository):
    baseline = repository / FULL_SCAN_LIST
    if baseline.is_file():
        return baseline
    published = repository / PUBLISHED_LIST
    manifest = repository / PUBLISHED_MANIFEST
    if published.is_file() and manifest.is_file():
        data = read_json(manifest)
        if data.get("scan_mode", "full") == "full" and data["tested_candidates"] == data["discovered_candidates"]:
            return published
    return None


def sha256_file(path):
    with path.open("rb") as file:
        return file_digest(file, "sha256").hexdigest()


def write_output(path, name, value):
    with path.open("a", encoding="utf-8") as file:
        print(f"{name}={json.dumps(value)}", file=file)


def prepare(args):
    if args.limit < 0:
        raise ValueError("مقدار limit باید نامنفی باشد")
    started = datetime.now(timezone.utc)
    previous = args.previous
    if args.snapshot_root is not None:
        previous = full_scan_list(args.snapshot_root)
    if args.scan == "recheck":
        if args.limit:
            raise ValueError("بازتست باید تمام فهرست مبنا را بررسی کند")
        if args.skip_fresh:
            published = args.snapshot_root / PUBLISHED_MANIFEST
            if published.is_file():
                data = read_json(published)
                finished = datetime.fromisoformat(data["finished_at_utc"])
                complete = data["tested_candidates"] == data["discovered_candidates"]
                if complete and timedelta(0) <= started - finished < FRESH_WINDOW:
                    print("انتشار قبلی تازه است. بازتست تا نوبت بعد انجام نمی‌شود.", flush=True)
                    write_output(args.github_output, "shards", [])
                    return
        selected = list(prox.read_previous_candidates(previous))
        if not selected:
            print("فهرست سالمی از تست اصلی برای بازتست وجود ندارد.", flush=True)
            write_output(args.github_output, "shards", [])
            return
        prox.require_curl()
        collection_stats = {"discovered_candidates": len(selected), "baseline_sha256": sha256_file(previous)}
        shard_size = RECHECK_SHARD_SIZE
    else:
        prox.require_curl()
        publishers, candidates, collection_stats = prox.collect(prox.load_feeds(args.sources), previous)
        selected = prox.select_candidates(publishers, candidates, args.limit, started)
        shard_size = TARGET_SHARD_SIZE
    shard_count = min(ceil(len(selected) / shard_size), MAX_MATRIX_JOBS)

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
            "scan_mode": args.scan,
            "started_at_utc": started.isoformat(timespec="seconds"),
            "country_database": {"source": database_source, "credit": "IP Geolocation by DB-IP"},
            **collection_stats,
        },
    })
    write_output(args.github_output, "shards", list(range(shard_count)))
    print(f"{len(selected):,} نامزد یکتا در {shard_count:,} بخش آماده شد", flush=True)


def read_shard(plan_path, shard, size):
    with (plan_path / f"{shard}.txt").open(encoding="utf-8") as file:
        proxies = [prox.parse_proxy(line.rstrip("\n")) for line in file]
    if None in proxies or len(set(proxies)) != len(proxies) or len(proxies) != size:
        raise ValueError(f"Invalid candidate list for shard {shard}")
    return proxies


def check(args):
    prox.require_curl()
    plan = read_json(args.plan / "plan.json")
    if not 0 <= args.shard < len(plan["shard_sizes"]):
        raise ValueError(f"Invalid shard: {args.shard}")
    proxies = read_shard(args.plan, args.shard, plan["shard_sizes"][args.shard])
    targets, direct_ips = prox.check_targets(prox.DEFAULT_TIMEOUT)
    started = datetime.fromisoformat(plan["manifest"]["started_at_utc"])
    database, _ = prox.load_country_database(started, args.plan / COUNTRY_FILE)
    checks, failures = prox.check_all(
        proxies, prox.DEFAULT_WORKERS, prox.DEFAULT_TIMEOUT, database, targets, direct_ips,
        retry_timeout=plan["manifest"]["scan_mode"] == "recheck",
    )
    if not checks:
        prox.choose_target(targets["https"], prox.DEFAULT_TIMEOUT)
    prox.json_file(args.report, {
        "plan_id": plan["id"], "shard": args.shard, "tested_candidates": len(proxies),
        "checks": [asdict(item) for item in checks],
        "probe_failures": dict(failures),
    })


def merge(args):
    plan = read_json(args.plan / "plan.json")
    checks = []
    failures = Counter()
    tested = 0
    endpoints = set()
    for shard, size in enumerate(plan["shard_sizes"]):
        report = read_json(args.reports / f"check-{shard}.json")
        if report["plan_id"] != plan["id"] or report["shard"] != shard or report["tested_candidates"] != size:
            raise ValueError(f"Incomplete or mismatched report for shard {shard}")
        tested += report["tested_candidates"]
        failures.update(report.get("probe_failures", {}))
        candidates = set(read_shard(args.plan, shard, size))
        endpoints.update((proxy.host, proxy.port) for proxy in candidates)
        seen = set()
        for row in report["checks"]:
            proxy = prox.Proxy(**row.pop("proxy"))
            modes = ("connect", "forward") if proxy.scheme in prox.WEB_PROXIES else ("tunnel",)
            key = (proxy, row["mode"])
            if (
                proxy not in candidates or row["mode"] not in modes or key in seen
                or not prox.COUNTRY_CODE.fullmatch(row["country"])
            ):
                raise ValueError(f"Invalid check in report for shard {shard}")
            seen.add(key)
            checks.append(prox.Check(proxy=proxy, **row))
    prox.publish_snapshot(args.output, checks, {
        **plan["manifest"],
        "finished_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tested_candidates": tested,
        "tested_endpoints": len(endpoints),
        "probe_failures": dict(failures),
    })


def stage_publication(args):
    manifest = read_json(args.snapshot / "manifest.json")
    all_proxies = args.snapshot / "all.txt"
    if not all_proxies.is_file():
        raise ValueError("Snapshot is missing all.txt")
    published = args.repository / PUBLISHED_MANIFEST
    if published.is_file():
        current_start = datetime.fromisoformat(read_json(published)["started_at_utc"])
        new_start = datetime.fromisoformat(manifest["started_at_utc"])
        if new_start <= current_start:
            print("خروجی تازه‌تری در مخزن ثبت شده است.", flush=True)
            write_output(args.github_output, "publish", False)
            return

    baseline = args.repository / FULL_SCAN_LIST
    previous = full_scan_list(args.repository)
    if manifest["scan_mode"] == "recheck":
        if previous is None or sha256_file(previous) != manifest["baseline_sha256"]:
            print("فهرست مبنای بازتست تغییر کرده است.", flush=True)
            write_output(args.github_output, "publish", False)
            return
    elif manifest["tested_candidates"] == manifest["discovered_candidates"]:
        previous = all_proxies

    if previous is not None and previous != baseline:
        baseline.parent.mkdir(parents=True, exist_ok=True)
        copyfile(previous, baseline)
    write_output(args.github_output, "publish", True)


def main():
    parser = argparse.ArgumentParser(description="مراحل گردآوری و تست موازی در GitHub Actions")
    stages = parser.add_subparsers(required=True)

    prepare_parser = stages.add_parser("prepare")
    prepare_parser.add_argument("plan", type=Path)
    prepare_parser.add_argument("--sources", type=Path, default=Path(__file__).with_name("sources.json"))
    previous = prepare_parser.add_mutually_exclusive_group()
    previous.add_argument("--previous", type=Path)
    previous.add_argument("--snapshot-root", type=Path)
    prepare_parser.add_argument("--scan", choices=("full", "recheck"), default="full")
    prepare_parser.add_argument("--skip-fresh", action="store_true")
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

    publish_parser = stages.add_parser("stage-publication")
    publish_parser.add_argument("snapshot", type=Path)
    publish_parser.add_argument("repository", type=Path)
    publish_parser.add_argument("--github-output", required=True, type=Path)
    publish_parser.set_defaults(stage=stage_publication)

    args = parser.parse_args()
    if args.stage is prepare and args.skip_fresh and (args.scan != "recheck" or args.snapshot_root is None):
        parser.error("--skip-fresh requires --scan recheck and --snapshot-root")
    try:
        args.stage(args)
    except (ValueError, OSError, EOFError, KeyError, TypeError, subprocess.SubprocessError) as error:
        if os.environ.get("GITHUB_ACTIONS") == "true":
            message = str(error).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
            print(f"::error::{message}", flush=True)
        parser.exit(1, f"Prox: {error}\n")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    main()
