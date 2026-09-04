# Hand-written ground truth

These files are the denominator of every recall and specificity figure this project quotes. They were moved out of `local/` on 2026-08-18 for one reason: being gitignored made them unversioned, unreviewable and one `rm -rf local/` from gone.

## What is here

`<population>.json` — `edge_hardness` judgements, keyed by filename. Counted 2026-09-04: **1,038 entries, 981 carrying a classification** (`pixel_art` 552, `antialiased` 391, `unsuitable_no_edges` 31, `ambiguous` 7); the remaining 57 are prose notes explaining why an asset was not classifiable.

⚠️ **Several files elsewhere in this repo still say "714 judgements", including `populations.py`.** That figure is stale by 267. Derive the count rather than restating it — see `gif-deferred-list.md`, `[P3 · XS]`.

## What is NOT here, and where it is

⚠️ **Labels for the PROTECTION decision — the coin-flip `--auto` refuses on — are collected by a different tool and live in a different repo.**

`--auto` refuses on **12.8%** of assets overall (39 of 304); the **enclosure question specifically** is **10.2%** (31 of 304) and the fade question 2.6%. ⚠️ Do not quote 10.2% alone as "the refusal rate" — `references/lessons.md` flags that exact figure as the original pooled measurement, stale in the unsafe direction because it predates the fade gate. That is a labelling problem, and this directory holds **zero** labels for it while holding 981 for `edge_hardness`.

The **Devoid** app (`/Applications/Claude Code/Devoid`, `github.com/HarkiratMangat/Devoid`) asks that question visually and records every answer as a labelled row — outline colour, enclosure ratio, frame counts, bbox, verdict — at:

```
Devoid/labels/protection.jsonl      (tracked in that repo)
```

⚠️ **That file does not exist yet** — it is created at Devoid's `PLAN.md` stage 5.1. If it is absent, the labels have not started being collected, not been deleted.

It is deliberately not written here: Devoid owns its own data. **This pointer exists because nothing else in this repo would tell you those labels exist**, and a session working on the autonomy goal would look here first. If that path moves, fix this line.
