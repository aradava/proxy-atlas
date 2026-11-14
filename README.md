<p align="center">
  <img src=".github/assets/proxy-atlas.webp" alt="نقشهٔ جهان با مسیرهای ارتباطی" width="100%">
</p>

<h1 align="center" dir="rtl">ProxyAtlas · اطلس پروکسی</h1>

<p align="center" dir="rtl">
  پروکسی‌های عمومی را هر ۱۵ دقیقه از همهٔ منابع پروژه گردآوری می‌کنیم و بدون تست اتصال، به تفکیک کشور و پروتکل منتشر می‌کنیم.
</p>

<p align="center" dir="rtl">
  <a href="https://raw.githubusercontent.com/aradava/proxy-atlas/main/results/all.txt"><strong>↓ دریافت فهرست کامل</strong></a>
  &nbsp;·&nbsp;
  <a href="results/countries"><strong>مرور کشورها</strong></a>
  &nbsp;·&nbsp;
  <a href="results/manifest.json"><strong>گزارش آخرین انتشار</strong></a>
</p>

<p align="center">
  <a href="https://github.com/aradava/proxy-atlas/actions/workflows/proxies.yml"><img src="https://github.com/aradava/proxy-atlas/actions/workflows/proxies.yml/badge.svg?branch=main" alt="وضعیت گردآوری"></a>
  <a href="results/manifest.json"><img src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fraw.githubusercontent.com%2Faradava%2Fproxy-atlas%2Fmain%2Fresults%2Fmanifest.json&amp;query=%24.collected_proxies&amp;label=collected&amp;color=0D9488&amp;labelColor=0B2137&amp;style=flat-square" alt="شمار آدرس‌های گردآوری‌شده در آخرین انتشار"></a>
</p>

<div dir="rtl">

## 🧭 فهرست‌ها و گزارش‌ها

| خروجی | چه چیزی در آن هست؟ |
| --- | --- |
| [همهٔ پروکسی‌ها](https://raw.githubusercontent.com/aradava/proxy-atlas/main/results/all.txt) | یک آدرس `protocol://IP:port` در هر سطر |
| [کشورها](results/countries) | فهرست هر کشور بر اساس IP سرور پروکسی |
| [پروتکل‌ها](results/protocols) | [HTTP](results/protocols/http.txt) · [HTTPS](results/protocols/https.txt) · [SOCKS4](results/protocols/socks4.txt) · [SOCKS4a](results/protocols/socks4a.txt) · [SOCKS5](results/protocols/socks5.txt) · [SOCKS5h](results/protocols/socks5h.txt) |
| [خروجی JSON](results/proxies.json) | آدرس، پروتکل ثبت‌شده در فید و کشور سرور |
| [گزارش آخرین انتشار](results/manifest.json) | شمار آدرس‌های گردآوری‌شده، زمان اجرا و وضعیت هر فید |

## از فید تا فهرست عمومی

1. **دریافت منابع.** آدرس‌ها از فایل‌های متنی، JSON، CSV و جدول‌های عمومی خوانده می‌شوند. برای خطاهای موقت دانلود دوباره تلاش می‌کنیم. گزارش هر اجرا فیدهای خالی، خطاهای دانلود و خطاهای قالب را جداگانه نشان می‌دهد. [منابع پروژه](sources.json)
2. **حذف تکراری‌ها و دسته‌بندی.** هر ترکیب یکتای IP، پورت و پروتکل یک بار در فهرست می‌آید. کشور با استفاده از IP سرور و پایگاه DB-IP تعیین می‌شود.
3. **انتشار.** فهرست گردآوری‌شده از فیدهای همان اجرا بدون سقف و بدون تست اتصال جای فهرست قبلی را می‌گیرد. [فهرست منتشرشده](results/)

## گردآوری هر ۱۵ دقیقه

زمان‌بند GitHub Actions به‌طور پیش‌فرض هر ۱۵ دقیقه گردآوری را شروع می‌کند. اجراهای دستی و خودکار به‌نوبت از یک صف عبور می‌کنند. [گردش‌کار گردآوری](https://github.com/aradava/proxy-atlas/actions/workflows/proxies.yml)

---

دادهٔ کشور از DB-IP تحت مجوز CC BY 4.0 می‌آید. کد `ZZ` در فایل‌ها به معنی کشور نامشخص است. [DB-IP Country Lite](https://db-ip.com/db/lite.php)

</div>
