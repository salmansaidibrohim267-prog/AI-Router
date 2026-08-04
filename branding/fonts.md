# Fonts

Official type system for AI Router brand materials and documentation.

## Families

| Role | Family | Fallback | License |
| --- | --- | --- | --- |
| UI & headings | Inter (Variable) | system-ui, -apple-system, Segoe UI, Roboto | SIL Open Font License |
| Code & metrics | JetBrains Mono | ui-monospace, SFMono-Regular, Menlo, Consolas | Apache 2.0 |

Both are free to use; source from Google Fonts or the projects' own
repositories. Never substitute proprietary look-alike faces.

## Type scale (digital)

| Token | Size / Line-height | Weight | Use |
| --- | --- | --- | --- |
| display | 56 / 64 px | 700 | Landing hero |
| h1 | 40 / 48 px | 700 | Page titles |
| h2 | 32 / 40 px | 650 | Section titles |
| h3 | 24 / 32 px | 600 | Sub-sections |
| body | 16 / 24 px | 400 | Paragraphs |
| small | 14 / 20 px | 400 | Captions, metadata |
| code | 14 / 20 px | 400 | Inline code, metrics |

## Usage rules

- Headings: Inter 600–700, tracking −0.01em, no all-caps
- Body: Inter 400, line-height 1.5, max measure 72ch
- Code and metric values: JetBrains Mono 400
- Numerals in dashboards/stats: JetBrains Mono for tabular alignment
- Technical docs: max line length 90ch

## Wordmark

"AI Router" in Inter 700, letterspacing +0.02em; "Router" may use the
primary color while "AI" stays neutral (see `logo-guidelines.md`).

## Self-hosting

If web fonts cannot be loaded from a CDN (air-gapped intranets, strict CSP),
bundle the WOFF2 files from the official Inter and JetBrains Mono releases.
Fallbacks listed above remain acceptable.
