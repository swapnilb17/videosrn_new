# Mobile-Friendly Migration — Progress Log

> **Persistent context for the agent across chats / context refreshes.**
> Keep this file up-to-date as you work. If context is lost, read this first.

## Goal

Make EnablyAI_VGEN first-class on phones while **keeping the desktop UI byte-for-byte identical** (all mobile changes are gated behind Tailwind responsive prefixes — typically `< md` for shell, `< xl` for creator panels).

## Authoritative plan

`/Users/swapnilbhairavkar/.cursor/plans/vgen_mobile-friendly_migration_3fecbfb1.plan.md`

## Key decisions (locked)

- **Depth:** first-class mobile UX (not just "don't break").
- **Creator panels:** stack vertically on mobile (controls → preview → history). No tab UI.
- **Bottom nav order:** `Home · Templates · Create (centered FAB) · Media · More`.
- **Create button behavior:** tapping the centered FAB opens a `<Sheet>` ("Create" bottom sheet) listing all 5 AI services as tappable rows. Tap a row → routes to `/dashboard/create?service=<key>`. Does NOT directly route to one service.
- **Desktop preserved:** sidebar rail + topbar remain unchanged at `md:` and up. Multi-column creator layouts remain at `xl:` and up.
- **No new heavy deps:** built `<Sheet>` ourselves on top of existing Radix Slot / lucide. No `@dnd-kit`, no `vaul`, no shadcn install.

## Tech stack snapshot (do not relearn)

- Next.js 16.2.2 (App Router). `viewport` is exported (not in `metadata`).
- Tailwind v4 — no `tailwind.config.*`; theme tokens via `@theme inline` in `app/globals.css`.
- React 19.2.4.
- `next-auth` v4. Dashboard layout is `"use client"` and checks `useAuth().isAuthenticated`.
- Utility: `cn()` from `@/lib/utils` (clsx + tailwind-merge).
- `Card` = simple wrapper in `components/ui/card.tsx`.
- `ClayButton` = primary CTA with `.clay` class from `globals.css`.
- All `<aside>` / `<header>` chrome lives in `components/dashboard/sidebar.tsx` + `topbar.tsx`.

## Server / deployment

- **Prod server:** `65.0.170.188`
- **SSH key:** `~/Downloads/EnablyAI_KeyPair_New.pem`
- **Repo deploy:** `git push origin main` triggers GitHub Actions (see `push-to-prod.sh`).
- **Direct SSH** for one-off ops: `ssh -i ~/Downloads/EnablyAI_KeyPair_New.pem ubuntu@65.0.170.188` (user may differ — check `Dockerfile.*` / docs).

## Phase status

| Phase | Status | Notes |
|-------|--------|-------|
| 1. Foundation (viewport, dvh utils, useIsMobile, Sheet) | done | |
| 2. Navigation shell (mobile topbar + FAB bottom nav + Create sheet) | done | |
| 3. Creator panels (5 files, stack on mobile) | done | |
| 4. Galleries / tables / settings | done | Templates: tap autoplay; Media: 2-col mobile grid; UsageReport: card list on mobile |
| 5. Landing + auth polish | skipped | Already responsive (`md:` prefixes); coarse-pointer hover suppression handled in `globals.css` |
| 6. QA (lint + build) | done | `npm run lint` clean; `npm run build` 19 routes OK |
| 7. Deploy to 65.0.170.188 | pending | Push to `origin/main` triggers `.github/workflows/deploy.yml` |

## File-by-file change log

### New files
- `MOBILE_MIGRATION_PROGRESS.md` — this file.
- `lib/use-is-mobile.ts` — `useIsMobile(bp)` + `useIsTouch()` SSR-safe hooks.
- `lib/dashboard-nav.ts` — shared `mainLinks` + `serviceLinks` (was duplicated in `sidebar.tsx`).
- `components/ui/sheet.tsx` — portal-rendered drawer (left/right/bottom) with scrim, Esc, swipe-down, body-scroll lock.
- `components/dashboard/mobile-topbar.tsx` — mobile-only topbar: hamburger drawer + credits pill + avatar menu sheet.
- `components/dashboard/mobile-nav.tsx` — bottom nav with centered FAB Create button + Create chooser sheet + More sheet.

