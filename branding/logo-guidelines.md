# Logo Guidelines

Specification for the AI Router logo. The logo asset itself is NOT committed;
produce it following this spec.

> MANUAL ACTION REQUIRED — create and commit:
> - `branding/assets/logo.svg` (vector master)
> - `branding/assets/logo.png` (512×512, transparent background)

## Concept

A gateway/router motif combined with an AI element:

- A rounded-square or hexagon node representing the gateway
- Multiple paths radiating outward to smaller nodes (providers), suggesting
  intelligent routing rather than a straight line
- A subtle spark/beam in the primary color implying intelligence

## Construction

- Canvas: 1024×1024 (master), safe zone 512×512
- Grid: 8px base grid; all geometry snaps to the grid
- Rounded corners: radius = 16% of the node width
- Stroke: 2.5% of canvas width, uniform
- Single primary color by default (see `colors.md`); the white variant is
  used on the graphite background

## Clear space

- Minimum clear space around the logo: 1× the height of the node on all sides
- Never place text, images, or other marks inside the clear space

## Minimum sizes

| Context | Minimum width |
| --- | --- |
| Digital (screen) | 32 px |
| Favicon | 16 px (simplified glyph only) |
| Print | 10 mm |

## Variants

| Variant | Use |
| --- | --- |
| Primary (BlueViolet on transparent) | Light backgrounds, docs, web |
| Inverse (white) | Graphite backgrounds, dark UI, social images |
| Monochrome (single neutral) | Favicons, watermarks, embossing |

## Prohibited

- Do not stretch, rotate, or skew the logo
- Do not change the colors outside the palette
- Do not add gradients, shadows, or outlines
- Do not place the logo on busy or low-contrast backgrounds
- Do not combine the logo with third-party marks inside the clear space

## Lockup

Horizontal lockup for headers: logo mark + wordmark "AI Router" in the
primary typeface, separated by 1× node width. Vertical lockup for square
formats: mark above the wordmark, aligned center.
