#!/usr/bin/env python3
"""THE population registry -- one place that knows what corpora exist.

Why this file exists (2026-08-18): a new candidate measure used to cost four
script edits, because extract.py, final_run.py, sprite_run.py and corpus_run.sh
each hardcoded their own directory lists. Two populations therefore existed only
inside the script that had most recently needed them, and the labelled 31-asset
set -- ALL of it fully opaque GIFs -- was the one every threshold got scored
against. Two brand-new rules passed that scoring on 2026-08-18 and were broken
hours later by content types the sample did not contain.

So: add a population HERE, and every consumer sees it.

    from populations import iter_assets, score
    recs = {k: {'label': lab, 'pop': pop, 'pred': my_measure(path)}
            for k, path, pop, lab in iter_assets()}
    print(score(recs))

Labels are written by eye and never by a measure the script itself computes -- a
corpus labelled by the thing under test proves only that the thing agrees with
itself (references/lessons.md SS23).

WHERE THE LABELS LIVE, and why it changed on 2026-08-18: they used to sit as a
LABELS.json beside each corpus, i.e. inside `local/`, i.e. GITIGNORED. Hours of
hand-labelling -- 714 judgements, the most expensive artefact this project owns,
and the denominator of every recall and specificity figure ever quoted -- were
one `rm -rf local/` from gone, unversioned and unreviewable. They now live in
labels/<population>.json NEXT TO THIS FILE, in tracked space. The image corpora
stay in `local/`: they are third-party assets and stay out of git deliberately.
A harness whose ground truth is untracked is not a control (see this repo's
CLAUDE.md, "A discipline is not a control").
"""
import json, os, glob

ROOT = "/Applications/Claude Code/Gif-Background-Remover"
LABELS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'labels')
EM = os.path.join(ROOT, "local/Diors-builds Emojis")
EXTS = ('.gif', '.png', '.webp', '.avif', '.jpg', '.jpeg', '.apng')

# A label that is not a claim about edge structure. Scoring skips these on
# purpose: 30 flat overlay plates would otherwise hand any hard-edge rule 30
# free true negatives that test nothing at all.
EXCLUDED_LABELS = ('unsuitable_no_edges', 'ambiguous')

