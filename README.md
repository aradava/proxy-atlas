<p align="center">
  <img src=".github/assets/proxy-atlas.webp" alt="نقشهٔ جهان با مسیرهای ارتباطی" width="100%">
</p>

<h1 align="center" dir="rtl">ProxyAtlas · اطلس پروکسی</h1>

<p align="center" dir="rtl">
  پروکسی‌های عمومی را از ۲۱۸ فید جمع می‌کنیم، اتصالشان را می‌سنجیم و سالم‌های هر اجرا را با کشور خروجی و زمان پاسخ منتشر می‌کنیم.
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
  <a href="results/manifest.json"><img src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fraw.githubusercontent.com%2Faradava%2Fproxy-atlas%2Fmain%2Fresults%2Fmanifest.json&amp;query=%24.working_proxies&amp;label=%D8%B3%D8%A7%D9%84%D9%85%20%D8%AF%D8%B1%20%D8%A2%D8%AE%D8%B1%DB%8C%D9%86%20%D8%A7%D9%86%D8%AA%D8%B4%D8%A7%D8%B1&amp;color=0D9488&amp;labelColor=0B2137&amp;style=flat-square" alt="شمار پروکسی‌های سالم در آخرین انتشار"></a>
</p>

<div dir="rtl">

## 🧭 فهرست‌ها و گزارش‌ها

| خروجی | چه چیزی در آن هست؟ |
| --- | --- |
| [همهٔ پروکسی‌ها](https://raw.githubusercontent.com/aradava/proxy-atlas/main/results/all.txt) | یک آدرس `protocol://IP:port` در هر سطر، مرتب از کمترین زمان پاسخ |
| [کشورها](results/countries) | فهرست هر کشور بر اساس IP خروجی یا، اگر در پاسخ نیامده باشد، IP سرور پروکسی |
| [پروتکل‌ها](results/protocols) | [HTTP](results/protocols/http.txt) · [HTTPS](results/protocols/https.txt) · [SOCKS4](results/protocols/socks4.txt) · [SOCKS4a](results/protocols/socks4a.txt) · [SOCKS5](results/protocols/socks5.txt) · [SOCKS5h](results/protocols/socks5h.txt) |
| [حالت‌های اتصال](results/modes) | فهرست‌های جداگانه برای تونل CONNECT، ارسال مستقیم HTTP و تونل SOCKS |
| [جزئیات هر نتیجه](results/proxies.json) | آدرس، پروتکل، حالت اتصال، IP خروجی در صورت دریافت، مبنای کشور و زمان پاسخ بر حسب میلی‌ثانیه |
| [گزارش آخرین انتشار](results/manifest.json) | زمان شروع و پایان، تعداد نامزدهای تست‌شده، سالم‌ها، دلیل رد شدن آزمون‌ها و شمارش به تفکیک کشور |

## از فید تا فهرست عمومی

1. **گردآوری از ۷۴ منتشرکننده.** نامزدها را از فایل‌های متنی، JSON، CSV و جدول‌های عمومی می‌خوانیم و با سالم‌های آخرین تست کامل ترکیب می‌کنیم. آدرس، پورت و پروتکل تعیین می‌کنند کدام موارد تکراری‌اند. خطای هر فید در گزارش تست کامل ثبت می‌شود و جمع‌آوری از فیدهای دیگر ادامه پیدا می‌کند. [منابع پروژه](sources.json)
2. **تقسیم و تست موازی.** GitHub Actions همهٔ نامزدهای یکتا را بین چند رانر تقسیم می‌کند. هر رانر درخواست‌ها را گروهی اجرا می‌کند و اگر یک گروه نیمه‌تمام بماند، فقط درخواست‌های بی‌نتیجه را دوباره می‌فرستد. [گردش‌کار تست](.github/workflows/proxies.yml)
3. **سنجش روش‌های اتصال.** برای تونل CONNECT و SOCKS، دریافت پاسخ از مقصد HTTPS با گواهی معتبر برای قبولی کافی است، حتی اگر سرویس مقصد IP خروجی را برنگرداند. در تست ارسال مستقیم HTTP، پاسخ باید شناسهٔ همان درخواست و IP خروجی معتبر داشته باشد. [منطق تست](prox.py)
4. **ادغام و انتشار.** پس از پایان بخش‌ها، نتیجه‌ها را بر اساس زمان پاسخ منتشر می‌کنیم. اگر مقصد IP خروجی را برنگرداند، فیلد `exit_ip` خالی است و کشور از IP سرور پروکسی تخمین زده می‌شود. هر خروجی به تست همان اجرا متکی است. [فهرست منتشرشده](results/)

> در یکی از تست‌های کامل ثبت‌شده، **۱۲۶٬۴۸۵ نامزد** بررسی شدند. [گزارش همان تست](https://github.com/aradava/proxy-atlas/blob/4a4805292d7e841c8746b65d5032bb95a26e7186/results/manifest.json)

## تست کامل هر ۹۰ دقیقه

Cloudflare هر ۹۰ دقیقه تست کامل را در GitHub Actions ثبت می‌کند. این گردش‌کار فیدها را دوباره می‌خواند، همهٔ نامزدهای یکتا و سالم‌های آخرین تست را می‌سنجد و نتیجه را در فهرست عمومی منتشر می‌کند. درخواست‌های خودکار و دستی به‌نوبت از یک صف عبور می‌کنند. [گردش‌کار تست کامل](https://github.com/aradava/proxy-atlas/actions/workflows/proxies.yml)

[فهرست مبنا](full-scan/all.txt) سالم‌های آخرین تست کامل را نگه می‌دارد. حتی اگر آدرسی در فیدهای نوبت بعد دیده نشود، از فهرست مبنا وارد تست می‌شود.

---

سنجش IP خروجی با ipify و تشخیص کشور با دادهٔ DB-IP تحت مجوز CC BY 4.0 انجام می‌شود. کد `ZZ` در فایل‌ها به معنی کشور نامشخص است. [ipify](https://www.ipify.org/) · [DB-IP Country Lite](https://db-ip.com/db/lite.php)

</div>
