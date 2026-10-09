// Set runtime options before vinext imports Wrangler, on every supported shell.
process.env.WRANGLER_LOG_PATH ??= ".wrangler/wrangler.log";
process.env.WRANGLER_WRITE_LOGS ??= "false";
process.env.MINIFLARE_REGISTRY_PATH ??= ".wrangler/registry";

await import(new URL("./cli.js", import.meta.resolve("vinext")).href);
