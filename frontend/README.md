# Chat Frontend (Svelte)

This Svelte + TypeScript app is a lightweight client for the OpenRouter FastAPI backend. It mirrors the core behaviour of the legacy static frontend:

- Select an OpenRouter model exposed by the backend
- Send chat prompts and stream assistant responses in real time
- Cancel or clear the active conversation on demand

## Getting started

```bash
npm install
npm run dev
```

The development server proxies `/api/*` requests to `http://localhost:8000`. Enable the FastAPI backend (see repository root README) before starting the frontend.

### Environment variables

Set `VITE_API_BASE_URL` in `frontend/.env` if you need to target a remote backend instance:

```bash
VITE_API_BASE_URL=https://your-api-host.example.com
```

When unset, the app uses relative URLs so that the dev proxy or same-origin hosting works out of the box.

## Scripts

- `npm run dev` – Vite development server with hot module replacement
- `npm run build` – production build (outputs to `frontend/dist`)
- `npm run preview` – preview the production build locally
- `npm run check` – type-check the project with `svelte-check` and `tsc`

## Building for deployment

The compiled assets live under `frontend/dist`. You can serve them from any static host or mount the directory behind FastAPI (e.g. via `StaticFiles`) as part of your deployment pipeline.