#: name -> (directory, labels-source, what it falsifies)
POPULATIONS = {
    'labelled': dict(
        dir=os.path.join(EM, 'others'), labels='labelled.json', recurse=False,
        what='31 hand-labelled assets, 25 pixel art / 6 antialiased. ALL FULLY OPAQUE GIFs.',
        blind_to='anything with an alpha channel; anything not a GIF.'),
    'alphas': dict(
        dir=os.path.join(EM, 'others/alphas'), labels='alphas.json', recurse=False,
        what='37 already-background-removed assets, 22 pixel art / 15 antialiased; 35 hard-alpha cutouts + 2 soft-alpha PNGs.',
        blind_to='opaque sources; large art (most are <=500px).'),
    'sprites': dict(
        dir=os.path.join(ROOT, 'local/itch.io sprites'), labels='sprites.json', recurse=True,
        what='524 itch.io sprite-pack files, 493 pixel art / 31 unsuitable. The only ALPHA-CARRYING pixel-art population.',
        blind_to='antialiased art -- it contains none, so it cannot detect a false positive.'),
    'emoji': dict(
        # A ROSTER, not a default (2026-08-18). With default_label the membership of the corpus
        # that 148 of the negatives are counted from was whatever happened to be in six folders.
        dir=EM, labels='emoji.json', recurse=False, default_label='antialiased',
        subdirs=["Arrows", "Database emojis", "codm emojis", "interface emojis", "more", "untitled folder"],
        what='122 vector emoji/icons, presumed antialiased -- the main false-positive falsifier. COUNTED, not remembered: the six folders hold 130 files, of which 122 carry an image extension (2 .zip, 1 .psd and 5 extensionless directories are not assets). The tracker carried "145" for weeks; that figure was never derived.',
        blind_to='pixel art -- a rule that fires on nothing scores perfectly here.'),
    'small_aa': dict(
        dir=os.path.join(ROOT, 'local/corpus small sizes'), labels='small_aa.json', recurse=False,
        what='150 antialiased icons and custom emoji at 32-128px -- the population the corpus was MISSING. '
             'Before it, exactly ONE antialiased asset sat in the 400-3,000 art-pixel band against 99 pixel-art '
             'ones, so every measure built for small sprites scored perfectly and was untestable (SS29.12).',
        blind_to='pixel art -- it contains none. Large art: everything over 128px was moved to _excluded/, '
                 'because the corpus already held 133 antialiased assets of that class.'),
    'small_aa_quantized': dict(
        dir=os.path.join(ROOT, 'local/corpus small quantized'), labels='small_aa_quantized.json', recurse=False,
        what='117 DERIVED assets: the small_aa originals re-exported as GIF at 16-64 colours. Not a synthetic '
             'fixture -- this is what a small GIF icon IS, and it is the transformation that puts real '
             'antialiased art into the 16-64 colour band where it becomes indistinguishable from hand-authored '
             'pixel art. Every asset whose source ramps did not survive is in _excluded/.',
        blind_to='pixel art. ⚠️ DERIVED -- each one shares a source with an asset in small_aa, so the two '
                 'populations are NOT independent and a pooled figure over both double-counts the artwork.'),
    'gradient_beds': dict(
        dir=os.path.join(ROOT, 'local/corpus gradient beds'), labels=None, recurse=False,
        default_label='ambiguous',
        what='23 assets carrying a smooth horizontal alpha ramp, built with the ACTUAL nameplate-bed curve '
             'and palette from Dior\'s Builds (utils/nameplatePalettes.js: four stops 0 -> 0.08 -> 0.08 -> 0.5, '
             'twelve dark-theme hexes), reproduced in Python so nothing in that repo is executed or modified '
             'and no network or Cloudinary is involved. Harkirat\'s suggestion, because gradient-heavy source '
             'material is genuinely hard to find in the wild.',
        blind_to='EVERYTHING about hardness -- labelled `ambiguous` on purpose, so it is excluded from every '
                 'recall and specificity figure. Its job is the gifsicle colour-dither question, which is about '
                 'what the ENCODER does to a smooth ramp, not about what kind of art something is. That is also '
                 'why a constructed fixture is legitimate here and was not for the detection corpus.'),
    'trial': dict(
        dir=os.path.join(ROOT, 'local/Corpus Trial Gifs'), labels=None, recurse=False,
        glob='*.gif', default_label='antialiased',
        what='The 6 assets the 2026-08-19 three-agent trial and its follow-up were run on: five '
             '640x640 flat vector icons on white (galaxy, growth, hurricane, rocket, satellite) '
             'plus paper-plane, supplied by Harkirat 2026-08-20. Every one of them is a case some '
             'gate here could NOT see: the trial found five defects in ninety minutes on a build '
             'that had just passed the 797-asset corpus, an xhigh code review and a full render '
             'diff, because all three compare the product against itself or a label rather than '
             'against what a user wanted. paper-plane is the sharpest of them -- it exits the '
             'canvas at frame 41 of 98, reproducing in v6 the same "pixels stuck mid-animation" '
             'Harkirat saw in v3.x, and it independently exercises BOTH 2026-08-20 P1 fixes: the '
             'fully-transparent-frame GIF refusal, and the area-conditioned incidental-region '
             'verdict (its two design regions sit at enclosure_ratio 0.85, under the old 0.9 bar, '
             'so the previous code would have deleted them).',
        blind_to='pixel art entirely, and small sample. These are 6 easy true negatives for any '
                 'hard-edge rule, so they buy specificity almost for free -- read the per-population '
                 'split, never the pooled figure, exactly as with `corpus`. Their real job is the '
                 'RENDER gate, where they are the only assets in it that a real user actually '
                 'complained about.'),
    'dark_bg': dict(
        dir=os.path.join(ROOT, 'local/corpus dark'), labels=None, recurse=False,
        default_label='ambiguous',
        what='105 assets on FLAT OPAQUE NON-WHITE backgrounds -- measured on the final set '
             '2026-08-20: 55 dark (<80 luminance), 54 saturated (chroma >=60), 65 animated. '
             'Supplied by Harkirat 2026-08-20 to close the one gap the rest of the corpus could '
             'not test around: before this, 76 of 97 opaque-background assets were white-ish, only '
             '5 were dark, and all 18 non-white ones came from a single population. 119 were '
             'supplied; 2 byte-identical duplicates were dropped, 6 with no keyable background '
             'moved to _excluded/ and 6 whose background CHANGES COLOUR mid-animation to '
             '_changing_bg/ (that last set is the only demonstration anywhere of the '
             'changing-background defect, and is deliberately kept out of scoring rather than '
             'deleted).',
        blind_to='EVERYTHING about hardness -- labelled `ambiguous` ON PURPOSE, so it is excluded '
                 'from every recall and specificity figure. Its job is the RING METRIC and the '
                 'narrow fringe constants on a non-white background, not classification. Labelling '
                 '105 assets by blanket would be the exact error SS32 records; labelling them by '
                 'eye would cost hours and buy nothing this population is for. '
                 '⚠️ AND IT IS NOT UNIFORMLY FLAT-KEYABLE: measured 2026-08-20 on a 24-asset '
                 'falsifier sample (the 12 darkest plus the 12 most saturated), only 13 have a '
                 'border that is >=90% one colour -- the other 11 are photos or gradients with a '
                 'dark cast. Never quote a pooled render figure over this population; split it by '
                 'border flatness first, or it will report this tool failing at content it does '
                 'not claim to handle.'),
    'corpus': dict(
        dir=os.path.join(ROOT, 'local/corpus-webp-avif-2026-08-17'), labels=None, recurse=False,
        glob='*_ORIGINAL.gif', default_label='antialiased',
        what='5 originals from the WebP/AVIF corpus, antialiased.',
        blind_to='pixel art; small sample.'),
}


