# Frontend

Read the [frontend guide](README.md) for page behavior and deployment. The HTML
entries live under `src/entry/`, the Vite root. Direct navigation to `/`,
`/login/` and `/admin/` must work through both Vite and Nginx.

- Follow Feature-Sliced Design. Import down the layers from `app` to `pages`,
  `widgets`, `features`, `entities` and `shared`. Use a slice's public
  `index.ts` from outside that slice. Keep page-specific code near its consumers.
- Render data with typed Svelte components and text interpolation. Keep HTTP
  and EventSource contracts in `entities`. Keep session credentials in cookies.
- Use Flux for shared and asynchronous workflows. A command performs the
  effect and dispatches typed actions. A pure reducer updates state and
  components subscribe. Transient DOM details such as focus stay local.
- Dispose of subscriptions, listeners, timers and streams on teardown. Ignore
  obsolete responses after a change of dialog or session.
- Run `npm --prefix frontend run check`, the affected tests with
  `npm --prefix frontend test -- tests/agent-api.test.js` (substitute the
  affected file), and `npm --prefix frontend run build`. For route or proxy
  changes run `npm --prefix frontend run test:proxy`. Verify layout changes
  in a browser at desktop and mobile widths.
