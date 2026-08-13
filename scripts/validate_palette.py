"""Check the chart palettes used by plot_summary.py are colorblind-safe.

A Python port of the `dataviz` skill's `validate_palette.js` (Node isn't
installed on this machine, and the point of those checks is that they're
computed rather than eyeballed). Thresholds, the Machado-Oliveira-Fernandes
(2009) severity-1.0 CVD matrices, and the OKLab math are copied from that
script unchanged.

The port was self-tested against the reference numbers documented in the
skill's own palette.md before being trusted -- see SELF_TESTS below, which
run first and abort if the port has drifted.

    .\\.venv\\Scripts\\python.exe scripts\\validate_palette.py

Exits 0 if every palette passes.
"""
import math
import sys

BAND = {"light": (0.43, 0.77), "dark": (0.48, 0.67)}
CHROMA_FLOOR = 0.10
CVD_TARGET, CVD_FLOOR = 8.0, 6.0
NORMAL_FLOOR = 15.0
CONTRAST_MIN = 3.0
DEFAULT_SURFACE = {"light": "#fcfcfb", "dark": "#1a1a19"}
ORDINAL_MIN_DL = 0.06
ORDINAL_LIGHT_FLOOR = 2.0

MACHADO = {
    "protan": [[0.152286, 1.052583, -0.204868],
               [0.114503, 0.786281, 0.099216],
               [-0.003882, -0.048116, 1.051998]],
    "deutan": [[0.367322, 0.860646, -0.227968],
               [0.280085, 0.672501, 0.047413],
               [-0.011820, 0.042940, 0.968881]],
    "tritan": [[1.255528, -0.076749, -0.178779],
               [-0.078411, 0.930809, 0.147602],
               [0.004733, 0.691367, 0.303900]],
}


def hex2srgb(h):
    h = h.strip().lstrip("#")
    return [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]


