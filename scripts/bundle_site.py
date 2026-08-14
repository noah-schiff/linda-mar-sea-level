"""Fold site/ into one self-contained HTML file.

Produces two files, both with three.js, OrbitControls, the CSS, the app, and
every data file inlined:

  dist/linda-mar-explorer.html           full document, for double-clicking
  dist/linda-mar-explorer.artifact.html  body-only, for an Artifact host that
                                         supplies its own document skeleton

Two transforms, both load-bearing -- an earlier version of this script used ES
modules and a data:-URL importmap, and it silently failed to boot:

  1. ES modules become CLASSIC scripts. A strict CSP (the Artifact sandbox,
     for one) refuses a data:-URL importmap, so the app module never ran at
     all; and Chrome blocks module loading over file:// on CORS grounds, so
     double-clicking the bundle would have failed too. Classic inline scripts
     dodge both. three.js's single trailing `export{...}` is rewritten to a
     window.THREE assignment, and the two importers are rewritten to read from
     it. Each script is wrapped in a strict-mode IIFE, since classic scripts
     are sloppy-mode by default while modules are not.

  2. Data files are handed to the app's own fetch() calls by a shim that
     decodes base64 in-process. They are NOT data: URIs -- fetching one is
     still governed by CSP connect-src, which strict hosts deny. This way the
     page makes zero network requests, and app.js stays byte-identical to the
     version the hosted site serves.

    .\\.venv\\Scripts\\python.exe scripts\\bundle_site.py
"""

import base64
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
DIST = ROOT / "dist"
OUT_FULL = DIST / "linda-mar-explorer.html"
OUT_ARTIFACT = DIST / "linda-mar-explorer.artifact.html"

DATA_FILES = ["terrain.json", "terrain.bin", "shorelines.json", "shorelines.bin",
              "sealevel.json", "summary.json"]


def strict_iife(code: str) -> str:
    return "(function(){'use strict';\n" + code + "\n})();"


def three_as_global(src: str) -> str:
    """Rewrite three.js's trailing `export{a as A,b as B}` into window.THREE."""
    matches = list(re.finditer(r"export\s*\{", src))
    if len(matches) != 1:
        raise SystemExit(f"expected exactly 1 export in three.module.min.js, got {len(matches)}")
    start = matches[0].start()
    body = src[start:]
    inner = body[body.index("{") + 1: body.rindex("}")]

    pairs = []
    for item in inner.split(","):
        item = item.strip()
        if not item:
            continue
        if " as " in item:
            local, exported = (p.strip() for p in item.split(" as "))
        else:
            local = exported = item
        pairs.append(f"{json.dumps(exported)}:{local}")

    return strict_iife(src[:start] + "\nwindow.THREE={" + ",".join(pairs) + "};")


def orbit_as_global(src: str) -> str:
    """OrbitControls imports only the bare specifier `three` and exports one
    symbol, so it converts to a destructure + a global assignment."""
    src, n_imp = re.subn(r"import\s*\{([\s\S]*?)\}\s*from\s*['\"]three['\"];",
                         lambda m: f"const {{{m.group(1)}}} = window.THREE;", src, count=1)
    src, n_exp = re.subn(r"export\s*\{\s*OrbitControls\s*\};",
                         "window.OrbitControls = OrbitControls;", src, count=1)
    if not (n_imp and n_exp):
        raise SystemExit("OrbitControls import/export shape changed; update the transform")
    return strict_iife(src)


def app_as_global(src: str) -> str:
    src, a = re.subn(r"import \* as THREE from 'three';",
                     "const THREE = window.THREE;", src, count=1)
    src, b = re.subn(r"import \{ OrbitControls \} from '\./vendor/OrbitControls\.js';",
                     "const OrbitControls = window.OrbitControls;", src, count=1)
    if not (a and b):
        raise SystemExit("app.js import shape changed; update the transform")
    if re.search(r"^\s*import\s", src, re.M):
        raise SystemExit("app.js still has an unhandled import")
    return strict_iife(src)