def _label_map(spec):
    if not spec.get('labels'):
        return None
    p = os.path.join(LABELS_DIR, spec['labels'])
    if not os.path.exists(p):
        raise SystemExit(f"populations: {p} is missing -- a population without labels cannot be scored.")
    return json.load(open(p))['labels']


def check_corpora():
    """Fail LOUDLY when a corpus directory is absent, rather than scoring zero assets.

    The image corpora are gitignored, so a fresh clone has the labels and none of the
    pictures. Without this, `iter_assets` yields nothing and every score comes back a
    perfect 1.000 over an empty population -- a vacuous pass, which is worse than an error.
    """
    missing = [f"{n}: {s['dir']}" for n, s in POPULATIONS.items() if not os.path.isdir(s['dir'])]
    if missing:
        raise SystemExit("populations: corpus directories are missing, so nothing can be scored:\n  "
                         + "\n  ".join(missing))


def iter_assets(populations=None, include_excluded=False):
    """Yield (key, path, population, label). `key` is stable and unique across populations."""
    check_corpora()
    want = list(POPULATIONS) if populations is None else list(populations)
    for name in want:
        spec = POPULATIONS[name]
        labels = _label_map(spec)
        base = spec['dir']
        if spec.get('subdirs'):
            # ⚠️ The extension filter is NOT optional here, and leaving it out was a
            # real bug: this branch was yielding .zip, .psd and extensionless
            # DIRECTORIES as assets, so the emoji population reported 130 members
            # when 122 are images. Found by enumerating the folder rather than by
            # reading the count -- the same way the "145-asset" figure in the
            # tracker turned out never to have been derived at all.
            paths = [p for d in spec['subdirs']
                     for p in sorted(glob.glob(os.path.join(base, d, '*')))
                     if p.lower().endswith(EXTS) and not os.path.basename(p).startswith('.')]
        elif spec.get('glob'):
            paths = sorted(glob.glob(os.path.join(base, spec['glob'])))
        elif spec.get('recurse'):
            paths = sorted(os.path.join(dp, f) for dp, _, fn in os.walk(base) for f in fn
                           if f.lower().endswith(EXTS) and not f.startswith('.'))
        else:
            paths = sorted(p for p in glob.glob(os.path.join(base, '*'))
                           if p.lower().endswith(EXTS) and not os.path.basename(p).startswith('.'))
        for p in paths:
            rel = os.path.relpath(p, base)
            if labels is not None:
                if rel not in labels:
                    continue                       # LABELS.json is the roster for a labelled population
                lab = labels[rel]
            else:
                lab = spec['default_label']
            if lab in EXCLUDED_LABELS and not include_excluded:
                continue
            yield f"{name}/{rel}", p, name, lab


def counts():
    out = {}
    for name in POPULATIONS:
        scored = sum(1 for _ in iter_assets([name]))
        allp = sum(1 for _ in iter_assets([name], include_excluded=True))
        out[name] = {'scored': scored, 'total': allp, 'excluded': allp - scored}
    return out


def score(records, pred_key='pred'):
    """records: {key: {'label':…, 'pop':…, pred_key: bool}} -> nested accuracy report.

    `pred` is True when the measure says HARD-EDGED / pixel art. Reported per
    population AND, for `sprites`, per pack -- one pack is 78% of that
    population, so a pooled number there is mostly a statement about it.
    """
    rep = {}
    for k, r in records.items():
        if r.get('label') in EXCLUDED_LABELS or r.get(pred_key) is None:
            continue
        pop = r['pop']
        buckets = [pop]
        if pop == 'sprites':
            buckets.append('sprites::' + k.split('/', 1)[1].split('/')[0])
        for b in buckets:
            d = rep.setdefault(b, {'tp': 0, 'fn': 0, 'fp': 0, 'tn': 0, 'n': 0})
            hit = bool(r[pred_key])
            pix = r['label'] == 'pixel_art'
            d['n'] += 1
            d['tp' if (pix and hit) else 'fn' if pix else 'fp' if hit else 'tn'] += 1
    for d in rep.values():
        pos, neg = d['tp'] + d['fn'], d['fp'] + d['tn']
        d['recall'] = round(d['tp'] / pos, 4) if pos else None
        d['specificity'] = round(d['tn'] / neg, 4) if neg else None
    tot = {'tp': 0, 'fn': 0, 'fp': 0, 'tn': 0, 'n': 0}
    for b, d in rep.items():
        if b.startswith('sprites::'):
            continue
        for k2 in tot:
            tot[k2] += d[k2]
    pos, neg = tot['tp'] + tot['fn'], tot['fp'] + tot['tn']
    tot['recall'] = round(tot['tp'] / pos, 4) if pos else None
    tot['specificity'] = round(tot['tn'] / neg, 4) if neg else None
    rep['ALL'] = tot
    return rep


if __name__ == '__main__':
    import pprint
    pprint.pprint(counts())
    tot = sum(v['total'] for v in counts().values())
    print(f"{tot} assets across {len(POPULATIONS)} populations; "
          f"{sum(v['scored'] for v in counts().values())} scoreable.")