def s2lin(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def lin(h):
    return [s2lin(c) for c in hex2srgb(h)]


def rel_lum(h):
    r, g, b = lin(h)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    hi, lo = sorted([rel_lum(a), rel_lum(b)], reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def oklab_from_lin(rgb):
    r, g, b = rgb
    l = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    m = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    s = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    return [
        0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
        1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
        0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s,
    ]


def oklab(h):
    return oklab_from_lin(lin(h))


def oklch(h):
    L, a, b = oklab(h)
    return L, math.hypot(a, b)


def okhue(h):
    _, a, b = oklab(h)
    return (math.degrees(math.atan2(b, a)) % 360 + 360) % 360


def simulate(h, kind):
    r, g, b = lin(h)
    M = MACHADO[kind]
    return [min(1, max(0, M[i][0] * r + M[i][1] * g + M[i][2] * b)) for i in range(3)]


def delta_e(h1, h2, kind=None):
    a = oklab_from_lin(simulate(h1, kind) if kind else lin(h1))
    b = oklab_from_lin(simulate(h2, kind) if kind else lin(h2))
    return 100 * math.dist(a, b)


def validate(palette, mode="light", surface=None, pairs="adjacent"):
    surface = surface or DEFAULT_SURFACE[mode]
    lo, hi = BAND[mode]
    report, ok = [], True

    offband = [(c, round(oklch(c)[0], 3)) for c in palette if not (lo <= oklch(c)[0] <= hi)]
    if offband:
        ok = False
    report.append(("Lightness band", not offband,
                   f"outside band: {offband}" if offband else f"all {len(palette)} inside L {lo}-{hi}"))

    lowc = [(c, round(oklch(c)[1], 3)) for c in palette if oklch(c)[1] < CHROMA_FLOOR]
    if lowc:
        ok = False
    report.append(("Chroma floor", not lowc,
                   f"below floor (reads gray): {lowc}" if lowc else f"all {len(palette)} >= {CHROMA_FLOOR}"))

    n = len(palette)
    if pairs == "all":
        pairlist = [(i, j) for i in range(n) for j in range(i + 1, n)]
    else:
        pairlist = [(i, i + 1) for i in range(n - 1)]
    label = "all-pairs" if pairs == "all" else "adjacent"

    worst = None
    for kind in ("protan", "deutan"):
        for i, j in pairlist:
            d = delta_e(palette[i], palette[j], kind)
            if worst is None or d < worst[0]:
                worst = (d, kind, palette[i], palette[j])
    tri = min([delta_e(palette[i], palette[j], "tritan") for i, j in pairlist], default=99)
    wd = worst[0] if worst else 99
    cvd_state = "pass" if wd >= CVD_TARGET else ("floor" if wd >= CVD_FLOOR else "fail")
    if cvd_state == "fail":
        ok = False
    report.append(("CVD separation", cvd_state,
                   f"worst {label} {worst[3]}<->{worst[2]} dE {wd:.1f} ({worst[1]}) - tritan {tri:.1f}"
                   if worst else "n/a"))

    nworst = None
    for i, j in pairlist:
        d = delta_e(palette[i], palette[j])
        if nworst is None or d < nworst[0]:
            nworst = (d, palette[i], palette[j])
    nd = nworst[0] if nworst else 99
    nor_state = "pass" if nd >= NORMAL_FLOOR else "fail"
    if nor_state == "fail":
        ok = False
    report.append(("Normal-vision floor", nor_state,
                   f"worst {label} {nworst[2]}<->{nworst[1]} dE {nd:.1f} (normal)" if nworst else "n/a"))

    low = [(c, round(contrast(c, surface), 2)) for c in palette if contrast(c, surface) < CONTRAST_MIN]
    report.append(("Contrast vs surface", "relief" if low else "pass",
                   f"below {CONTRAST_MIN}:1 - relief required (visible labels or table view): {low}"
                   if low else f"all {len(palette)} >= {CONTRAST_MIN}:1"))

    return report, ok


def validate_ordinal(palette, mode="light", surface=None):
    surface = surface or DEFAULT_SURFACE[mode]
    report, ok = [], True
    Ls = [oklch(c)[0] for c in palette]

    order = sorted(range(len(Ls)), key=lambda i: Ls[i])
    fwd = all(v == i for i, v in enumerate(order))
    rev = all(v == len(Ls) - 1 - i for i, v in enumerate(order))
    mono = fwd or rev
    if not mono:
        ok = False
    report.append(("Lightness monotone", mono,
                   "steps read light->dark" if mono else f"out of order - L {[round(l,3) for l in Ls]}"))

    gaps = [abs(Ls[i + 1] - Ls[i]) for i in range(len(Ls) - 1)]
    thin = [(palette[i], palette[i + 1], round(g, 3)) for i, g in enumerate(gaps) if g < ORDINAL_MIN_DL]
    if thin:
        ok = False
    report.append(("Adjacent dL", not thin,
                   f"steps too close: {thin}" if thin else f"all gaps >= {ORDINAL_MIN_DL}"))

    by_l = sorted(palette, key=lambda c: oklch(c)[0])
    lightest = by_l[-1] if mode == "light" else by_l[0]
    cr = contrast(lightest, surface)
    if cr < ORDINAL_LIGHT_FLOOR:
        ok = False
    report.append(("Light-end contrast", cr >= ORDINAL_LIGHT_FLOOR,
                   f"{lightest} at {cr:.2f}:1 vs surface"
                   + ("" if cr >= ORDINAL_LIGHT_FLOOR else f" - below {ORDINAL_LIGHT_FLOOR}:1 floor")))

    hues = [okhue(c) for c in palette]
    spread = max(hues) - min(hues)
    if spread > 180:
        spread = 360 - spread
    one_hue = spread <= 40
    if not one_hue:
        ok = False
    report.append(("Single hue", one_hue,
                   f"hue spread {spread:.0f}deg" + ("" if one_hue else " - >40deg, not a one-hue ramp")))

    return report, ok


GLYPH = {True: "PASS", False: "FAIL", "pass": "PASS", "floor": "WARN", "fail": "FAIL", "relief": "WARN"}


def run(name, palette, ordinal=False, mode="light", surface=None, pairs="adjacent"):
    surf = surface or DEFAULT_SURFACE[mode]
    report, ok = (validate_ordinal(palette, mode, surf) if ordinal
                  else validate(palette, mode, surf, pairs))
    kind = "ordinal ramp" if ordinal else f"categorical ({pairs})"
    print(f"\n{name}  [{mode}, surface {surf}, {kind}] {len(palette)} slots")
    for check, state, detail in report:
        print(f"  [{GLYPH.get(state, state):<4}] {check:<22} {detail}")
    print(f"  -> {'ALL CHECKS PASS' if ok else 'FAILED - fix the marked checks'}")
    return ok


# Reference values documented in the dataviz skill's palette.md for the
# shipped 8-slot categorical order. If the port is faithful it reproduces
# these exactly; if it doesn't, none of the results below can be trusted.
SHIPPED_8 = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100",
             "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
SELF_TESTS = [
    ("adjacent CVD", lambda: min(delta_e(SHIPPED_8[i], SHIPPED_8[i + 1], k)
                                 for i in range(7) for k in ("protan", "deutan")), 9.1),
    ("adjacent normal-vision", lambda: min(delta_e(SHIPPED_8[i], SHIPPED_8[i + 1])
                                           for i in range(7)), 19.6),
]


def self_test():
    print("Self-test vs. the skill's documented reference values:")
    ok = True
    for name, fn, expected in SELF_TESTS:
        got = fn()
        good = abs(got - expected) < 0.05
        ok &= good
        print(f"  [{'PASS' if good else 'FAIL'}] {name:<24} got {got:.1f}, expected {expected}")
    return ok


if __name__ == "__main__":
    if not self_test():
        print("\nPort no longer reproduces the reference values -- not validating.")
        sys.exit(2)

    results = []
    # plot_summary.py panels 1 & 2 share one grammar: blue = smoothed signal,
    # orange = fitted trend. Adjacent-pair checks (lines).
    results.append(run("Time-series: signal blue + trend orange", ["#2a78d6", "#eb6834"]))
    # plot_summary.py panel 3 flood zones. ORDERED (already wet -> Int 2100 ->
    # High 2100), so these take the ordinal checks, not the categorical ones:
    # a correct one-hue ramp fails the categorical lightness-band and chroma
    # gates by design (it is built to span lightness and to go pale at one end).
    flood = ["#86b6ef", "#2a78d6", "#104281"]
    results.append(run("Flood zones: ordinal blue ramp", flood, ordinal=True))

    # Informational: the ramp steps also stay mutually distinguishable as
    # filled areas. Reported, not gated -- the ordinal checks above are the
    # gate for an ordered ramp.
    worst_cvd = min(delta_e(a, b, k) for i, a in enumerate(flood)
                    for b in flood[i + 1:] for k in ("protan", "deutan"))
    worst_nrm = min(delta_e(a, b) for i, a in enumerate(flood) for b in flood[i + 1:])
    print(f"\nFlood ramp mutual separation (informational): "
          f"worst CVD dE {worst_cvd:.1f}, worst normal-vision dE {worst_nrm:.1f}")

    print(f"\n{'ALL PALETTES PASS' if all(results) else 'FAILED'}")
    sys.exit(0 if all(results) else 1)
