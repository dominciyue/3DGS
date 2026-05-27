# Frontend — Task Dashboard

A zero-build single-page app (plain HTML/CSS/JS) for driving the 3DGS-Agent backend:
drag-drop images, give the Agent a natural-language instruction, watch the pipeline
run live (Server-Sent Events), then download the `.ply` and see the Unity next-steps.

## Run

Two options:

**A. Served by the backend (simplest).** The FastAPI app mounts this folder at `/`,
so just start the backend and open it:
```bash
cd ../backend && uvicorn app.main:app --reload   # http://localhost:8000
```

**B. Standalone static server** (separate origin; backend CORS already allows it):
```bash
python -m http.server 5173      # open http://localhost:5173
```
`app.js` auto-detects the API base: same-origin when served by the backend (case A),
otherwise `http://localhost:8000` (case B).

## Files

- `index.html` — layout: upload, instruction, preset, job view, recent jobs.
- `styles.css` — dark technical theme, no external fonts/CDNs (works offline).
- `app.js` — upload → `POST /api/jobs`, live `EventSource` on `/api/jobs/{id}/events`,
  stage progress, log stream, result download.

No `package.json`, no bundler — open it and it works. (If a build step is ever added,
`node_modules/` and `dist/` are already covered by the repo `.gitignore`.)
