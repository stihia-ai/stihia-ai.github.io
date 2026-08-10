#!/usr/bin/env python3
"""Generate Claude Design preview files from the live stylesheet.

main.css stays the single source of truth. Each preview inlines the real
tokens and component rules, so a card can never drift from the site: change
main.css, re-run this, re-push. Run from anywhere:

    python3 ui_kit/build.py
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAIN_CSS = ROOT / "assets" / "css" / "main.css"
SRC = Path(__file__).resolve().parent / "src"
DIST = Path(__file__).resolve().parent / "dist"

# The handful of Bootstrap rules the components actually lean on. Vendored so
# previews render standalone instead of depending on the CDN reaching them.
BOOTSTRAP_SHIM = """
/* Reboot. Not optional: .stage-card pairs height:100% with 1.7rem padding and
   overflows its row by 54px without border-box. */
*, *::before, *::after { box-sizing: border-box; }

.btn {
  display: inline-block;
  padding: 0.375rem 0.75rem;
  border: 1px solid transparent;
  border-radius: 0.375rem;
  font-size: 1rem;
  font-weight: 400;
  line-height: 1.5;
  text-align: center;
  text-decoration: none;
  vertical-align: middle;
  cursor: pointer;
  user-select: none;
  background-color: transparent;
}
.btn-lg { padding: 0.5rem 1rem; font-size: 1.25rem; border-radius: 0.5rem; }
.btn-sm { padding: 0.25rem 0.5rem; font-size: 0.875rem; border-radius: 0.25rem; }
.rounded-pill { border-radius: 50rem !important; }
.btn-outline-light { color: #f8f9fa; border-color: #f8f9fa; }
"""

# Chrome for the preview page itself — deliberately neutral so it reads as a
# spec sheet, not as another Stihia page competing with the component.
HARNESS_CSS = """
body {
  margin: 0;
  padding: 40px;
  background: var(--color-bg);
  color: var(--color-text);
  font-family: var(--font-family-base);
  font-size: var(--fs-body);
  line-height: var(--lh-normal);
  -webkit-font-smoothing: antialiased;
}
.ds-head { margin-bottom: 34px; }
.ds-title {
  margin: 0 0 6px;
  font-size: var(--fs-card-title);
  font-weight: var(--fw-semibold);
  color: var(--color-text-strong);
}
.ds-note {
  margin: 0;
  font-size: var(--fs-sm);
  letter-spacing: var(--ls-tight);
  color: var(--color-text-muted-utility);
}
.ds-group { margin-bottom: 40px; }
.ds-group:last-child { margin-bottom: 0; }
.ds-label {
  margin: 0 0 16px;
  font-size: var(--fs-xs);
  letter-spacing: var(--ls-wide);
  text-transform: uppercase;
  color: var(--color-text-muted-utility);
}
.ds-row { display: flex; flex-wrap: wrap; gap: 16px; align-items: center; }
.ds-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(230px, 1fr));
  gap: 18px;
}
.ds-mono {
  font-family: var(--font-family-mono);
  font-size: var(--fs-xs);
  color: var(--color-text-muted);
}

/* Token specimen chrome */
.tok {
  border: 1px solid var(--color-border-subtle);
  border-radius: 12px;
  padding: 14px 16px;
  background: var(--color-card-surface);
}
.tok-swatch {
  height: 56px;
  border-radius: 8px;
  border: 1px solid var(--color-border-soft);
  margin-bottom: 12px;
}
.tok-name {
  font-family: var(--font-family-mono);
  font-size: var(--fs-xs);
  color: var(--color-text-strong);
  word-break: break-all;
}
.tok-value {
  font-family: var(--font-family-mono);
  font-size: 0.68rem;
  color: var(--color-text-gray);
  word-break: break-all;
  margin-top: 4px;
}
.tok-specimen {
  color: var(--color-text-strong);
  margin-bottom: 8px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
/* .stage-card ships height:100%, sized for Bootstrap equal-height columns.
   The preview supplies that context explicitly so the card is not asked to
   fill an auto-height block and overflow. */
.ds-stage-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 22px;
  align-items: stretch;
}
.ds-stage-grid-single {
  grid-template-columns: minmax(0, 420px);
  justify-content: start;
}
@media (max-width: 900px) {
  .ds-stage-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}