def build_assets_shim() -> str:
    assets = {f"./data/{name}":
              base64.b64encode((SITE / "data" / name).read_bytes()).decode("ascii")
              for name in DATA_FILES}
    return (
        "<script>\n"
        "// Feed the inlined assets to the app's own fetch() calls -- decoded\n"
        "// in-process, so the page issues no network request of any kind.\n"
        f"const __ASSETS = {json.dumps(assets)};\n"
        "function __b64bytes(s) {\n"
        "  const bin = atob(s), n = bin.length, out = new Uint8Array(n);\n"
        "  for (let i = 0; i < n; i++) out[i] = bin.charCodeAt(i);\n"
        "  return out;\n"
        "}\n"
        "const __origFetch = window.fetch.bind(window);\n"
        "window.fetch = (u, ...rest) =>\n"
        "  Object.prototype.hasOwnProperty.call(__ASSETS, u)\n"
        "    ? Promise.resolve(new Response(__b64bytes(__ASSETS[u]), { status: 200 }))\n"
        "    : __origFetch(u, ...rest);\n"
        "</script>"
    )


def main() -> None:
    missing = [f for f in DATA_FILES if not (SITE / "data" / f).exists()]
    if missing:
        raise SystemExit(f"missing site data: {missing} -- run build_site.py first")

    html = (SITE / "index.html").read_text(encoding="utf-8")
    css = (SITE / "style.css").read_text(encoding="utf-8")

    scripts = "\n".join([
        build_assets_shim(),
        "<script>\n" + three_as_global(
            (SITE / "vendor" / "three.module.min.js").read_text(encoding="utf-8")) + "\n</script>",
        "<script>\n" + orbit_as_global(
            (SITE / "vendor" / "OrbitControls.js").read_text(encoding="utf-8")) + "\n</script>",
        "<script>\n" + app_as_global(
            (SITE / "app.js").read_text(encoding="utf-8")) + "\n</script>",
    ])

    html = html.replace('<link rel="stylesheet" href="./style.css">',
                        f"<style>\n{css}\n</style>")
    # The importmap only exists to resolve bare specifiers for the module
    # build; the classic-script bundle has no bare specifiers left to resolve.
    html = re.sub(r'<script type="importmap">.*?</script>', "", html, flags=re.S)
    html = html.replace('<script type="module" src="./app.js"></script>', scripts)

    for leftover in ('href="./style.css"', 'src="./app.js"', "./vendor/", "importmap",
                     'type="module"'):
        if leftover in html:
            raise SystemExit(f"bundle still references {leftover}")

    DIST.mkdir(parents=True, exist_ok=True)
    OUT_FULL.write_text(html, encoding="utf-8")
    print(f"Wrote {OUT_FULL}  ({OUT_FULL.stat().st_size/1e6:.2f} MB)")

    # Body-only variant: the Artifact host supplies <!doctype>/<html>/<head>/
    # <body>. <title> leads, because only the first 8 KB is scanned for it and
    # the inlined stylesheet alone is larger than that.
    body = re.search(r"<body[^>]*>(.*)</body>", html, re.S).group(1)
    style = re.search(r"<style>.*?</style>", html[:html.index("</head>")], re.S).group(0)
    artifact = "\n".join(["<title>Linda Mar Sea Level Explorer</title>", style, body.strip()])
    for banned in ("<!doctype", "<html", "<head", "<body"):
        if banned in artifact.lower():
            raise SystemExit(f"artifact variant still contains {banned}")
    OUT_ARTIFACT.write_text(artifact, encoding="utf-8")
    print(f"Wrote {OUT_ARTIFACT}  ({OUT_ARTIFACT.stat().st_size/1e6:.2f} MB)")
    print("  classic scripts (no ES modules, no data: URLs, no network)")


if __name__ == "__main__":
    main()
