# Changelog

## 0.1.0 (2026-11-02)

First working release.

- Tape format (JSONL, versioned) with canonical JSON hashing.
- `record`, `playback` and `counterfactual` sessions; `tapedeck.chat` and `@tapedeck.tool`.
- Matcher with keyed and positional ordering, `ignore`/`casefold` fields, per-tool
  `on_miss: live` for pure reads, nearest-call miss messages; `external` tools are never
  called outside recording.
- Key-value and append-log simulators, seeded from the tape; final state derived from the
  trajectory for recorded runs.
- Verifiers: `called`, `never_called`, `called_before`, `max_steps`, `cost_under`, `state`,
  `output_contains`.
- Parallel N-run suite runner with a cost budget.
- Statistical gate: Wilson intervals, one-sided Fisher exact test, Holm-Bonferroni,
  minimum effect; false-alarm and power simulation (`tapedeck power`).
- Behavior diff: Needleman-Wunsch alignment of tool sequences, explained in one sentence.
- CLI (`record`, `playback`, `baseline`, `test`, `power`), HTML and Markdown reports.
- Composite GitHub Action with a sticky PR comment.
- Example support agent with 8 cases, 3 prompts and an offline scripted model.
