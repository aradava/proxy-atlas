import argparse
import csv
import gzip
import io
import json
import re
import secrets
import shutil
import subprocess
import sys
from bisect import bisect_right
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from ipaddress import IPv6Address, ip_address
from itertools import islice
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit


PROTOCOLS = ("http", "https", "socks4", "socks4a", "socks5", "socks5h")
WEB_PROXIES = ("http", "https")
PROBE_URLS = {
    "https": ("https://api64.ipify.org/", "https://checkip.amazonaws.com/"),
    "http": ("http://api.ipify.org/",),
}
COUNTRY_CODE = re.compile(r"[A-Z]{2}")
ENDPOINT = re.compile(
    r"(?:(http|https|socks4a?|socks5h?)://)?(\[[0-9a-f:]+\]|[0-9.]+):([0-9]{1,5})",
    re.IGNORECASE | re.ASCII,
)
MAX_FEED_BYTES = 8 * 1024 * 1024
MAX_GEO_BYTES = 16 * 1024 * 1024
DEFAULT_WORKERS = 96
DEFAULT_TIMEOUT = 6
SCHEMA = {"generator": "prox", "schema_version": 1}


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


@dataclass(frozen=True)
class Check:
    proxy: Proxy
    mode: str
    exit_ip: str
    country: str
    latency_ms: int


class CurlRequestError(ValueError):
    def __init__(self, returncode, status):
        super().__init__(f"curl {returncode}, HTTP {status}")
        if returncode == 28:
            self.reason = "timeout"
        elif status not in ("?", "000", "200"):
            self.reason = "http_status"
        elif returncode and returncode != 63:
            self.reason = "connection"
        else:
            self.reason = "invalid_response"


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
    if proxy is None:
        return ()
    schemes = {
        "https": ("https", "http"),
        "socks4": ("socks4", "socks4a"),
        "socks4a": ("socks4a", "socks4"),
        "socks5": ("socks5", "socks5h"),
        "socks5h": ("socks5h", "socks5"),
    }.get(proxy.scheme, (proxy.scheme,))
    return tuple(Proxy(scheme, proxy.host, proxy.port) for scheme in schemes)


def feed_entries(payload, feed):
    if feed.format in ("text", "text-with-country"):
        text = payload.decode("utf-8-sig", errors="replace")
        for line in text.splitlines():
            parts = line.split(maxsplit=1)
            if parts and not parts[0].startswith("#"):
                endpoint = parts[0]
                if feed.format == "text-with-country":
                    address, _, country = endpoint.rpartition(":")
                    if COUNTRY_CODE.fullmatch(country.upper()):
                        endpoint = address
                yield from parse_endpoint(endpoint, feed.protocol)
        return

    rows = json.loads(payload.decode("utf-8-sig"))
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
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        schemes = row.get("protocol", row.get("protocols", feed.protocol))
        if not isinstance(schemes, list):
            schemes = [schemes]
        for scheme in schemes:
            if isinstance(scheme, str) and scheme.lower() in PROTOCOLS:
                yield from parse_endpoint(f"{host}:{row.get('port')}", scheme.lower())


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
        if feed.protocol not in (None, *PROTOCOLS) or feed.format not in ("text", "text-with-country", "json"):
            raise ValueError(f"Unsupported feed configuration: {feed.url}")
    if not feeds or len({feed.url for feed in feeds}) != len(feeds):
        raise ValueError("Configure at least one feed and use each URL once")
    return feeds


