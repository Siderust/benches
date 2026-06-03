# Siderust Lab — Frontend

Internal standalone React/Vite dashboard for the Siderust benchmark lab.
The public `siderust.github.io` benchmark page is rendered by Astro at
`/<locale>/benchmarks`, so this app must not publish into the parent site's
`public/lab/` directory.

| Command | Output | Where data comes from |
| --- | --- | --- |
| `npm run build` / `npm run build:standalone` | `./dist/` (self-contained) | bundled under `./dist/data/lab/` |

The standalone bundle can be served by any static host:

```sh
npm run build:standalone
npx serve dist
# open http://localhost:3000
```

The standalone mode copies the local static export from
`../../static_export` at build time via `scripts/copy-data.mjs`. To refresh
the data, regenerate the lab data first:

```sh
python3 -m pipeline.export_static
npm run build:standalone
```

For details about the lab itself, see `../../USER_MANUAL.md`.
