<div dir="rtl">

# زمان‌بند Cloudflare برای ProxyAtlas

زمان‌بند پیش‌فرض پروژه GitHub Actions است. برای استفاده از Cloudflare، Worker را با Cron پانزده‌دقیقه‌ای راه‌اندازی کنید و متغیر `PROXY_SCHEDULER` را تنظیم کنید. هر اجرا همهٔ فیدها را با `limit=0` می‌خواند و فهرست را بدون تست اتصال منتشر می‌کند.

## به‌روزرسانی Worker موجود از داشبورد

1. در **Edit code** محتوای کامل [worker.mjs](worker.mjs) را جایگزین کنید و **Deploy** بزنید.
2. در **Settings → Trigger Events → Cron Triggers** زمان‌بندی‌های قبلی را حذف کنید و `6,21,36,51 * * * *` را اضافه کنید. Cloudflare هر ساعت در دقیقه‌های ۰۶، ۲۱، ۳۶ و ۵۱ به وقت UTC اجرا می‌شود. [مستندات Cron](https://developers.cloudflare.com/workers/configuration/cron-triggers/)
3. در GitHub به **Settings → Secrets and variables → Actions → Variables** بروید و متغیر مخزن `PROXY_SCHEDULER` را با مقدار `cloudflare` بسازید تا فقط زمان‌بند Cloudflare گردآوری خودکار را شروع کند. بعد از نوبت بعدی، اجرای **گردآوری پروکسی‌ها · Cloudflare** را در [GitHub Actions](https://github.com/aradava/proxy-atlas/actions/workflows/proxies.yml) بررسی کنید.

## گردآوری دستی از مرورگر

1. در Cloudflare، Worker فعلی را باز کنید. در **Edit code** محتوای کامل [worker.mjs](worker.mjs) را جایگزین و **Deploy** کنید.
2. در **Settings → Variables and Secrets** یک مقدار از نوع **Secret** با نام `MANUAL_TEST_PASSWORD` بسازید. در **Value** یک رمز تصادفی و بلند وارد کنید. توکن GitHub در Secret فعلی `GITHUB_ACTIONS_TOKEN` می‌ماند. [مدیریت Secret در Cloudflare](https://developers.cloudflare.com/workers/configuration/secrets/#via-the-dashboard)
3. آدرس `workers.dev` همان Worker را باز کنید، رمز اجرای دستی را وارد کنید و **گردآوری فهرست** را بزنید. صفحه بعد از پذیرش درخواست، لینک اجرای GitHub را نشان می‌دهد.

اجرای دستی فیدها را دوباره می‌خواند و فهرست تازه را در GitHub منتشر می‌کند.

## راه‌اندازی با Wrangler

1. در GitHub یک **Fine-grained personal access token** برای مخزن `aradava/proxy-atlas` بسازید و دسترسی **Actions → Read and write** بدهید. [ساخت توکن محدود](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens#creating-a-fine-grained-personal-access-token)
2. دستورهای زیر را از ریشهٔ مخزن اجرا کنید. مقدار توکن را فقط در ورودی مخفی دستور `secret put` وارد کنید. Wrangler در اولین اجرا برای ساخت Worker تأیید می‌گیرد. [ثبت Secret در Wrangler](https://developers.cloudflare.com/workers/configuration/secrets/)

</div>

```powershell
npx wrangler@4.160.0 login
npx wrangler@4.160.0 secret put GITHUB_ACTIONS_TOKEN --config scheduler/wrangler.toml
npx wrangler@4.160.0 secret put MANUAL_TEST_PASSWORD --config scheduler/wrangler.toml
npx wrangler@4.160.0 deploy --config scheduler/wrangler.toml
```

<div dir="rtl">

3. متغیر مخزن `PROXY_SCHEDULER` را در GitHub با مقدار `cloudflare` تنظیم کنید و اجرای بعدی را در [GitHub Actions](https://github.com/aradava/proxy-atlas/actions/workflows/proxies.yml) بررسی کنید. ثبت تغییرات Cron در Cloudflare ممکن است تا ۱۵ دقیقه طول بکشد. [Cron Triggers](https://developers.cloudflare.com/workers/configuration/cron-triggers/)

</div>