def curl_request(url, timeout, max_bytes, proxy=None, download=False):
    command = [
        "curl", "--disable", "--silent", "--show-error", "--fail", "--globoff",
        "--max-time", str(timeout), "--connect-timeout", str(min(timeout, 8)),
        "--max-filesize", str(max_bytes), "--write-out", "\n%{http_code} %{time_total}",
    ]
    if download:
        command += [
            "--proto", "=https", "--proto-redir", "=https", "--location",
            "--max-redirs", "3",
        ]
    if proxy is None:
        command += ["--proxy", ""]
    else:
        command += ["--proxy", proxy.url, "--noproxy", ""]
    response = subprocess.run(
        [*command, "--url", url], capture_output=True,
        timeout=timeout + 3,
        check=False,
    )
    body, _, status = response.stdout.rpartition(b"\n")
    fields = status.split()
    if response.returncode or len(fields) != 2 or fields[0] != b"200" or len(body) > max_bytes:
        status_code = fields[0].decode("ascii", errors="replace") if fields else "?"
        raise CurlRequestError(response.returncode, status_code)
    return body, round(float(fields[1]) * 1000)


def fetch_feed(feed):
    try:
        payload, _ = curl_request(feed.url, 20, MAX_FEED_BYTES, download=True)
        proxies = list(dict.fromkeys(feed_entries(payload, feed)))
        if not proxies:
            raise ValueError("No public proxy endpoints parsed")
        return feed, proxies, None
    except (ValueError, RecursionError, subprocess.TimeoutExpired) as error:
        return feed, [], str(error) if not isinstance(error, subprocess.TimeoutExpired) else "download timed out"


def read_previous_candidates(path):
    previous = {}
    if path is None:
        return previous
    try:
        with path.open(encoding="utf-8-sig") as file:
            for line in file:
                proxy = parse_proxy(line.strip())
                if proxy is not None:
                    previous[proxy] = None
    except FileNotFoundError:
        pass
    return previous


