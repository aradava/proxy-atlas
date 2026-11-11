const repository = "aradava/proxy-atlas";
const workflows = new Map([
  ["recheck", { file: "recheck.yml", inputs: {} }],
  ["full", { file: "proxies.yml", inputs: { limit: 0 } }],
]);
const schedules = new Map([
  ["6 */2 * * *", "full"],
  ["13,28,43,58 * * * *", "recheck"],
]);

const responseHeaders = {
  "Cache-Control": "no-store",
  "Referrer-Policy": "no-referrer",
  "X-Content-Type-Options": "nosniff",
};

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/" && request.method === "GET") {
      const nonce = crypto.randomUUID();
      return new Response(dashboard(nonce, Boolean(env.MANUAL_TEST_PASSWORD)), {
        headers: {
          ...responseHeaders,
          "Content-Type": "text/html; charset=utf-8",
          "Content-Security-Policy": [
            "default-src 'none'",
            "script-src 'nonce-" + nonce + "'",
            "style-src 'nonce-" + nonce + "'",
            "connect-src 'self'",
            "base-uri 'none'",
            "frame-ancestors 'none'",
            "form-action 'self'",
          ].join("; "),
        },
      });
    }
    if (url.pathname === "/favicon.ico" && request.method === "GET") {
      return new Response(null, { status: 204, headers: responseHeaders });
    }
    if (url.pathname === "/run" && request.method === "POST") {
      return runManualTest(request, env, url.origin);
    }
    return new Response("Not found", { status: 404, headers: responseHeaders });
  },

  async scheduled(controller, env) {
    const workflow = workflows.get(schedules.get(controller.cron));
    if (!workflow) {
      throw new Error(`Unknown cron trigger: ${controller.cron}`);
    }
    if (!env.GITHUB_ACTIONS_TOKEN) {
      throw new Error("The GITHUB_ACTIONS_TOKEN secret is required");
    }

    const result = await dispatchWorkflow(workflow, env.GITHUB_ACTIONS_TOKEN, {
      automation: true,
      publish: true,
    });
    if (!result.ok) {
      const detail = result.message ? `: ${result.message}` : "";
      throw new Error(`GitHub rejected ${workflow.file} with HTTP ${result.status}${detail}`);
    }

    console.log(JSON.stringify({
      trigger: "cron",
      workflow: workflow.file,
      scheduled_at: new Date(controller.scheduledTime).toISOString(),
      github_run_id: result.runId,
      github_run_url: result.runUrl,
    }));
  },
};

async function runManualTest(request, env, origin) {
  if (request.headers.get("Origin") !== origin) {
    return json({ message: "درخواست باید از همین صفحه ارسال شود." }, 403);
  }
  if (!env.MANUAL_TEST_PASSWORD) {
    return json({ message: "Secret با نام MANUAL_TEST_PASSWORD تنظیم نشده است." }, 503);
  }
  if (Number(request.headers.get("Content-Length")) > 2048) {
    return json({ message: "حجم درخواست بیش از حد مجاز است." }, 413);
  }

  const input = await request.json().catch(() => null);
  const workflow = workflows.get(input?.workflow);
  const password = input?.password;
  if (!workflow || typeof password !== "string" || password.length > 256) {
    return json({ message: "درخواست تست معتبر نیست." }, 400);
  }

  const encoder = new TextEncoder();
  const [submitted, expected] = await Promise.all([
    crypto.subtle.digest("SHA-256", encoder.encode(password)),
    crypto.subtle.digest("SHA-256", encoder.encode(env.MANUAL_TEST_PASSWORD)),
  ]);
  if (!crypto.subtle.timingSafeEqual(submitted, expected)) {
    return json({ message: "رمز تست دستی اشتباه است." }, 401);
  }
  if (!env.GITHUB_ACTIONS_TOKEN) {
    return json({ message: "Secret با نام GITHUB_ACTIONS_TOKEN تنظیم نشده است." }, 503);
  }

  const workflowUrl = `https://github.com/${repository}/actions/workflows/${workflow.file}`;
  try {
    const result = await dispatchWorkflow(workflow, env.GITHUB_ACTIONS_TOKEN, {
      automation: false,
      publish: true,
    });
    if (!result.ok) {
      return json({
        message: `گیت‌هاب درخواست را رد کرد (HTTP ${result.status}).${result.message ? " " + result.message : ""}`,
        runUrl: workflowUrl,
      }, 502);
    }

    console.log(JSON.stringify({
      trigger: "manual",
      workflow: workflow.file,
      github_run_id: result.runId,
      github_run_url: result.runUrl,
    }));

    return json({
      message: "گیت‌هاب درخواست تست را پذیرفت. وضعیت صف و نتیجه را در GitHub Actions ببین.",
      runUrl: result.runUrl ?? workflowUrl,
      runId: result.runId,
    }, 202);
  } catch {
    return json({
      message: "پاسخ گیت‌هاب دریافت نشد. پیش از تکرار، تاریخچهٔ اجراها را بررسی کن.",
      runUrl: workflowUrl,
    }, 502);
  }
}