### Modified files
- `app/layout.tsx` — exported Next 16 `viewport` with `device-width`, `viewportFit: "cover"`, `themeColor`.
- `app/globals.css` — body hardening (text-size-adjust, overscroll-behavior, touch-action), `.h-app` / `.h-screen-app` dvh utilities, `.pb-safe` / `.pt-safe`, `(pointer: coarse)` hover suppression for `.clay` and `.cta-glow`.
- `app/dashboard/layout.tsx` — renders `<MobileTopbar />` and `<MobileNav />` for `< md`, keeps desktop `<DashboardSidebar />` + `<DashboardTopbar />`. `<main>` gets bottom padding for the fixed bottom nav on mobile.
- `components/dashboard/sidebar.tsx` — split into `SidebarContent` (reused by mobile drawer) + `DashboardSidebar` rail; rail is now `hidden md:block`.
- `components/dashboard/topbar.tsx` — `hidden ... md:flex` so it doesn't double-render with mobile topbar.
- `components/dashboard/video-editor.tsx` — `flex flex-col gap-4 xl:grid xl:grid-cols-[320px_1fr_300px]`; viewport-height caps moved behind `xl:`.
- `components/dashboard/text-to-image.tsx` — same stack pattern; style tile grid `grid-cols-3 sm:grid-cols-4`; mobile-friendly upload copy.
- `components/dashboard/text-to-voice.tsx` — same stack pattern.
- `components/dashboard/photo-to-video.tsx` — same stack pattern.
- `components/dashboard/image-to-ad-video.tsx` — same stack pattern.
- `components/dashboard/templates-gallery.tsx` — `IntersectionObserver` autoplay for touch devices, hover-only autoplay for mouse; full-width search on phones. **Remix flow**: each card is a `<Link>` to `/dashboard/create?…`. URL carries `template_id`, `template_title`, `aspect`, `duration`, `prompt`, `asset_variant`. Image → Text-to-Image with `asset_variant=image`. Video → Photo-to-Video in `image_to_video` mode with `asset_variant=thumbnail` when the template has a thumbnail still, else falls back to `text_to_video`. The "Remix" overlay pill is always visible on touch, hover-only on `md+`. Prompt scaffold composes title + description + tags + category + an instruction to match the reference.
- `components/dashboard/text-to-image.tsx` — reads `prompt`, `template_title`, `template_id`, `asset_variant`, `aspect` from `useSearchParams`. When `template_id` + `asset_variant` are present, calls `GET /api/templates/{id}/asset?variant=…` (backend route, same-origin via existing nginx routing) and seeds `uploadedImage` + `imagePreview`. Banner reflects actual attach state: loading → attached → couldn't-load (amber).
- `components/dashboard/photo-to-video.tsx` — reads `prompt`, `task`, `template_title`, `template_id`, `asset_variant`, `aspect`, `duration` from `useSearchParams`. Same backend asset call seeds `startFrame` + `startPreview` so the generated video opens from the template's first frame.

### Backend
- `backend/app/routers/templates_public.py` — new `GET /api/templates/{template_id}/asset?variant=image|thumbnail` endpoint streams the template's bytes straight from S3 (the backend has the IAM role, the browser doesn't). 25 MB stream cap, `Cache-Control: public, max-age=300`. Required because the dashboard nginx forwards all of `/api/*` (except a small allowlist) to FastAPI; a Next.js route handler under `/api/` wouldn't be reached, and `<img src>` / `<video src>` against the presigned URL works only for media tags — `fetch()` needs same-origin which S3 CORS doesn't provide.

### New library
- `lib/template-asset.ts` — `loadTemplateAsImageFile(templateId, variant, base)` helper. Hits the backend asset endpoint same-origin, falls back to JPEG MIME when the upstream content-type is missing, returns a `File` ready for the creator's `FormData`.
- `components/dashboard/media-gallery.tsx` — `grid-cols-2` on mobile (was 1-col default).
- `components/billing/usage-report.tsx` — wide table only at `md:` and up; mobile renders a card list with the same data.

## Build / verification commands

```bash
cd /Users/swapnilbhairavkar/Documents/EnablyAI_VGEN
npm run lint   # clean
npm run build  # 19 routes, ✓ Compiled successfully
```

## Open questions / blockers

(None — ready to deploy.)

## Build / verification commands

```bash
cd /Users/swapnilbhairavkar/Documents/EnablyAI_VGEN
npm run lint
npm run build
```

## Open questions / blockers

(None yet.)
