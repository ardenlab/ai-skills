"""Check whether a video evidence index is complete and can be followed to its sources."""

import argparse
import json
import math
from pathlib import Path
import sys


def require(condition, message):
    if not condition:
        raise ValueError(message)


def text(value):
    return isinstance(value, str) and bool(value.strip())


def validate(index, allow_gaps):
    duration = float(index['video']['duration_seconds'])
    require(math.isfinite(duration) and duration > 0, 'Use the positive finite duration of the original video.')
    records = index['evidence']
    require(isinstance(records, list) and bool(records), 'Evidence intervals are required.')
    seen = set()
    previous_start, covered = -1, 0
    for row in records:
        label = row['id']
        require(text(label) and label not in seen, f'Duplicate or empty evidence ID: {label!r}.')
        seen.add(label)
        start, end = float(row['start_seconds']), float(row['end_seconds'])
        require(0 <= start < end <= duration + 0.02 and previous_start <= start, f'Invalid or unsorted time range for {label}.')
        if not allow_gaps:
            require(start <= covered + 0.02, f'Timeline gap before {label}.')
        previous_start, covered = start, max(covered, end)
        require(text(row['title']) and (text(row.get('spoken_summary')) or text(row.get('visual_evidence'))),
                f'Identify the substantive evidence for {label}.')
        require(text(row.get('youtube_at_start')) or text(row.get('playback_link')) or
                row.get('frames') or row.get('audio_segment_indexes') or row.get('wemm_clip_indexes'),
                f'Provide a source reference for {label}.')
    if not allow_gaps:
        require(covered >= duration - 0.02, 'The evidence timeline must reach the end of the video.')

    numbers = index['numeric_claims']
    require(isinstance(numbers, list), 'Use a list for numeric_claims.')
    for entry in numbers:
        require(entry['evidence_id'] in seen and text(entry.get('value')) and text(entry.get('scope')),
                'Give each numeric claim an existing evidence ID, value, and scope.')

    questions = index['question_answers']
    require(isinstance(questions, list) and bool(questions), 'Include questions the evidence can answer.')
    for question in questions:
        citations = question['evidence']
        require(text(question['question']) and text(question['answer']) and isinstance(citations, list) and bool(citations),
                'Include the question, an evidence-bound answer, and its citations.')
        require(all(reference['id'] in seen for reference in citations), 'A question cites an unknown evidence ID.')
    counts = {'evidence_intervals': len(records), 'numeric_entries': len(numbers), 'question_answers': len(questions)}
    if 'counts' in index:
        require(all(index['counts'].get(key) == count for key, count in counts.items()),
                'Index counts do not match its contents.')
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('index', type=Path)
    parser.add_argument('--allow-gaps', action='store_true', help='For a request explicitly limited to selected clips.')
    args = parser.parse_args()
    try:
        print(json.dumps(validate(json.loads(args.index.read_text(encoding='utf-8')), args.allow_gaps)))
    except (ValueError, KeyError, OSError, TypeError) as error:
        print(f'Invalid evidence index: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
