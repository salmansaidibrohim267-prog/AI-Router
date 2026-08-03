# Social Preview

Specification for the repository's social preview image.

> MANUAL ACTION REQUIRED — render and commit:
> `branding/assets/social-preview.png` (1280×640 px), then upload it in
> **GitHub → Settings → Social preview** (opencode: this requires owner
> access and cannot be automated).

## Canvas

- Size: **1280×640 px** (2:1, GitHub's recommended ratio)
- Format: PNG, flat (no transparency on the base)
- Safe margins: 80 px on all sides (text/logo inside the safe area)

## Layout

| Region | Content |
| --- | --- |
| Background | Graphite `#12141A` with a subtle diagonal network motif (grid of nodes + thin lines, opacity < 8%) |
| Top-left | Logo mark (inverse/white variant) at 96 px height |
| Center-left | Wordmark "AI Router" (Inter 700, 96 px), primary-color underline bar |
| Below wordmark | Tagline: **Multi-LLM Routing · RAG · MCP · Plugins** (Inter 400, 40 px, Slate-200) |
| Bottom-left | `salmansaidibrohim267-prog/AI-Router` (JetBrains Mono, 24 px, Slate-500) |
| Accent | Cyan `#22D3EE` horizontal rule (4 px) separating header from tagline |

## Text checklist

- Tagline and repo handle must fit within the safe margins at 1280 px width
- No text below y = 560 px (GitHub crops the bottom on some surfaces)
- No transparency over text areas

## Variants

- Base: graphite background (default dark mode)
- Optional light variant: Canvas `#F7F7FB` background, primary logo,
  ink text — for light-theme surfaces

## Validation

- Check at 100%, 50%, and 25% zoom — text must stay legible at 25%
- Check on a white and on a graphite mock background
- Confirm no rounded corners are baked into the image (GitHub applies masks)
