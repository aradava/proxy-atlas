const repository = "aradava/proxy-atlas";
const branch = "main";
const schedules = new Map([
  ["6 */2 * * *", { workflow: "proxies.yml", inputs: { limit: 0 } }],
  ["13,28,43,58 * * * *", { workflow: "recheck.yml", inputs: {} }],
]);

export default {
  async scheduled(controller, env) {
    const schedule = schedules.get(controller.cron);
    if (!schedule) {
      throw new Error(`Unknown cron trigger: ${controller.cron}`);
    }
    if (!env.GITHUB_ACTIONS_TOKEN) {
      throw new Error("The GITHUB_ACTIONS_TOKEN secret is required");
    }

    const url = `https://api.github.com/repos/${repository}/actions/workflows/${schedule.workflow}/dispatches`;
    const response = await fetch(url, {
      method: "POST",
      redirect: "error",
      signal: AbortSignal.timeout(15_000),
      headers: {
        "Accept": "application/vnd.github+json",
        "Authorization": `Bearer ${env.GITHUB_ACTIONS_TOKEN}`,
        "Content-Type": "application/json",
        "User-Agent": "ProxyAtlas-Scheduler",
        "X-GitHub-Api-Version": "2026-03-10",
      },
      body: JSON.stringify({
        ref: branch,
        inputs: { ...schedule.inputs, automation: true, publish: true },
      }),
    });

    if (!response.ok) {
      throw new Error(`GitHub rejected ${schedule.workflow} with HTTP ${response.status}`);
    }

    const details = response.status === 200 ? await response.json() : {};
    console.log(JSON.stringify({
      workflow: schedule.workflow,
      scheduled_at: new Date(controller.scheduledTime).toISOString(),
      github_run_id: details.workflow_run_id,
      github_run_url: details.html_url,
    }));
  },
};
