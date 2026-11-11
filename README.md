<p align="center">
  <img src=".github/assets/proxy-atlas.webp" alt="نقشهٔ جهان با نقاط و مسیرهای شبکه" width="100%">
</p>

<h1 align="center">ProxyAtlas · اطلس پروکسی</h1>

<p align="center" dir="rtl">فهرست به‌روز پروکسی‌های عمومی، تست‌شده با درخواست واقعی و مرتب‌شده بر اساس کشورِ IP خروجی</p>

<p align="center">
  <a href="https://github.com/aradava/proxy-atlas/actions/workflows/proxies.yml"><img src="https://github.com/aradava/proxy-atlas/actions/workflows/proxies.yml/badge.svg?branch=main" alt="وضعیت GitHub Actions"></a>
  <a href="results/manifest.json"><img src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fraw.githubusercontent.com%2Faradava%2Fproxy-atlas%2Fmain%2Fresults%2Fmanifest.json&amp;query=%24.working_proxies&amp;label=%D8%B3%D8%A7%D9%84%D9%85&amp;color=0D9488&amp;labelColor=0B2137&amp;style=flat-square" alt="شمار پروکسی‌های سالم در آخرین انتشار"></a>
  <a href="results/manifest.json"><img src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fraw.githubusercontent.com%2Faradava%2Fproxy-atlas%2Fmain%2Fresults%2Fmanifest.json&amp;query=%24.tested_candidates&amp;label=%D8%AA%D8%B3%D8%AA%E2%80%8C%D8%B4%D8%AF%D9%87&amp;color=156F9E&amp;labelColor=0B2137&amp;style=flat-square" alt="شمار نامزدهای تست‌شده در آخرین انتشار"></a>
</p>

<p align="center" dir="rtl">
  <a href="https://raw.githubusercontent.com/aradava/proxy-atlas/main/results/all.txt"><strong>↓ دریافت فهرست کامل</strong></a>
  &nbsp;·&nbsp;
  <a href="results/countries"><strong>مرور کشورها</strong></a>
  &nbsp;·&nbsp;
  <a href="https://github.com/aradava/proxy-atlas/actions/workflows/proxies.yml">مشاهدهٔ اجراها</a>
</p>

<div dir="rtl">

## دریافت پروکسی‌ها

| خروجی | محتوا |
| --- | --- |
| [فهرست کامل](results/all.txt) | یک آدرس `protocol://IP:port` در هر سطر، به‌ترتیب کمترین زمان پاسخ |
| [به تفکیک کشور](results/countries) | برای هر کد دوحرفی، یک فهرست کامل و فایل‌های موجود به تفکیک پروتکل. `ZZ` یعنی کشور نامشخص |
| [به تفکیک پروتکل](results/protocols) | [HTTP](results/protocols/http.txt) · [HTTPS](results/protocols/https.txt) · [SOCKS4](results/protocols/socks4.txt) · [SOCKS4a](results/protocols/socks4a.txt) · [SOCKS5](results/protocols/socks5.txt) · [SOCKS5h](results/protocols/socks5h.txt) |
| [به تفکیک نوع اتصال](results/modes) | تونل CONNECT، ارسال مستقیم HTTP و تونل SOCKS |
| [دادهٔ JSON](results/proxies.json) | پروتکل، حالت اتصال، IP خروجی، کشور و زمان پاسخ هر تست موفق |
| [گزارش آخرین انتشار](results/manifest.json) | زمان شروع و پایان، شمار نامزدهای یکتا، نتیجهٔ دریافت فیدها و شمار پروکسی‌های سالم هر کشور |

## از گردآوری تا انتشار

