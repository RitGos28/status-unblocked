# Status Unblocked — React Frontend

Modern React application for Status Unblocked, built with Vite, React 18, and JSX.

## Features

- **Modern Architecture**: Component-based React JSX structure with responsive design tokens and CSS variables.
- **Dark/Light Mode**: Full support with dynamic styling, contrast checking, and typography.
- **Interactive Updates Form**: Multi-field async standup submission with immediate feedback.
- **Digests Dashboard**: Team cycle browsing, manual digest build/rebuild triggers, state badges.
- **Rich Digest Viewer**: Verbatim quote claims, rule explanation subtext, tracker links with age badges, and one-click citation source navigation.
- **Verifiable Evidence Inspector**: Canonical evidence view with character-offset highlights on original submissions and cryptographic audit notice.
- **Teams Bot Linking**: Seamless 1:1 bot pairing code display with copy-to-clipboard functionality.
- **Manager Portal** (`/#/manager`): a separate username/password sign-in; one team at a time with a 7/14/30-day summary read from the digests (open blockers, day-by-day counts, each person's lines), the day list with Build/Rebuild, and Add member. Demo credentials come from `backend/.env.example`.

## Development

```bash
cd frontend
npm install
npm run dev
```

The frontend dev server runs at `http://localhost:5173` with automatic API proxying to `http://127.0.0.1:8000`.

## Production Build

```bash
npm run build
npm run preview
```