async function dispatchWorkflow(workflow, token, { automation, publish }) {
  const url = `https://api.github.com/repos/${repository}/actions/workflows/${workflow.file}/dispatches`;
  const inputs = Object.fromEntries(
    Object.entries({ ...workflow.inputs, automation, publish })
      .map(([name, value]) => [name, String(value)]),
  );
  const response = await fetch(url, {
    method: "POST",
    redirect: "manual",
    signal: AbortSignal.timeout(15_000),
    headers: {
      "Accept": "application/vnd.github+json",
      "Authorization": `Bearer ${token}`,
      "Content-Type": "application/json",
      "User-Agent": "ProxyAtlas-Scheduler",
      "X-GitHub-Api-Version": "2026-03-10",
    },
    body: JSON.stringify({ ref: "main", inputs }),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => null);
    const message = [error?.message, error?.errors?.[0]?.message]
      .filter((value) => typeof value === "string")
      .join(" ")
      .replaceAll(token, "[redacted]")
      .slice(0, 500);
    return { ok: false, status: response.status, message };
  }

  const details = response.status === 200 ? await response.json().catch(() => null) : null;
  const runId = details?.workflow_run_id;
  const runUrl = Number.isSafeInteger(runId) && runId > 0
    ? `https://github.com/${repository}/actions/runs/${runId}`
    : undefined;
  return { ok: true, runId, runUrl };
}

function json(data, status) {
  return Response.json(data, { status, headers: responseHeaders });
}

