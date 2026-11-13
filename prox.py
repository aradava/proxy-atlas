import argparse
import csv
import gzip
import io
import json
import os
import re
import shutil
import subprocess
import sys
from bisect import bisect_right
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from ipaddress import IPv6Address, ip_address
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit

from proxy_sources import table_entries


PROTOCOLS = ("http", "https", "socks4", "socks4a", "socks5", "socks5h")
TABLE_FORMATS = ("table", "proxynova", "proxyverity")
PROTOCOL_LABEL = re.compile(r"\b(?:https?|socks4a?|socks5h?)\b", re.IGNORECASE | re.ASCII)
COUNTRY_CODE = re.compile(r"[A-Z]{2}")
ENDPOINT = re.compile(
    r"(?:(http|https|socks4a?|socks5h?)://)?(\[[0-9a-f:]+\]|[0-9.]+):([0-9]{1,5})",
    re.IGNORECASE | re.ASCII,
)
MAX_FEED_BYTES = 8 * 1024 * 1024
MAX_GEO_BYTES = 16 * 1024 * 1024
SCHEMA = {"generator": "prox", "schema_version": 2}


@dataclass(frozen=True)
class Proxy:
    scheme: str
    host: str
    port: int

    @property
    def url(self):
        host = f"[{self.host}]" if ":" in self.host else self.host
        return f"{self.scheme}://{host}:{self.port}"


@dataclass(frozen=True)
class Feed:
    publisher: str
    homepage: str
    url: str
    protocol: str | None = None
    format: str = "text"


