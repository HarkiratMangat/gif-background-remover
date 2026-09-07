# Hand-written ground truth

These files are the denominator of every recall and specificity figure this project quotes. They were moved out of `local/` on 2026-08-18 for one reason: being gitignored made them unversioned, unreviewable and one `rm -rf local/` from gone.

## What is here

`<population>.json` — `edge_hardness` judgements, keyed by filename. Counted 2026-09-04: **1,038 entries, 981 carrying a classification** (`pixel_art` 552, `antialiased` 391, `unsuitable_no_edges` 31, `ambiguous` 7); the remaining 57 are prose notes explaining why an asset was not classifiable.

⚠️ **Several files elsewhere in this repo still say "714 judgements", including `populations.py`.** That figure is stale by 267. Derive the count rather than restating it — see `gif-deferred-list.md`, `[P3 · XS]`.

## What is NOT here, and where it is

⚠️ **Labels for the PROTECTION decision — the coin-flip `--auto` refuses on — are collected by a different tool and live in a different repo.**

`--auto` refuses on **12.8%** of assets overall (39 of 304); the **enclosure question specifically** is **10.2%** (31 of 304) and the fade question 2.6%. ⚠️ Do not quote 10.2% alone as "the refusal rate" — `references/lessons.md` flags that exact figure as the original pooled measurement, stale in the unsafe direction because it predates the fade gate. That is a labelling problem, and this directory holds **zero** labels for it while holding 981 for `edge_hardness`.

⚠️ **THEY ARE NOT BEING COLLECTED, AND THIS FILE SAID THEY WERE (corrected 2026-09-07 14:15 EDT).**

The **Devoid** app (`/Applications/Claude Code/Devoid`) asks the enclosure question visually, and this README said it *"records every answer as a labelled row"* at `Devoid/labels/protection.jsonl`. **It does not.** The writer was built, shipped, and then removed on 2026-09-07 at Devoid's owner's instruction -- *"drop the labels from the app, it's just adding friction and the repo has its own corpus that i supply it anyway."* The file and its history stay in that repo (`Devoid/labels/README.md`); nothing appends to it.

So the count here is still **zero**, and there is currently **no collector** for the protection decision. That is the honest state, not a broken one:

* the answers a person gives in Devoid steer that render and are recorded in its `jobs.jsonl` alongside the rest of the run's settings -- as work, not as ground truth, and not in a schema anything here can score against;
* building a collector again is a decision for this repo, since this repo is what would consume the labels. Filed as `[P2 · S]` in `gif-deferred-list.md`.

**This pointer stays because nothing else here would tell you the gap exists** -- a session working on the autonomy goal would look in this directory first, find 981 `edge_hardness` judgements, and reasonably assume the harder question was covered too.
