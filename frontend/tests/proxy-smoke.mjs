import assert from "node:assert/strict";
import { createServer as createHttpServer } from "node:http";
import { fileURLToPath } from "node:url";

import { JSDOM } from "jsdom";
import { createServer as createViteServer } from "vite";

const backend = createHttpServer((request, response) => {
  if (request.url === "/api/v1/dialogs" && request.method === "POST") {
    response.writeHead(201, { "Content-Type": "application/json" });
    response.end(JSON.stringify({ dialog_id: "fake-dialog" }));
  } else if (request.url === "/api/v1/dialogs/fake-dialog/events") {
    response.writeHead(200, { "Content-Type": "text/event-stream" });
    response.write("event: ready\ndata: {}\n\n");
    response.write('event: message_delta\ndata: {"delta":"Привет"}\n\n');
    response.end('event: message_delta\ndata: {"delta":", Крош!"}\n\n');
  } else {
    response.writeHead(404);
    response.end();
  }
});

await new Promise(resolve => backend.listen(0, "127.0.0.1", resolve));
process.env.BACKEND_URL = `http://127.0.0.1:${backend.address().port}`;
let vite;

try {
  vite = await createViteServer({
    configFile: fileURLToPath(new URL("../vite.config.js", import.meta.url)),
    server: { host: "127.0.0.1", port: 0, strictPort: false },
  });
  await vite.listen();
  const base = `http://127.0.0.1:${vite.httpServer.address().port}`;

  for (const [path, entry] of [["/", "chat"], ["/admin/", "admin"], ["/login/", "login"]]) {
    const page = await fetch(base + path);
    assert.equal(page.status, 200);
    const html = await page.text();
    const document = JSDOM.fragment(html);
    const entryUrl = document.querySelector(`script[type="module"][src$="/app/${entry}.ts"]`)?.getAttribute("src");
    assert.ok(entryUrl, `Missing module for ${path}`);
    const url = new URL(entryUrl, base + path);
    assert.equal(url.pathname, `/src/app/${entry}.ts`);
    const module = await fetch(url);
    assert.equal(module.status, 200);
    assert.match(module.headers.get("content-type"), /javascript/);
  }

  const dialog = await fetch(`${base}/api/v1/dialogs`, { method: "POST" });
  assert.equal(dialog.status, 201);
  assert.deepEqual(await dialog.json(), { dialog_id: "fake-dialog" });

  const events = await fetch(`${base}/api/v1/dialogs/fake-dialog/events`);
  assert.equal(events.status, 200);
  assert.match(events.headers.get("content-type"), /text\/event-stream/);
  const stream = await events.text();
  assert.match(stream, /event: ready/);
  assert.equal((stream.match(/event: message_delta/g) || []).length, 2);

  console.log("Vite page, POST proxy, and SSE proxy: passed");
} finally {
  await vite?.close();
  await new Promise(resolve => backend.close(resolve));
}
