<p align="center">
  <img src=".github/assets/proxy-atlas.webp" alt="نقشهٔ جهان با مسیرهای ارتباطی" width="100%">
</p>

<h1 align="center" dir="rtl">ProxyAtlas · اطلس پروکسی</h1>

<p align="center" dir="rtl">
  پروکسی‌های عمومی را از ۱۲۸ فید جمع می‌کنیم، اتصالشان را می‌سنجیم و سالم‌های هر اجرا را با کشور خروجی و زمان پاسخ منتشر می‌کنیم.
</p>

<p align="center" dir="rtl">
  <a href="https://raw.githubusercontent.com/aradava/proxy-atlas/main/results/all.txt"><strong>↓ دریافت فهرست کامل</strong></a>
  &nbsp;·&nbsp;
  <a href="results/countries"><strong>مرور کشورها</strong></a>
  &nbsp;·&nbsp;
  <a href="results/manifest.json"><strong>گزارش آخرین انتشار</strong></a>
</p>

<p align="center">
  <a href="https://github.com/aradava/proxy-atlas/actions/workflows/proxies.yml"><img src="https://github.com/aradava/proxy-atlas/actions/workflows/proxies.yml/badge.svg?branch=main" alt="وضعیت تست کامل"></a>
  <a href="https://github.com/aradava/proxy-atlas/actions/workflows/recheck.yml"><img src="https://github.com/aradava/proxy-atlas/actions/workflows/recheck.yml/badge.svg?branch=main" alt="وضعیت بازتست سالم‌ها"></a>
  <a href="results/manifest.json"><img src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fraw.githubusercontent.com%2Faradava%2Fproxy-atlas%2Fmain%2Fresults%2Fmanifest.json&amp;query=%24.working_proxies&amp;label=%D8%B3%D8%A7%D9%84%D9%85%20%D8%AF%D8%B1%20%D8%A2%D8%AE%D8%B1%DB%8C%D9%86%20%D8%A7%D9%86%D8%AA%D8%B4%D8%A7%D8%B1&amp;color=0D9488&amp;labelColor=0B2137&amp;style=flat-square" alt="شمار پروکسی‌های سالم در آخرین انتشار"></a>
</p>

<div dir="rtl">

## 🧭 فهرست‌ها و گزارش‌ها

| خروجی | چه چیزی در آن هست؟ |
| --- | --- |
| [همهٔ پروکسی‌ها](https://raw.githubusercontent.com/aradava/proxy-atlas/main/results/all.txt) | یک آدرس `protocol://IP:port` در هر سطر، مرتب از کمترین زمان پاسخ |
| [کشورها](results/countries) | فهرست هر کشور بر اساس IP خروجی، با فایل‌های جداگانه برای پروتکل‌های موجود |
| [پروتکل‌ها](results/protocols) | [HTTP](results/protocols/http.txt) · [HTTPS](results/protocols/https.txt) · [SOCKS4](results/protocols/socks4.txt) · [SOCKS4a](results/protocols/socks4a.txt) · [SOCKS5](results/protocols/socks5.txt) · [SOCKS5h](results/protocols/socks5h.txt) |
| [حالت‌های اتصال](results/modes) | فهرست‌های جداگانه برای تونل CONNECT، ارسال مستقیم HTTP و تونل SOCKS |
| [جزئیات هر نتیجه](results/proxies.json) | آدرس پروکسی، پروتکل، حالت اتصال، IP خروجی، کشور و زمان پاسخ بر حسب میلی‌ثانیه |
| [گزارش آخرین انتشار](results/manifest.json) | زمان شروع و پایان، تعداد نامزدهای تست‌شده، سالم‌ها و شمارش به تفکیک کشور |

## از فید تا فهرست عمومی

1. **گردآوری از ۴۴ منتشرکننده.** نامزدهای تازه را با سالم‌های آخرین تست کامل ترکیب می‌کنیم. آدرس، پورت و پروتکل تعیین می‌کنند کدام موارد تکراری‌اند. خطای هر فید در گزارش تست کامل ثبت می‌شود و جمع‌آوری از فیدهای دیگر ادامه پیدا می‌کند. [منابع پروژه](sources.json)
2. **تقسیم و تست موازی.** GitHub Actions نامزدهای یکتا را بین چند رانر تقسیم می‌کند. هر رانر از مسیر خود پروکسی درخواست می‌فرستد. آزمون وقتی موفق است که مقصد با `HTTP 200` و یک IP عمومی معتبر پاسخ دهد. [گردش‌کار تست](.github/workflows/proxy-pipeline.yml)
3. **سنجش روش‌های اتصال.** برای HTTP و HTTPS، تونل CONNECT و ارسال مستقیم HTTP جداگانه تست می‌شوند. برای SOCKS، ارتباط تونلی سنجیده می‌شود. در نتیجه می‌شود دید یک آدرس دقیقاً در کدام حالت کار کرده است. [منطق تست](prox.py)
4. **ادغام و انتشار.** پس از پایان بخش‌ها، نتیجه‌ها را ادغام می‌کنیم، کشور را از IP خروجی پیدا می‌کنیم و آدرس‌های سالم را بر اساس زمان پاسخ در فهرست عمومی منتشر می‌کنیم. هر خروجی به تست همان اجرا متکی است. [فهرست منتشرشده](results/)

> در یکی از تست‌های کامل ثبت‌شده، **۱۲۶٬۴۸۵ نامزد** بررسی شدند و **۸٬۸۵۱ پروکسی سالم** با خروجی در **۱۰۹ کد کشور مشخص** به دست آمد. [گزارش همان تست](https://github.com/aradava/proxy-atlas/blob/4a4805292d7e841c8746b65d5032bb95a26e7186/results/manifest.json)

## دو نوبت برای تازه نگه‌داشتن فهرست

| نوبت | برنامه | چه کاری انجام می‌دهد؟ |
| --- | --- | --- |
| [تست کامل](https://github.com/aradava/proxy-atlas/actions/workflows/proxies.yml) | هر **۲ ساعت** | فیدها را دوباره می‌خواند و همهٔ نامزدهای تازه و سالم‌های آخرین تست کامل را می‌سنجد. |
| [بازتست سالم‌ها](https://github.com/aradava/proxy-atlas/actions/workflows/recheck.yml) | هر **۱۵ دقیقه** | سالم‌های آخرین تست کامل را دوباره می‌سنجد و فهرست عمومی را با مواردی که هنوز پاسخ می‌دهند به‌روز می‌کند. |

Cloudflare درخواست اجرا را به GitHub Actions می‌فرستد. هر دو گردش‌کار در یک صف مشترک به‌نوبت اجرا می‌شوند. اگر آخرین انتشار حاصل تست همهٔ نامزدهای آن اجرا باشد و از پایان تست کمتر از سه دقیقه گذشته باشد، آن نوبت بازتست رد می‌شود. [زمان‌بند پروژه](scheduler/worker.mjs) · [منطق بازتست](actions_pipeline.py)

[فهرست مبنا](full-scan/all.txt) سالم‌های آخرین تست کامل را نگه می‌دارد. اگر یک پروکسی در بازتست موقتاً از دسترس خارج شود، در نوبت بعد دوباره فرصت تست دارد و با پاسخ موفق به فهرست عمومی برمی‌گردد.

---

سنجش IP خروجی با ipify و تشخیص کشور با دادهٔ DB-IP تحت مجوز CC BY 4.0 انجام می‌شود. کد `ZZ` در فایل‌ها به معنی کشور نامشخص است. [ipify](https://www.ipify.org/) · [DB-IP Country Lite](https://db-ip.com/db/lite.php)

</div>
