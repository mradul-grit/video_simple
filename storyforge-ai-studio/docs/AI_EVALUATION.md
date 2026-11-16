# AI evaluation protocol

## Build a consented evaluation corpus
- Collect short clips from consenting test speakers; allow deletion and do not repurpose data.
- Include Hindi, Indian English and Hinglish/code-switching, regional accents, quiet/loud speakers, mild background noise, names, technical words and natural disfluencies.
- Create human-corrected reference transcripts and timestamps for a subset.
- Include examples where silence is meaningful (dramatic pause, emphasis, breath, joke timing) and where filler removal is beneficial.
- Label visual beats and suitable/unsuitable image candidates.

## Metrics
- Word error rate / character error rate per language slice; do not report one aggregate only.
- Timestamp boundary error.
- Cut precision/recall and percentage of harmful cuts.
- Editorial caption factual support and readability; percentage with valid transcript citations.
- Visual relevance acceptance/rejection, licensing metadata completeness and timestamp placement error.
- Render artifact rate, A/V sync offset and export success.

## Release gate
Do not market a language or automatic feature as reliable until it passes an agreed human evaluation threshold. Publish limitations and provide easy correction controls.