def collect(feeds, previous_file=None):
    by_publisher = defaultdict(dict)
    source_stats = []
    with ThreadPoolExecutor(max_workers=12) as executor:
        for feed, proxies, error in executor.map(fetch_feed, feeds):
            source_stats.append({**asdict(feed), "candidates": len(proxies), "error": error})
            by_publisher[feed.publisher].update(dict.fromkeys(proxies))
            status = f"خطا: {error}" if error else f"{len(proxies):,} نامزد"
            print(f"{feed.publisher}: {status} ({feed.url})", flush=True)
    candidates = set().union(*by_publisher.values())
    previous = read_previous_candidates(previous_file)
    previous_only = {proxy: None for proxy in previous if proxy not in candidates}
    if previous_only:
        by_publisher[None] = previous_only
        candidates.update(previous_only)
    if not candidates:
        raise ValueError("هیچ پروکسی عمومی معتبری از فیدها یا خروجی قبلی پیدا نشد")
    return by_publisher, candidates, {
        "discovered_candidates": len(candidates),
        "previous_candidates": len(previous),
        "previous_only_candidates": len(previous_only),
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


def load_country_database(started, path, *, save_to=None):
    if path is not None:
        with path.open("rb") as file:
            data = file.read(MAX_GEO_BYTES + 1)
        if len(data) > MAX_GEO_BYTES:
            raise ValueError("Local country database exceeds the size limit")
        database = CountryDatabase(data)
        if save_to is not None:
            save_to.write_bytes(data)
        return database, path.name

    previous = started.replace(day=1) - timedelta(days=1)
    for month in (started, previous):
        filename = f"dbip-country-lite-{month:%Y-%m}.csv.gz"
        url = f"https://download.db-ip.com/free/{filename}"
        try:
            data, _ = curl_request(url, 30, MAX_GEO_BYTES, download=True)
            database = CountryDatabase(data)
        except (ValueError, OSError, EOFError, subprocess.TimeoutExpired) as error:
            print(f"Country data unavailable ({filename}): {error}", file=sys.stderr)
            continue
        if save_to is not None:
            save_to.write_bytes(data)
        return database, url
    raise ValueError("No usable DB-IP country database was available")


def probe_ip(url, timeout, proxy=None):
    if not url.startswith("http://"):
        body, latency = curl_request(url, timeout, 256, proxy=proxy)
        return public_ip(body.decode("ascii").strip()), latency

    # A unique callback makes an old cached IP or static IP response invalid.
    callback = f"prox_{secrets.token_hex(12)}"
    body, latency = curl_request(f"{url}?format=jsonp&callback={callback}", timeout, 256, proxy=proxy)
    prefix = f"{callback}(".encode("ascii")
    body = body.strip()
    if not body.startswith(prefix) or not body.endswith(b");"):
        raise ValueError("HTTP probe did not echo its callback")
    result = json.loads(body[len(prefix):-2].decode("ascii"))
    if not isinstance(result, dict) or not isinstance(result.get("ip"), str):
        raise ValueError("HTTP probe did not return an IP")
    return public_ip(result["ip"]), latency


def choose_target(urls, timeout):
    last_error = None
    for url in urls * 2:
        try:
            ip, _ = probe_ip(url, max(10, timeout))
            return url, ip
        except (ValueError, subprocess.TimeoutExpired) as error:
            last_error = error
    raise ValueError(f"آزمون مستقیم مقصد {urls[0]} ناموفق بود ({last_error})") from last_error


def check_targets(timeout):
    targets, direct_ips = {}, set()
    for scheme, urls in PROBE_URLS.items():
        targets[scheme], ip = choose_target(urls, timeout)
        direct_ips.add(ip)
    return targets, frozenset(direct_ips)


def probe_proxy(url, timeout, proxy, retry_timeout):
    try:
        return probe_ip(url, timeout, proxy)
    except (CurlRequestError, subprocess.TimeoutExpired) as error:
        if not retry_timeout or (isinstance(error, CurlRequestError) and error.reason != "timeout"):
            raise
    return probe_ip(url, timeout, proxy)


def check_proxy(proxy, timeout, database, targets, direct_ips, retry_timeout):
    modes = [("https", "connect" if proxy.scheme in WEB_PROXIES else "tunnel")]
    if proxy.scheme in WEB_PROXIES:
        modes.append(("http", "forward"))
    checks = []
    failures = Counter()
    for scheme, mode in modes:
        try:
            ip, latency = probe_proxy(targets[scheme], timeout, proxy, retry_timeout)
        except CurlRequestError as error:
            failures[error.reason] += 1
            continue
        except subprocess.TimeoutExpired:
            failures["timeout"] += 1
            continue
        except ValueError:
            failures["invalid_response"] += 1
            continue
        if ip in direct_ips:
            failures["runner_ip"] += 1
            continue
        checks.append(Check(proxy, mode, str(ip), database.country(ip), latency))
    return checks, failures


def check_all(proxies, workers, timeout, database, targets, direct_ips, *, retry_timeout=False):
    def check(proxy):
        return check_proxy(proxy, timeout, database, targets, direct_ips, retry_timeout)

    checks = []
    failures = Counter()
    remaining = iter(proxies)
    completed = 0
    with ThreadPoolExecutor(max_workers=workers) as executor:
        while batch := list(islice(remaining, workers * 16)):
            for result, rejected in executor.map(check, batch):
                checks.extend(result)
                failures.update(rejected)
            completed += len(batch)
            print(f"تست‌شده {completed:,}/{len(proxies):,}، آزمون موفق {len(checks):,}", flush=True)
    return checks, failures


def json_file(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def write_snapshot(root, checks, manifest):
    lists = defaultdict(dict)
    lists["all.txt"] = {}
    for protocol in PROTOCOLS:
        lists[f"protocols/{protocol}.txt"] = {}
    rows = []
    for check in sorted(checks, key=lambda item: (item.latency_ms, item.proxy.url, item.mode)):
        url, protocol, country = check.proxy.url, check.proxy.scheme, check.country
        rows.append({
            "proxy": url, "protocol": protocol, "mode": check.mode,
            "exit_ip": check.exit_ip, "country": country, "latency_ms": check.latency_ms,
        })
        for path in (
            "all.txt", f"protocols/{protocol}.txt", f"modes/{protocol}-{check.mode}.txt",
            f"countries/{country}/all.txt", f"countries/{country}/{protocol}.txt",
        ):
            lists[path][url] = None

    for path, urls in lists.items():
        file = root / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text("".join(f"{url}\n" for url in urls), encoding="utf-8", newline="\n")
    countries = sorted({check.country for check in checks})
    json_file(root / "proxies.json", rows)
    json_file(root / "manifest.json", {
        **SCHEMA, **manifest,
        "working_proxies": len(lists["all.txt"]),
        "successful_probes": len(checks),
        "countries": {code: len(lists[f"countries/{code}/all.txt"]) for code in countries},
    })


def publish_snapshot(output, checks, manifest):
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
            if any(old.get(key) != value for key, value in SCHEMA.items()):
                raise ValueError(f"Choose a new directory or a previous Prox output: {output}")
        with TemporaryDirectory(dir=output.parent, prefix=".prox-") as temporary:
            root = Path(temporary)
            snapshot, previous = root / "snapshot", root / "previous"
            write_snapshot(snapshot, checks, manifest)
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
        raise ValueError("curl با قابلیت HTTPS-proxy را نصب و به PATH اضافه کنید")
    version = subprocess.check_output(["curl", "--disable", "--version"], text=True)
    if "HTTPS-proxy" not in version or tuple(map(int, version.split()[1].split(".")[:2])) < (8, 4):
        raise ValueError("curl نسخهٔ ۸٫۴ یا جدیدتر با قابلیت HTTPS-proxy لازم است")


def main():
    parser = argparse.ArgumentParser(description="گردآوری و تست پروکسی‌های عمومی HTTP و SOCKS")
    parser.add_argument("--sources", type=Path, default=Path(__file__).with_name("sources.json"), help="فایل تنظیم منابع")
    parser.add_argument("--output", type=Path, default=Path("results"), help="پوشهٔ نتیجه")
    parser.add_argument("--country-db", type=Path, help="فایل محلی CSV.GZ پایگاه DB-IP Country Lite")
    parser.add_argument("--limit", type=int, default=0, help="سقف اختیاری نامزدهای تست؛ پیش‌فرض ۰ یعنی همه")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS, help="تعداد بررسی‌های هم‌زمان")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="حداکثر زمان هر درخواست به ثانیه")
    args = parser.parse_args()
    if args.limit < 0 or not 1 <= args.workers <= 256 or not 1 <= args.timeout <= 60:
        parser.error("سقف نامزدها نامنفی، تعداد بررسی هم‌زمان ۱ تا ۲۵۶ و مهلت درخواست ۱ تا ۶۰ ثانیه است")
    started = datetime.now(timezone.utc)
    try:
        require_curl()
        feeds = load_feeds(args.sources)
        targets, direct_ips = check_targets(args.timeout)
        database, database_source = load_country_database(started, args.country_db)
        by_publisher, candidates, collection_stats = collect(feeds, args.output / "all.txt")
        selected = select_candidates(by_publisher, candidates, args.limit, started)
        print(f"بررسی {len(selected):,} از {len(candidates):,} نامزد یکتا", flush=True)
        checks, failures = check_all(selected, args.workers, args.timeout, database, targets, direct_ips)
        if not checks:
            for target in targets.values():
                choose_target((target,), args.timeout)
        publish_snapshot(args.output, checks, {
            "started_at_utc": started.isoformat(timespec="seconds"),
            "finished_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "country_database": {"source": database_source, "credit": "IP Geolocation by DB-IP"},
            "tested_candidates": len(selected),
            "probe_failures": dict(failures),
            **collection_stats,
        })
    except (ValueError, OSError, EOFError, KeyError, TypeError, subprocess.SubprocessError) as error:
        parser.exit(1, f"Prox: {error}\n")
    print(f"{len({check.proxy for check in checks}):,} پروکسی سالم در {args.output} ذخیره شد")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    main()
