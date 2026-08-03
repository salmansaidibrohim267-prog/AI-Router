# Typography

Type system for AI Router brand materials and documentation.

## Families

| Role | Family | Fallback |
| --- | --- | --- |
| UI & headings | Inter (Variable) | system-ui, -apple-system, Segoe UI, Roboto |
| Code & metrics | JetBrains Mono | ui-monospace, SFMono-Regular, Menlo, Consolas |

Inter and JetBrains Mono are available free from Google Fonts (SIL Open
Font License / Apache 2.0 respectively).

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

- Headings: Inter 600–700, tight tracking (-0.01em), no all-caps
- Body: Inter 400, 1.5 line-height, max measure 72ch
- Code and metric values: JetBrains Mono, 400
- Numerals in dashboards and stats: JetBrains Mono for tabular alignment
- Line length for technical content: 90ch max in docs

## Wordmark

"AI Router" set in Inter 700 with letterspacing +0.02em; the word "Router"
may use the primary color while "AI" stays neutral (see `logo-guidelines.md`
lockup rules).

## Licensing note

Inter and JetBrains Mono are open-source fonts. If a distribution channel
cannot bundle web fonts, use the listed system fallbacks — never substitute
fonts with similar-looking proprietary faces.
