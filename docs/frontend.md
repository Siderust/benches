# Frontend Dashboard

`webapp/frontend/` is an internal standalone React/Vite dashboard for inspecting
exported benchmark artifacts. The public `siderust.github.io` benchmark page is
rendered by the parent Astro site, not by this app.

## Data Flow

Generate static lab data first:

```bash
python3 -m pipeline.export_static --lab-root . --output static_export
```

The standalone frontend build copies `../../static_export` into
`webapp/frontend/dist/data/benches/` through `scripts/copy-data.mjs`.
When run through `./run.sh export`, the same export also refreshes
`benches/latest_results/` so the public Astro benchmark page stays current.

## Commands

```bash
cd webapp/frontend
npm install
npm run dev
npm run lint
npm run build:standalone
npm run preview
```

`npm run build` is an alias for `npm run build:standalone`.

## Outputs

| Command | Output | Data source |
| --- | --- | --- |
| `npm run dev` | Vite dev server | `/data/benches/` path expected by the app |
| `npm run build:standalone` | `dist/` | copied from `../../static_export` |
| `npm run preview` | local static preview | built `dist/` |

The frontend is read-only. It must not write to the parent site's public
directory and must not expose benchmark execution controls.

## Refresh Workflow

```bash
cd ../..
./run.sh export
cd webapp/frontend
npm run build:standalone
```

For a full local report build:

```bash
./run.sh build
./run.sh full
./run.sh export
cd webapp/frontend
npm install
npm run build:standalone
```
