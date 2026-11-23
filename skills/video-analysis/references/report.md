# Report and follow-up evidence

## Write the report for a reader who will ask a second question

Lead with a substantive content conclusion. Summarize what the speaker argues and the agent's evidence-bound interpretation. Separate material questions of causality or external accuracy from what the video itself establishes. Preserve the speaker's qualifications and examples.

Use a full timeline of meaningful content changes. Split a long model clip into finer report entries when it contains multiple claims, numerical values, examples, or visible actions. A general analysis follows from the start through the end, and a targeted analysis covers the portions relevant to the user's questions. Every entry has a time range, useful topic terms, substantive observed detail, and a source pointer. Include exact names, examples, task steps, visible labels and appropriate timecodes where the evidence supports them.

For numbers, retain what was measured, its unit, population or denominator, time period, comparison or forecast basis, and how the video attributes it. Check the original figure or graphic when a transcription differs. When a claim is an estimate, forecast or speaker's explanation, say so. Leave unresolved fields explicit. A chart is evidence about the video's presentation, and the actual source research answers questions about methods and external validity.

For an alleged operation, describe visible before and after states, an actual action, and its outcome when present. Demonstrations can coexist with narration, tutorial slides or stock footage. Confirm the evidence type at the relevant frames. In the trial, illustrated lists of nursing tasks and AI-assisted work were initially mistaken for depicted actions. Focused original frames showed the words and background illustrations, so the report described narrated examples.

Add a practical set of follow-up questions with direct answers and evidence. Cover exact steps and examples as well as headline topics. Useful queries include which people a percentage applies to, the exact reasons a speaker lists, which action is visible, and what inputs or results were shown. The appropriate number of entries follows the content of the source. Give denser detail where it supports materially different questions.

In the chat response, include the content conclusion and a link to the detailed report. Include performance measurements when they are part of the user's goal.

## Save a JSON index beside the report

Use an index such as `07-evidence-index.json` in the same video-specific Drive folder. The human-readable report may use headings and prose. The JSON index should contain the following fields so an agent can locate evidence without reading an entire transcript.

| Field | Required content |
| --- | --- |
| `video` | Source title or ID, original source locator, and `duration_seconds`. |
| `evidence` | Time-ordered entries with `id`, `title`, `start_seconds`, `end_seconds`, and `spoken_summary` and/or `visual_evidence`. Include keywords, relevant numbers, `scope_or_missing_detail`, and at least one source reference. |
| Evidence pointers | Use `youtube_at_start` or `playback_link` for navigation. Add `audio_segment_indexes`, `wemm_clip_indexes`, and `frames` with verified timestamp, page, row, column, and file URL where useful. Use the existing raw artifact indexes and clip IDs. |
| `numeric_claims` | Entries with `evidence_id`, `value` and `scope`, plus attribution and timing when available. An empty list is valid for a video with no numerical claims. |
| `question_answers` | Entries with `question`, `answer` and `evidence`, an array of objects with `id` values pointing to existing evidence. |
| `artifact_links` | Actual Drive addresses for raw transcription, model observations, frames, and verified audit material. |

An older index with these fields remains usable. The optional `counts` object uses `evidence_intervals`, `numeric_entries`, and `question_answers`. ASR indexes refer to the array position, starting at zero. WeMM clip indexes refer to the `clip` field in its output. Record the time origin in the index to avoid confusing clip-local evidence with source time.

Run `python3 scripts/validate_index.py <index-path>` and review the content as well. The checks require a continuous evidence timeline for a full report and reject broken question and numerical references. Use `--allow-gaps` for a request explicitly limited to selected scenes. Sample detailed questions from the start, middle and end. Check that each answer can be reconstructed from the identified evidence. Verify the index and the final report in the Drive folder before delivery.

## Answer questions later

Search the index by question, keyword, numerical value or time. Use the smallest relevant span and read the associated raw artifact if exact wording or a visual action matters. Report the answer with original timestamp links or Drive evidence. When a requested detail is missing or ambiguous, state what the present evidence supports and which detail needs checking. If the user asks to expand an existing report, preserve its original Drive file ID when the connector can update it in place.