function dashboard(nonce, manualEnabled) {
  return `<!doctype html>
<html lang="fa" dir="rtl">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="dark">
  <title>تست دستی پروکسی‌ها | ProxyAtlas</title>
  <style nonce="${nonce}">
    :root {
      font-family: Tahoma, "Segoe UI", sans-serif;
      color-scheme: dark;
      color: #eaf2f8;
      background: #0b141c;
      --muted: #a9bac8;
      --mint: #89efd5;
      --border: #2a3b48;
    }
    * { box-sizing: border-box; }
    body { margin: 0; }
    a { color: var(--mint); text-underline-offset: .25em; }
    button, input { font: inherit; }
    [hidden] { display: none !important; }
    :focus-visible { outline: 2px solid var(--mint); outline-offset: 4px; }
    .shell { width: min(880px, calc(100% - 40px)); margin: 0 auto; }
    .topbar {
      display: flex; align-items: center; justify-content: space-between;
      gap: 1rem; min-height: 82px;
    }
    .brand {
      display: inline-flex; align-items: center; gap: .75rem;
      font: 700 1.12rem "Segoe UI", sans-serif; letter-spacing: -.025em;
    }
    .brand-mark {
      display: grid; place-items: center; width: 34px; height: 34px;
      border-radius: 9px; border: 1px solid #3d796f; background: #183b3a;
    }
    .brand-mark::before {
      content: ""; width: 11px; height: 11px; transform: rotate(45deg);
      border: 2px solid var(--mint); border-radius: 2px;
    }
    .topbar a { font-size: .83rem; }
    .panel {
      overflow: hidden; border: 1px solid var(--border);
      border-radius: 22px; background: #111f2a;
    }
    .intro {
      position: relative; overflow: hidden; padding: 2.4rem 2rem 2.15rem;
      border-bottom: 1px solid var(--border);
      background:
        radial-gradient(ellipse at left top, #1a493e 0%, transparent 67%),
        linear-gradient(125deg, #10222d, #142e35);
    }
    .intro::after {
      position: absolute; inset: 0 52% 0 0; content: ""; pointer-events: none;
      background-image:
        linear-gradient(#95ffe314 1px, transparent 1px),
        linear-gradient(90deg, #95ffe314 1px, transparent 1px);
      background-size: 23px 23px;
      mask-image: linear-gradient(90deg, #000 10%, transparent);
    }
    h1 { font-size: clamp(1.65rem, 5vw, 2.65rem); margin: 0 0 .65rem; }
    p { margin: 0; line-height: 1.85; }
    .intro p, .description { color: var(--muted); }
    form { padding: 1.65rem 2rem 2rem; }
    fieldset { margin: 0; padding: 0; border: 0; min-width: 0; }
    label { display: block; font-size: .91rem; font-weight: 700; margin-bottom: .6rem; }
    input {
      width: min(100%, 360px); min-height: 46px; padding: .65rem .85rem;
      border: 1px solid var(--border); border-radius: 9px; background: #0b1720;
      color: inherit;
    }
    .actions {
      display: grid; grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: .9rem; margin-top: 1.45rem;
    }
    .action {
      display: flex; flex-direction: column; gap: .6rem; padding: 1.15rem;
      border-radius: 13px; border: 1px solid var(--border); background: #162632;
    }
    .action:first-child { border-color: #386158; }
    .action h2 { font-size: 1.03rem; margin: 0; }
    .action p { font-size: .82rem; }
    button {
      margin-top: auto; min-height: 43px; cursor: pointer;
      border: 1px solid #496677; border-radius: 8px; padding: .6rem .9rem;
      background: #1e3442; color: #edf6fb; font-weight: 700; font-size: .86rem;
    }
    button:hover:not(:disabled) { background: #284455; }
    .primary { background: var(--mint); color: #092621; border-color: var(--mint); }
    .primary:hover:not(:disabled) { background: #b1fae7; }
    :disabled { cursor: not-allowed; opacity: .58; }
    .notice {
      margin-top: 1rem; padding: .75rem .9rem; border: 1px solid #385d57;
      border-radius: 8px; background: #15302e; overflow-wrap: anywhere;
      font-size: .87rem;
    }
    .notice[data-tone="error"] { border-color: #89565d; background: #342428; }
    .notice a { display: inline-block; margin-top: .3rem; }
    code { direction: ltr; unicode-bidi: isolate; }
    footer { padding: 1rem 0 2rem; color: var(--muted); font-size: .8rem; }
    @media (max-width: 570px) {
      .shell { width: calc(100% - 28px); }
      .topbar { min-height: 66px; }
      .intro, form { padding: 1.25rem; }
      .actions { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <div class="shell">
    <header class="topbar">
      <span class="brand" dir="ltr"><span class="brand-mark" aria-hidden="true"></span>ProxyAtlas</span>
      <a href="https://github.com/${repository}/actions">تاریخچهٔ اجراها در GitHub</a>
    </header>
    <main class="panel">
      <div class="intro">
        <h1>تست دستی پروکسی‌ها</h1>
        <p>اکشن را همین حالا از Cloudflare به صف GitHub بفرست.</p>
      </div>
      <form id="test-form" method="post" action="/run" autocomplete="off">
        <fieldset id="controls"${manualEnabled ? "" : " disabled"}>
          <label for="password">رمز تست دستی</label>
          <input id="password" type="password" maxlength="256" dir="ltr" required>
          <div class="actions">
            <div class="action">
              <h2>بازتست سالم‌ها</h2>
              <p class="description">پروکسی‌های سالم آخرین تست کامل دوباره بررسی می‌شوند.</p>
              <button class="primary" type="submit" value="recheck">اجرای بازتست</button>
            </div>
            <div class="action">
              <h2>تست کامل</h2>
              <p class="description">همهٔ نامزدها از منابع گردآوری و بدون سقف بررسی می‌شوند.</p>
              <button type="submit" value="full">اجرای تست کامل</button>
            </div>
          </div>
        </fieldset>
        ${manualEnabled ? "" : '<p class="notice">برای فعال‌کردن دکمه‌ها، Secret با نام <code>MANUAL_TEST_PASSWORD</code> را در Cloudflare اضافه کن.</p>'}
        <div id="result" class="notice" hidden>
          <p id="message" role="status" aria-live="polite"></p>
          <a id="run-link" hidden>مشاهده در GitHub Actions</a>
        </div>
      </form>
    </main>
    <footer>نتیجهٔ تست دستی در فهرست عمومی پروکسی‌ها در GitHub منتشر می‌شود.</footer>
  </div>
  <script nonce="${nonce}">
    const form = document.querySelector("#test-form");
    const controls = document.querySelector("#controls");
    const password = document.querySelector("#password");
    const result = document.querySelector("#result");
    const message = document.querySelector("#message");
    const runLink = document.querySelector("#run-link");

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (controls.disabled) return;

      const workflow = event.submitter?.value || "recheck";
      const body = JSON.stringify({ workflow, password: password.value });
      controls.disabled = true;
      result.hidden = false;
      result.dataset.tone = "info";
      runLink.hidden = true;
      message.textContent = "در حال ارسال درخواست به GitHub…";

      try {
        const response = await fetch("/run", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body,
        });
        const data = await response.json();
        result.dataset.tone = response.ok ? "info" : "error";
        message.textContent = data.message;
        if (data.runUrl) {
          runLink.href = data.runUrl;
          runLink.hidden = false;
        }
      } catch {
        result.dataset.tone = "error";
        message.textContent = "ارتباط قطع شد. پیش از تکرار، تاریخچهٔ اجراها را در GitHub بررسی کن.";
      } finally {
        controls.disabled = false;
      }
    });
  </script>
</body>
</html>`;
}