def public_ip(value):
    if "%" in value:
        raise ValueError("Scoped IP address")
    ip = ip_address(value)
    if isinstance(ip, IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    if not ip.is_global or ip.is_multicast or ip.is_reserved or getattr(ip, "is_site_local", False):
        raise ValueError("Non-public IP address")
    return ip


def parse_proxy(value, protocol=None):
    match = ENDPOINT.fullmatch(value)
    if match is None:
        return None
    advertised, host, port = match.groups()
    scheme = advertised.lower() if advertised else protocol
    if scheme not in PROTOCOLS or not 1 <= int(port) <= 65535:
        return None
    try:
        ip = public_ip(host.strip("[]"))
    except ValueError:
        return None
    return Proxy(scheme, str(ip), int(port))


def parse_endpoint(value, protocol):
    proxy = parse_proxy(value.strip().removesuffix("/"), protocol)
    return () if proxy is None else (proxy,)


def parse_host_port(host, port, protocol):
    host = host.strip()
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    return parse_endpoint(f"{host}:{str(port).strip()}", protocol)


def feed_entries(payload, feed):
    if feed.format in TABLE_FORMATS:
        text = payload.decode("utf-8-sig", errors="replace")
        for address, port, labels in table_entries(text, feed.format):
            schemes = PROTOCOL_LABEL.findall(labels or "") or [feed.protocol]
            for scheme in schemes:
                scheme = scheme.lower() if scheme else None
                if port is None:
                    for endpoint in address.split():
                        yield from parse_endpoint(endpoint, scheme)
                else:
                    yield from parse_host_port(address, port, scheme)
        return

    if feed.format in ("text", "text-with-country"):
        text = payload.decode("utf-8-sig", errors="replace")
        for line in text.splitlines():
            parts = line.split(maxsplit=1)
            if parts and not parts[0].startswith("#"):
                endpoint = parts[0]
                if feed.format == "text-with-country":
                    address, _, country = endpoint.rpartition(":")
                    # Some feeds append a country name instead of an ISO code.
                    if country and country[0].isalpha():
                        endpoint = address
                yield from parse_endpoint(endpoint, feed.protocol)
        return

    text = payload.decode("utf-8-sig")
    if feed.format == "csv":
        rows = csv.DictReader(io.StringIO(text))
    else:
        rows = json.loads(text)
        if isinstance(rows, dict):
            rows = rows.get("data", rows.get("proxies"))
        if not isinstance(rows, list):
            raise ValueError("JSON feed must be an array or contain a data/proxies array")
    for row in rows:
        if isinstance(row, str):
            yield from parse_endpoint(row, feed.protocol)
            continue
        if not isinstance(row, dict):
            continue
        url = row.get("url", row.get("proxy"))
        if isinstance(url, str):
            endpoints = parse_endpoint(url, feed.protocol)
            if endpoints:
                yield from endpoints
                continue
        host = row.get("host", row.get("ip", row.get("ip_address")))
        if not isinstance(host, str):
            continue
        schemes = row.get("protocol", row.get("protocols", feed.protocol))
        if not isinstance(schemes, list):
            schemes = [schemes]
        for scheme in schemes:
            if isinstance(scheme, str) and scheme.lower() in PROTOCOLS:
                yield from parse_host_port(host, row.get("port"), scheme.lower())


def load_feeds(path):
    config = json.loads(path.read_text(encoding="utf-8"))
    feeds = [
        Feed(source["publisher"], source["homepage"], **feed)
        for source in config
        for feed in source["feeds"]
    ]
    for feed in feeds:
        url = urlsplit(feed.url)
        if url.scheme != "https" or not url.hostname or url.username is not None:
            raise ValueError(f"Expected an HTTPS feed URL without credentials: {feed.url}")
        if feed.protocol not in (None, *PROTOCOLS) or feed.format not in ("text", "text-with-country", "json", "csv", *TABLE_FORMATS):
            raise ValueError(f"Unsupported feed configuration: {feed.url}")
    if not feeds or len({feed.url for feed in feeds}) != len(feeds):
        raise ValueError("Configure at least one feed and use each URL once")
    return feeds


def download(url, timeout, max_bytes, *, retry=False):
    command = [
        "curl", "--disable", "--silent", "--show-error", "--fail", "--globoff",
        "--max-time", str(timeout), "--connect-timeout", str(min(timeout, 8)),
        "--max-filesize", str(max_bytes), "--write-out", "\n%{http_code}",
        "--proto", "=https", "--proto-redir", "=https", "--location",
        "--max-redirs", "3", "--user-agent", "ProxyAtlas/1.0 (+https://github.com/aradava/proxy-atlas)",
        "--proxy", "",
    ]
    if retry:
        command += ["--retry", "2", "--retry-max-time", str(timeout)]
    with TemporaryDirectory(prefix="prox-download-") as directory:
        output = Path(directory) / "feed"
        response = subprocess.run(
            [*command, "--output", str(output), "--url", url], capture_output=True,
            timeout=timeout * (2 if retry else 1) + 3, check=False,
        )
        status = response.stdout.strip()
        if response.returncode or status != b"200":
            status_code = status.decode("ascii", errors="replace") or "?"
            raise ValueError(f"curl {response.returncode}, HTTP {status_code}")
        if not output.exists():
            return b""
        with output.open("rb") as file:
            body = file.read(max_bytes + 1)
        if len(body) > max_bytes:
            raise ValueError("Download exceeds the size limit")
        return body


def fetch_feed(feed):
    try:
        payload = download(feed.url, 20, MAX_FEED_BYTES, retry=True)
    except (ValueError, OSError, subprocess.TimeoutExpired) as error:
        detail = "download timed out" if isinstance(error, subprocess.TimeoutExpired) else str(error)
        return feed, [], "download_error", detail

    if feed.format in ("text", "text-with-country") and not payload.decode("utf-8-sig", errors="replace").strip():
        return feed, [], "empty", None
    try:
        proxies = list(dict.fromkeys(feed_entries(payload, feed)))
        if not proxies:
            raise ValueError("No public proxy endpoints parsed")
    except (ValueError, RecursionError) as error:
        return feed, [], "parse_error", str(error)
    return feed, proxies, "ok", None


def collect(feeds):
    by_publisher = defaultdict(dict)
    source_stats = []
    batches = defaultdict(list)
    for index, feed in enumerate(feeds):
        # Pages from the same website are fetched in sequence to avoid bursts.
        key = urlsplit(feed.url).hostname if feed.format in TABLE_FORMATS else index
        batches[key].append((index, feed))

    def fetch_batch(batch):
        return [(index, fetch_feed(feed)) for index, feed in batch]

    with ThreadPoolExecutor(max_workers=12) as executor:
        downloaded = [item for batch in executor.map(fetch_batch, batches.values()) for item in batch]
    for _, (feed, proxies, state, error) in sorted(downloaded):
        source_stats.append({**asdict(feed), "candidates": len(proxies), "status": state, "error": error})
        by_publisher[feed.publisher].update(dict.fromkeys(proxies))
        status = f"خطا: {error}" if error else f"{len(proxies):,} نامزد"
        print(f"{feed.publisher}: {status} ({feed.url})", flush=True)
    candidates = set().union(*by_publisher.values())
    if not candidates:
        raise ValueError("هیچ آدرس پروکسی عمومی از فیدها پیدا نشد")
    return by_publisher, candidates, {
        "discovered_candidates": len(candidates),
        "sources": source_stats,
    }


def select_candidates(by_publisher, candidates, limit, started):
    if not limit or len(candidates) <= limit:
        return sorted(candidates, key=lambda proxy: proxy.url)

    # Rotate long feeds between scheduled runs and give each publisher a turn.
    pools = []
    interval = int(started.timestamp()) // 7200
    for entries in by_publisher.values():
        items = list(entries)
        if items:
            offset = interval * 997 % len(items)
            pools.append(iter(items[offset:] + items[:offset]))
    selected = {}
    while len(selected) < limit:
        for pool in pools:
            for proxy in pool:
                if proxy not in selected:
                    selected[proxy] = None
                    break
            if len(selected) == limit:
                break
    return list(selected)


class CountryDatabase:
    def __init__(self, compressed):
        self.ranges = {4: ([], [], []), 6: ([], [], [])}
        with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as data:
            with io.TextIOWrapper(data, encoding="utf-8", newline="") as text:
                for first, last, code in csv.reader(text):
                    start, end = ip_address(first), ip_address(last)
                    code = code.upper()
                    starts, ends, countries = self.ranges[start.version]
                    if start.version != end.version or start > end or (ends and int(start) <= ends[-1]):
                        raise ValueError("Invalid or overlapping IP range in country database")
                    starts.append(int(start))
                    ends.append(int(end))
                    countries.append(code if COUNTRY_CODE.fullmatch(code) else "ZZ")
        if not all(starts for starts, _, _ in self.ranges.values()):
            raise ValueError("Country database is missing IPv4 or IPv6 ranges")

    def country(self, ip):
        starts, ends, countries = self.ranges[ip.version]
        index = bisect_right(starts, int(ip)) - 1
        return countries[index] if index >= 0 and int(ip) <= ends[index] else "ZZ"


def load_country_database(started, path):
    if path is not None:
        with path.open("rb") as file:
            data = file.read(MAX_GEO_BYTES + 1)
        if len(data) > MAX_GEO_BYTES:
            raise ValueError("Local country database exceeds the size limit")
        return CountryDatabase(data), path.name

    previous = started.replace(day=1) - timedelta(days=1)
    for month in (started, previous):
        filename = f"dbip-country-lite-{month:%Y-%m}.csv.gz"
        url = f"https://download.db-ip.com/free/{filename}"
        try:
            data = download(url, 30, MAX_GEO_BYTES)
            database = CountryDatabase(data)
        except (ValueError, OSError, EOFError, subprocess.TimeoutExpired) as error:
            print(f"Country data unavailable ({filename}): {error}", file=sys.stderr)
            continue
        return database, url
    raise ValueError("No usable DB-IP country database was available")


def json_file(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def write_snapshot(root, proxies, database, manifest):
    lists = defaultdict(list)
    for protocol in PROTOCOLS:
        lists[f"protocols/{protocol}.txt"] = []
    endpoints = set()
    countries = {}
    with (root / "proxies.json").open("w", encoding="utf-8", newline="\n") as file:
        file.write("[\n")
        for index, proxy in enumerate(proxies):
            if proxy.host not in countries:
                countries[proxy.host] = database.country(ip_address(proxy.host))
            country = countries[proxy.host]
            url, protocol = proxy.url, proxy.scheme
            endpoints.add((proxy.host, proxy.port))
            if index:
                file.write(",\n")
            row = {"proxy": url, "protocol": protocol, "country": country}
            file.write(json.dumps(row, separators=(",", ":")))
            for path in (
                "all.txt", f"protocols/{protocol}.txt",
                f"countries/{country}/all.txt", f"countries/{country}/{protocol}.txt",
            ):
                lists[path].append(url)
        file.write("\n]\n")

    for path, urls in lists.items():
        file = root / path
        file.parent.mkdir(parents=True, exist_ok=True)
        with file.open("w", encoding="utf-8", newline="\n") as output:
            output.writelines(f"{url}\n" for url in urls)
    json_file(root / "manifest.json", {
        **SCHEMA, **manifest,
        "finished_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "collected_proxies": len(proxies),
        "distinct_endpoints": len(endpoints),
        "countries": {
            code: len(lists[f"countries/{code}/all.txt"]) for code in sorted(set(countries.values()))
        },
    })


def publish_snapshot(output, proxies, database, manifest):
    output = output.absolute()
    output.parent.mkdir(parents=True, exist_ok=True)
    lock = output.with_name(f".{output.name}.prox-lock")
    lock.touch(exist_ok=False)
    try:
        if output.is_symlink():
            raise ValueError(f"Choose a regular output directory: {output}")
        if output.exists():
            marker = output / "manifest.json"
            old = json.loads(marker.read_text(encoding="utf-8")) if marker.is_file() else {}
            if old.get("generator") != SCHEMA["generator"] or old.get("schema_version") not in (1, SCHEMA["schema_version"]):
                raise ValueError(f"Choose a new directory or a previous Prox output: {output}")
        with TemporaryDirectory(dir=output.parent, prefix=".prox-") as temporary:
            root = Path(temporary)
            snapshot, previous = root / "snapshot", root / "previous"
            snapshot.mkdir()
            write_snapshot(snapshot, proxies, database, manifest)
            if output.exists():
                output.rename(previous)
            try:
                snapshot.rename(output)
            except OSError:
                if previous.exists():
                    previous.rename(output)
                raise
    finally:
        lock.unlink()


def require_curl():
    if not shutil.which("curl"):
        raise ValueError("curl برای دریافت فیدها لازم است")


def main():
    parser = argparse.ArgumentParser(description="گردآوری و دسته‌بندی پروکسی‌های عمومی HTTP و SOCKS")
    parser.add_argument("--sources", type=Path, default=Path(__file__).with_name("sources.json"), help="فایل تنظیم منابع")
    parser.add_argument("--output", type=Path, default=Path("results"), help="پوشهٔ نتیجه")
    parser.add_argument("--country-db", type=Path, help="فایل محلی CSV.GZ پایگاه DB-IP Country Lite")
    parser.add_argument("--limit", type=int, default=0, help="سقف اختیاری خروجی؛ پیش‌فرض ۰ یعنی همه")
    args = parser.parse_args()
    if args.limit < 0:
        parser.error("سقف خروجی باید نامنفی باشد")
    started = datetime.now(timezone.utc)
    try:
        require_curl()
        feeds = load_feeds(args.sources)
        database, database_source = load_country_database(started, args.country_db)
        by_publisher, candidates, collection_stats = collect(feeds)
        selected = select_candidates(by_publisher, candidates, args.limit, started)
        publish_snapshot(args.output, selected, database, {
            "started_at_utc": started.isoformat(timespec="seconds"),
            "collection_mode": "grabber",
            "country_database": {"source": database_source, "credit": "IP Geolocation by DB-IP"},
            **collection_stats,
        })
    except (ValueError, OSError, EOFError, KeyError, TypeError, subprocess.SubprocessError) as error:
        if os.environ.get("GITHUB_ACTIONS") == "true":
            message = str(error).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
            print(f"::error::{message}", flush=True)
        parser.exit(1, f"Prox: {error}\n")
    print(f"{len(selected):,} آدرس پروکسی در {args.output} ذخیره شد")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    main()