.tok-bar {
  height: 18px;
  border-radius: 4px;
  background: linear-gradient(
    90deg,
    var(--accent-signature),
    var(--accent-semantic)
  );
  opacity: 0.55;
  margin-bottom: 10px;
}
"""

PAGE = """<!-- @dsCard group="{group}" -->
<meta charset="utf-8" />
<title>{title}</title>
<link rel="preconnect" href="https://fonts.googleapis.com" />
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600&family=Goldman&family=JetBrains+Mono&display=swap" />
<style>
{css}
</style>
<div class="ds-head">
  <h1 class="ds-title">{title}</h1>
  <p class="ds-note">{note}</p>
</div>
{body}
"""


def read_tokens():
    """Parse the :root block into [(group, name, value)], preserving order."""
    css = MAIN_CSS.read_text(encoding="utf-8")
    root = re.search(r":root\s*\{(.*?)\n\}", css, re.S)
    if not root:
        raise SystemExit("could not locate :root block in main.css")

    tokens, group = [], "Other"
    for line in root.group(1).splitlines():
        heading = re.search(r"/\*\s*[─\s]*(.+?)[─\s]*\*/", line)
        if heading:
            group = heading.group(1).strip()
            continue
        decl = re.match(r"\s*(--[\w-]+)\s*:\s*(.+?);", line)
        if decl:
            tokens.append((group, decl.group(1), decl.group(2).strip()))
    return tokens


def extract_section(title):
    """Pull one named section of main.css, from its banner to the next one."""
    css = MAIN_CSS.read_text(encoding="utf-8")
    banner = re.compile(
        r"/\* -{10,}\n\s*" + re.escape(title) + r".*?\n\s*-{10,} \*/(.*?)(?=/\* -{10,})",
        re.S,
    )
    match = banner.search(css)
    if not match:
        raise SystemExit(f"could not locate section {title!r} in main.css")
    return match.group(1).rstrip()


def group_tokens(tokens, prefixes=(), groups=()):
    return [
        t
        for t in tokens
        if (any(t[1].startswith(p) for p in prefixes) if prefixes else True)
        and (any(g in t[0] for g in groups) if groups else True)
    ]


def tok_card(name, value, inner=""):
    return (
        f'<div class="tok">{inner}'
        f'<div class="tok-name">{name}</div>'
        f'<div class="tok-value">{value}</div></div>'
    )


def build_color(tokens):
    out = []
    for group in ["Backgrounds", "Text", "Borders", "Accents", "Card Decorative"]:
        items = [t for t in tokens if group in t[0]]
        if not items:
            continue
        cards = "\n".join(
            tok_card(n, v, f'<div class="tok-swatch" style="background:{v}"></div>')
            for _, n, v in items
        )
        out.append(
            f'<div class="ds-group"><p class="ds-label">{group}</p>'
            f'<div class="ds-grid">{cards}</div></div>'
        )
    return "\n".join(out)


def build_type(tokens):
    out = []

    families = group_tokens(tokens, ("--font-family-",))
    cards = "\n".join(
        tok_card(
            n,
            v,
            f'<div class="tok-specimen" style="font-family:{v};font-size:1.4rem">'
            f"Stihia AI Security</div>",
        )
        for _, n, v in families
    )
    out.append(
        f'<div class="ds-group"><p class="ds-label">Families</p>'
        f'<div class="ds-grid">{cards}</div></div>'
    )

    sizes = group_tokens(tokens, ("--fs-",))
    rows = "\n".join(
        f'<div class="tok"><div class="tok-specimen" style="font-size:{v}">Ag</div>'
        f'<div class="tok-name">{n}</div><div class="tok-value">{v}</div></div>'
        for _, n, v in sizes
    )
    out.append(
        f'<div class="ds-group"><p class="ds-label">Size scale</p>'
        f'<div class="ds-grid">{rows}</div></div>'
    )

    for label, prefix in [
        ("Weight", "--fw-"),
        ("Line height", "--lh-"),
        ("Letter spacing", "--ls-"),
    ]:
        items = group_tokens(tokens, (prefix,))
        style = {
            "--fw-": "font-weight:{v}",
            "--lh-": "line-height:{v};white-space:normal",
            "--ls-": "letter-spacing:{v}",
        }[prefix]
        cards = "\n".join(
            tok_card(
                n,
                v,
                f'<div class="tok-specimen" style="{style.format(v=v)}">'
                f"The quick brown fox</div>",
            )
            for _, n, v in items
        )
        out.append(
            f'<div class="ds-group"><p class="ds-label">{label}</p>'
            f'<div class="ds-grid">{cards}</div></div>'
        )
    return "\n".join(out)


def build_spacing(tokens):
    out = []

    spacing = group_tokens(tokens, ("--space-",))
    cards = "\n".join(
        tok_card(n, v, f'<div class="tok-bar" style="width:{v}"></div>')
        for _, n, v in spacing
    )
    out.append(
        f'<div class="ds-group"><p class="ds-label">Spacing</p>'
        f'<div class="ds-grid">{cards}</div></div>'
    )

    radii = group_tokens(tokens, ("--radius-",))
    cards = "\n".join(
        tok_card(
            n,
            v,
            f'<div class="tok-swatch" style="border-radius:{v};'
            f"background:var(--color-panel)\"></div>",
        )
        for _, n, v in radii
    )
    out.append(
        f'<div class="ds-group"><p class="ds-label">Radii</p>'
        f'<div class="ds-grid">{cards}</div></div>'
    )

    widths = group_tokens(tokens, ("--max-w-",))
    cards = "\n".join(tok_card(n, v) for _, n, v in widths)
    out.append(
        f'<div class="ds-group"><p class="ds-label">Layout maxima</p>'
        f'<div class="ds-grid">{cards}</div></div>'
    )

    shadows = group_tokens(tokens, ("--shadow-",))
    cards = "\n".join(
        tok_card(
            n,
            v,
            f'<div class="tok-swatch" style="box-shadow:{v};'
            f"background:var(--color-panel)\"></div>",
        )
        for _, n, v in shadows
    )
    out.append(
        f'<div class="ds-group"><p class="ds-label">Shadows</p>'
        f'<div class="ds-grid">{cards}</div></div>'
    )
    return "\n".join(out)


# Each entry: (output path, card group, title, note, css sections, body builder)
CARDS = [
    (
        "foundations/type.html",
        "Foundations",
        "Type",
        "Families, size scale, weight, line height and tracking — parsed live from main.css :root.",
        [],
        lambda t: build_type(t),
    ),
    (
        "foundations/color.html",
        "Foundations",
        "Color",
        "Full oklch palette: backgrounds, text, borders, accents and card decoratives.",
        [],
        lambda t: build_color(t),
    ),
    (
        "foundations/spacing.html",
        "Foundations",
        "Spacing",
        "Spacing steps, corner radii, layout maxima and elevation.",
        [],
        lambda t: build_spacing(t),
    ),
    (
        "components/buttons.html",
        "Components",
        "Buttons",
        "Pill buttons in primary and outline-light, at three sizes. Extends Bootstrap .btn.",
        ["Buttons"],
        lambda t: (SRC / "buttons.html").read_text(encoding="utf-8"),
    ),
    (
        "components/stage-cards.html",
        "Components",
        "Stage cards",
        "Ordered sequence steps. Four accent variants driven by --stage-accent.",
        ["Stage Cards"],
        lambda t: (SRC / "stage-cards.html").read_text(encoding="utf-8"),
    ),
]


def main():
    tokens = read_tokens()
    root_block = re.search(
        r"(:root\s*\{.*?\n\})", MAIN_CSS.read_text(encoding="utf-8"), re.S
    ).group(1)

    for path, group, title, note, sections, body_fn in CARDS:
        css_parts = [root_block, BOOTSTRAP_SHIM, HARNESS_CSS]
        css_parts += [extract_section(s) for s in sections]
        page = PAGE.format(
            group=group,
            title=title,
            note=note,
            css="\n".join(css_parts),
            body=body_fn(tokens),
        )
        target = DIST / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(page, encoding="utf-8")
        print(f"{path}  ({len(page):,} bytes)")

    print(f"\n{len(CARDS)} previews -> {DIST}")


if __name__ == "__main__":
    main()
