<div dir="rtl">

# زمان‌بند Cloudflare برای ProxyAtlas

Worker از API گیت‌هاب دو اکشن موجود را فراخوانی می‌کند. تست اصلی هر دو ساعت و بازتست هر ۱۵ دقیقه درخواست می‌شود. هر دو از همان صف مشترک GitHub عبور می‌کنند.

1. در GitHub یک **Fine-grained personal access token** برای مخزن `aradava/proxy-atlas` بسازید و دسترسی **Actions → Read and write** بدهید. [ساخت توکن محدود](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens#creating-a-fine-grained-personal-access-token)
2. دستورهای زیر را از ریشهٔ مخزن اجرا کنید. مقدار توکن را فقط در ورودی مخفی دستور `secret put` وارد کنید. Wrangler در اولین اجرا برای ساخت Worker تأیید می‌گیرد. [ثبت Secret در Wrangler](https://developers.cloudflare.com/workers/configuration/secrets/)

</div>

```powershell
npx wrangler@4.160.0 login
npx wrangler@4.160.0 secret put GITHUB_ACTIONS_TOKEN --config scheduler/wrangler.toml
npx wrangler@4.160.0 deploy --config scheduler/wrangler.toml
```

<div dir="rtl">

3. در **GitHub Actions** اجراهای با عنوان **تست کامل · Cloudflare** و **بازتست سالم‌ها · Cloudflare** را بررسی کنید. ثبت تغییرات Cron در Cloudflare ممکن است تا ۱۵ دقیقه طول بکشد. [Cron Triggers](https://developers.cloudflare.com/workers/configuration/cron-triggers/)
4. بعد از تأیید هر دو اجرا از Cloudflare، بخش `schedule` را از `proxies.yml` و `recheck.yml` حذف کنید و `workflow_dispatch` را برای اجرای Worker و اجرای دستی نگه دارید.

</div>
