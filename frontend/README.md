# Warmline frontend

The web app for Warmline: a public landing page, the owner dashboard (chat links and FAQ),
and the hosted chat that customers open from a link.

Vite + React 19 + React Router, in plain JavaScript. Styling is Tailwind CSS v4 with
shadcn/ui components copied into `src/components/ui/` as JSX (built on Radix primitives,
so menus and dialogs are keyboard- and screen-reader-friendly).

## Run it

Node.js 22.22 or newer. The backend must be running, with this frontend's origin in its
`CORS_ALLOWED_ORIGINS` and `PUBLIC_CHAT_BASE_URL` pointing here (see the main README).

```bash
cp .env.example .env
npm install
npm run dev            # http://localhost:5173
```

| Script                            | What it does                                                                      |
| --------------------------------- | --------------------------------------------------------------------------------- |
| `npm run dev`                     | Development server with hot reload on port 5173.                                  |
| `npm test`                        | 48 unit and component tests (Vitest + Testing Library, fake `fetch`, no backend). |
| `npm run lint`                    | ESLint: JavaScript rules, React hooks rules, accessibility rules (jsx-a11y).      |
| `npm run format` / `format:check` | Prettier (also sorts Tailwind classes).                                           |
| `npm run build`                   | Production build into `dist/`.                                                    |
| `npm run preview`                 | Serves `dist/` on port 4173, to check the real build locally.                     |

CI (`.github/workflows/frontend.yml`) runs `npm ci`, lint, the format check, the tests
and the build whenever something under `frontend/` changes.

## Configuration

Set at build time from `.env` (see `.env.example`). **Everything in a frontend bundle is
public**: never put a secret in a `VITE_` variable.

| Variable            | Meaning                                                                                                                 |
| ------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| `VITE_API_BASE_URL` | The backend's address. Default `http://localhost:8000`.                                                                 |
| `VITE_SITE_URL`     | This site's public address, for the absolute link-preview URLs (`og:url`, `og:image`). Default `http://localhost:5173`. |

## How it is organised

```
src/
  main.jsx            starting point: error reporting, error page, router, login session, toasts
  App.jsx             the route table; every page is loaded on demand (its own JS file)
  index.css           Tailwind + design tokens (colours, fonts, radius, the two animations)
  api/                the only code that calls fetch(); one file per backend area
  auth/               the login session (AuthContext) and the guard for owner pages
  hooks/              useApiRequest (load data), useSubmit (send a change), useChat
  utils/              small helpers: cn, dates, initials, CSV file check, reportError
  components/
    ui/               shadcn/ui building blocks (button, dialog, table, toast, ...)
    layout/           page frames: dashboard shell, auth layout, headers, footer
    feedback/         error message, empty state, error boundary, toasts
    integrations/ faq/ chat/ landing/   the parts of each page
  pages/              one file per route
```

Rules the code follows:

- **One way to talk to the API.** Only `api/client.js` calls `fetch`. Every failure
  becomes an `ApiError` with the server's own message.
- **One way to load and one way to submit.** Pages load with `useApiRequest` (loading,
  error with Try again, data) and send changes with `useSubmit` (button disabled while
  sending, server error kept for display).
- **Every screen has its states:** skeletons while loading, an error with Try again, an
  empty state that says what to do next, and an error page (not a blank screen) if
  something crashes.
- **Text is text.** Chat messages and all API data are rendered by React as plain text,
  never as HTML.

## Design

Direction "Warm workshop": warm paper background `#FAF7F2`, ink `#1F1B16`, one accent
(ember `#C2410C`), Fraunces for headings and Inter for text, both self-hosted (no font
service). Every text colour pair passes WCAG AA contrast (4.5:1 or more). Motion is
limited to short CSS fades and is turned off for people who ask their system for reduced
motion.

## Deploying (notes for later; nothing is deployed)

The build is static files. Any static host or CDN works, with two requirements:

1. **Single-page app fallback:** unknown paths (for example `/c/abc123` or `/app/faq`)
   must return `index.html`, so the app can route them. Files under `/assets/` have
   hashed names and can be cached for a year; `index.html` should not be cached.
2. **Security headers**, sent by the host (a static build cannot send headers itself):

```
Content-Security-Policy: default-src 'self'; script-src 'self'; connect-src 'self' https://<api-host>;
  img-src 'self' data:; font-src 'self'; style-src 'self' 'unsafe-inline'; object-src 'none';
  base-uri 'self'; frame-ancestors 'none'; form-action 'self'
Strict-Transport-Security: max-age=31536000; includeSubDomains
X-Content-Type-Options: nosniff
Referrer-Policy: strict-origin-when-cross-origin     (no-referrer on /c/*)
Permissions-Policy: camera=(), microphone=(), geolocation=()
```

- `style-src 'unsafe-inline'` is needed because Radix positions menus with inline styles.
  Scripts stay strict (`'self'` only).
- `Referrer-Policy: no-referrer` on `/c/*` stops a chat link's secret part from leaking
  to other sites through the `Referer` header.
- `frame-ancestors 'none'` stops other sites from framing the app (clickjacking). If an
  embeddable widget is built later, the chat page will need its own rule.
- On the backend, `CORS_ALLOWED_ORIGINS` must list the production frontend origin
  (never `*`), and `PUBLIC_CHAT_BASE_URL` must point at the production frontend.

## Measured (production build, local preview)

- **Lighthouse** (mobile preset, local): landing 100 performance / 100 accessibility /
  100 best practices / 100 SEO. Chat page 100 / 100 / 100, SEO 63, on purpose:
  `robots.txt` keeps search engines out of `/c/` because chat links are private to each
  business.
- **First visit downloads** about 205 kB compressed: about 111 kB JavaScript, 7 kB CSS,
  84 kB fonts.
- **`npm audit`:** 0 known vulnerabilities.

These are local numbers; a real host and network will differ.

## Known limitations

- **No type checking.** The project is plain JavaScript by choice, so type mistakes are
  only caught by tests, lint and review. The request and response shapes are written as
  comments in `src/api/`.
- **The owner's login token is in `localStorage`.** A script injected into the page (an
  XSS bug) could read it. The app renders no raw HTML and the recommended CSP blocks
  outside scripts, but an `httpOnly` cookie would be safer; that needs backend changes
  and CSRF protection. There is no refresh token, so owners log in again after 30 minutes.
- **The hosted chat forgets on reload.** The backend has no route to read earlier
  messages, so a reload starts a new conversation.
- **Link previews are the same for every page.** Preview crawlers do not run JavaScript,
  so only the tags in `index.html` count.
- **Main flows are not tested end to end in CI.** That needs a running backend and the
  model. They were checked in a real browser against the real backend, by hand and with
  a script that is not in the repo.
- **Fonts are not preloaded.** They use `font-display: swap` and a size-matched fallback
  (no layout shift measured), but the first text paint can briefly use the fallback.
- The FAQ page cannot edit or delete one entry, and the list has no search or sort.
- The agent does not know the business's name when asked (the backend prompt does not
  include it); the chat page shows it.
