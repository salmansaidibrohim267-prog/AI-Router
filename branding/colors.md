# Brand Colors

Official AI Router color palette. Values are specified as hex with
OKLCH/HSL equivalents for tooling that needs them.

## Primary palette

| Name | Hex | OKLCH | Usage |
| --- | --- | --- | --- |
| Primary — BlueViolet | `#8A2BE2` | oklch(0.56 0.25 299°) | Logo, links, active states, badges |
| Graphite | `#12141A` | oklch(0.21 0.01 265°) | Dark surfaces, text on light, banners |
| Canvas | `#F7F7FB` | oklch(0.97 0.005 270°) | Light backgrounds |
| Accent — Cyan | `#22D3EE` | oklch(0.79 0.14 215°) | Highlights, streaming/status, focus rings |

## Semantic colors

| Name | Hex | Usage |
| --- | --- | --- |
| Success | `#22C55E` | Healthy, passed, ready |
| Warning | `#F59E0B` | Degraded, retrying, half-open |
| Danger | `#EF4444` | Failed, circuit open, errors |
| Info | `#3B82F6` | Informational, pending |

## Neutrals

| Name | Hex | Usage |
| --- | --- | --- |
| Ink | `#1F2937` | Body text on light backgrounds |
| Slate-500 | `#64748B` | Secondary text, captions |
| Slate-200 | `#E2E8F0` | Dividers, borders |
| White | `#FFFFFF` | Cards on dark, inverse text |

## Scale

- **40 : 1** primary-to-accent ratio in UI chrome (accent is sparing)
- **10 : 1** primary-to-semantic ratio (semantic colors only for state)
- Text on primary: white; text on graphite: white; text on canvas: ink

## Accessibility

- Minimum contrast 4.5:1 for body text, 3:1 for large text and UI elements
- Primary `#8A2BE2` on white passes WCAG AA for large text; use
  `#7A1FD2` (darker BlueViolet) for small body text on light backgrounds
- Semantic colors must never be the only indicator (pair with icons/words)

## Branded surfaces

- Social preview: graphite background, primary logo, cyan accent line
- Dark UI: graphite surfaces, white text, primary accents
- Docs/light UI: canvas background, ink text, primary links

> MANUAL ACTION REQUIRED — generate `branding/assets/palette.svg` (or a
> Figma/Adobe swatch file) from this table for designers.
