<div dir="rtl">

# زمان‌بند Cloudflare برای ProxyAtlas

Worker هر ۹۰ دقیقه یک تست کامل با `limit=0` در GitHub Actions ثبت می‌کند. اجرای دستی از همان گردش‌کار و صف استفاده می‌کند.

## به‌روزرسانی Worker موجود از داشبورد

1. در **Edit code** محتوای کامل [worker.mjs](worker.mjs) را جایگزین کنید و **Deploy** بزنید.
2. در **Settings → Trigger Events → Cron Triggers** زمان‌بندی‌های قبلی را حذف کنید و این دو عبارت را جداگانه اضافه کنید.
   - `6 */3 * * *`
   - `36 1-23/3 * * *`
3. Cloudflare ساعت‌های Cron را با UTC می‌خواند. این دو عبارت با هم به‌ترتیب ساعت‌های ۰۰:۰۶، ۰۱:۳۶، ۰۳:۰۶ و به همین شکل تا پایان روز را پوشش می‌دهند. بعد از نوبت بعدی، اجرای **تست کامل · Cloudflare** را در [GitHub Actions](https://github.com/aradava/proxy-atlas/actions/workflows/proxies.yml) بررسی کنید. [مستندات Cron](https://developers.cloudflare.com/workers/configuration/cron-triggers/)

## تست دستی از مرورگر

1. در Cloudflare، Worker فعلی را باز کنید. در **Edit code** محتوای کامل [worker.mjs](worker.mjs) را جایگزین و **Deploy** کنید.
2. در **Settings → Variables and Secrets** یک مقدار از نوع **Secret** با نام `MANUAL_TEST_PASSWORD` بسازید. در **Value** یک رمز تصادفی و بلند وارد کنید. توکن GitHub در Secret فعلی `GITHUB_ACTIONS_TOKEN` می‌ماند. [مدیریت Secret در Cloudflare](https://developers.cloudflare.com/workers/configuration/secrets/#via-the-dashboard)
3. آدرس `workers.dev` همان Worker را باز کنید، رمز تست دستی را وارد کنید و **اجرای تست کامل** را بزنید. صفحه بعد از پذیرش درخواست، لینک اجرای GitHub را نشان می‌دهد.

تست دستی همهٔ نامزدها را بررسی می‌کند و پس از موفقیت، نتیجه در فهرست عمومی پروکسی‌ها منتشر می‌شود.

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

3. بعد از نوبت بعدی، اجرای **تست کامل · Cloudflare** را در [GitHub Actions](https://github.com/aradava/proxy-atlas/actions/workflows/proxies.yml) بررسی کنید. ثبت تغییرات Cron در Cloudflare ممکن است تا ۱۵ دقیقه طول بکشد. [Cron Triggers](https://developers.cloudflare.com/workers/configuration/cron-triggers/)

</div>
