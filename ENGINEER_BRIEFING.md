# Structural RCC Suite — Tester Briefing

Thanks for agreeing to try this out. Ten minutes of honest reaction from a
practicing engineer is worth more to this tool than anything else right now.

## What this is

A web-based preliminary structural design aid for reinforced concrete
elements (beams, columns, pad footings, slabs, stairs), supporting BS 8110
and Eurocode 2. It's built to cut the setup time on preliminary sizing —
upload a drawing, get spans pre-filled, get a sized member with a full
audit trail of what was and wasn't checked.

**It is explicitly not a construction-ready design tool.** Every result
carries a stated set of limitations, and some checks are marked
`NOT CHECKED` rather than faked. That's intentional — see "What to look for"
below.

## Link

`[paste your live Streamlit URL here before sending]`

No installation needed — it runs in your browser. No login required (the
license screen has been switched off for this test build).

## What I'd like you to actually do

Please don't just read the numbers — click through it like you would a
real preliminary sizing task:

1. **Run a beam → column → footing in sequence**, using the 🔗 "pull from
   result" checkboxes in Column and Footing Design so loads carry through
   automatically. Does the load path make sense to you?
2. **Try the CAD/PDF Drawing Importer** with a real plan of yours (or any
   PDF/DXF you have handy). See what it detects vs. flags as "not
   detected" — tell me if that distinction is clear or confusing.
3. **Deliberately undersize something** (a shallow beam depth, a small
   column with a real applied moment) so it FAILs, and try the "🔁 Retry
   with..." button. Does the suggested fix make sense?
4. **Download a calc sheet (HTML) and a reinforcement detail (DXF)** for
   at least one element. Open the DXF in whatever CAD software you use —
   does it look like something you'd actually work from, or does it feel
   like a toy?
5. **Open the Project Dashboard** after calculating a few elements. Is the
   summary useful, or noise?

## What to look for specifically

- Do the **PASS / FAIL / WARNING / NOT CHECKED** labels feel honest? Would
  you trust a green PASS from this tool the way you'd trust your own hand
  calc?
- Are there any numbers that look **wrong**, not just incomplete? (Wrong
  is a much bigger problem than incomplete — flag those first.)
- Is anything **missing** that you'd genuinely reach for on a real
  preliminary design — column biaxial bending is implemented (simplified),
  but slab column moment transfer, wind/lateral loads, and a full frame
  analysis are not yet.
- Does the language and layout make sense to someone who hasn't seen the
  tool before, or does it assume too much?

## How to give feedback

Whatever's easiest for you — a message back to me, a marked-up screenshot,
or a quick call. I'd rather have "this number looks off, not sure why" than
nothing, even if you can't pin down the exact cause.

Thank you — this genuinely can't get better without a real engineer's eyes
on it.