1. **گردآوری** از ۱۲۸ فید عمومیِ ۴۴ منتشرکننده و حذف آدرس‌های تکراری. [فهرست منابع](sources.json)
2. **تست موازی** همهٔ نامزدهای یکتا روی GitHub Actions. رانر برای هر پروکسیِ عمومی IPv4 یا IPv6 و بدون اعتبارنامه، از مسیر همان پروکسی درخواست می‌فرستد و پاسخ `HTTP 200` با IP عمومی معتبر را بررسی می‌کند.
3. **دسته‌بندی و انتشار** پس از پایان همهٔ بخش‌ها. کشور بر اساس IP خروجی ثبت می‌شود. اگر یک آدرس در دو حالت از کشورهای متفاوت خارج شود، می‌تواند در هر دو فهرست دیده شود.

در `http://` و `https://` نوع اتصال به خود پروکسی فرق دارد. CONNECT و ارسال مستقیم HTTP جداگانه بررسی می‌شوند. در `https://` اعتبار گواهی خود پروکسی هم بررسی می‌شود. SOCKS4 و SOCKS5 نام مقصد را روی رانر resolve می‌کنند و SOCKS4a و SOCKS5h این کار را به پروکسی می‌سپارند. آزمون HTTP ساده به پاسخ بدون TLS متکی است.

## زمان‌بندی و اجرای دستی

گردش‌کار هر **۲ ساعت** در دقیقهٔ **۴۷ به وقت تهران** اجرا می‌شود. برای اجرای دستی، در **Actions → به‌روزرسانی پروکسی‌ها → Run workflow** شاخهٔ پیش‌فرض را انتخاب کنید. مقدار `limit=0` همهٔ نامزدها را بررسی می‌کند. برای اجرای کوتاه می‌توانید `limit=200` بگذارید و `publish` را خاموش کنید. فایل `proxy-results` در **Artifacts** اجرای موفق قابل دریافت است. [صفحهٔ اجرای اکشن](https://github.com/aradava/proxy-atlas/actions/workflows/proxies.yml)

## اجرای محلی

به پایتون ۳٫۱۱ یا جدیدتر و `curl` نسخهٔ ۸٫۴ یا جدیدتر با قابلیت `HTTPS-proxy` نیاز دارید.

</div>

```bash
git clone https://github.com/aradava/proxy-atlas.git
cd proxy-atlas
python prox.py --limit 500 --workers 32 --timeout 6 --output local-results
```

<div dir="rtl">

برای بررسی همهٔ نامزدها، `python prox.py` را اجرا کنید. خروجی پیش‌فرض در `results/` ذخیره می‌شود. با `--output` می‌توانید مسیر دیگری انتخاب کنید و با `--country-db` می‌توانید یک فایل محلی `CSV.GZ` از DB-IP بدهید. برنامه به‌طور پیش‌فرض پایگاه ماه جاری را دریافت می‌کند و در صورت خطا سراغ ماه قبل می‌رود.

<details>
<summary><strong>افزودن یا تغییر منابع</strong></summary>

در [`sources.json`](sources.json) نام منتشرکننده، صفحهٔ منبع و نشانی فیدهای HTTPS را وارد کنید.

- برای متن با سطرهای `protocol://IP:port`، نشانی فید کافی است. برای سطرهای `IP:port`، فیلد `protocol` را اضافه کنید.
- برای سطرهای `IP:port:Country`، مقدار `format` را `text-with-country` بگذارید.
- برای JSON، مقدار `format` را `json` بگذارید. داده می‌تواند آرایهٔ مستقیم یا آرایه‌ای در `data` یا `proxies` باشد. هر مورد باید `url` یا مجموعهٔ `host`، `port` و `protocol` داشته باشد. `ip` و `ip_address` به‌جای `host` و آرایهٔ `protocols` به‌جای `protocol` هم پذیرفته می‌شوند.

خطای هر فید در گزارش ثبت می‌شود و گردآوری از فیدهای دیگر ادامه پیدا می‌کند.

</details>

دادهٔ جغرافیایی تحت مجوز CC BY 4.0 ارائه شده است. [سرویس تشخیص IP از ipify](https://www.ipify.org/) · [IP Geolocation by DB-IP](https://db-ip.com/db/lite.php)

</div>
