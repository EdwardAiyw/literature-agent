import { loadSettings } from "./config";
import { Engine } from "./engine";
import { LocalJevApp } from "./server";

export { loadSettings } from "./config";
export { Engine } from "./engine";
export { LocalJevApp } from "./server";
export * from "./types";

if (import.meta.main) {
  const settings = loadSettings();
  const app = new LocalJevApp(settings, new Engine(settings));
  const server = Bun.serve({
    hostname: settings.host,
    port: settings.port,
    idleTimeout: 255,
    fetch: (request) => app.fetch(request),
  });

  console.log(`LocalJev listening on ${server.url}`);

  let closing = false;
  const shutdown = async () => {
    if (closing) return;
    closing = true;
    await server.stop();
    await app.close();
    process.exit(0);
  };
  process.on("SIGINT", shutdown);
  process.on("SIGTERM", shutdown);
}
