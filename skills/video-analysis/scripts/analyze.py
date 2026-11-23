"""Run pinned open-weight video and audio stages on a Colab GPU."""

import argparse
from collections import Counter
import json
import math
from pathlib import Path
import subprocess
from time import monotonic

from media import load_media, prepare_audio, save_json


WEMM = 'tencent/WeMM-Video-35BA3B'
WEMM_REVISION = '28f693611174f6228f665bddfb77ed0751362500'
WEMM_BYTES = 72359599040
ASR = 'Qwen/Qwen3-ASR-1.7B'
ASR_REVISION = '7278e1e70fe206f11671096ffdd38061171dd6e5'
ALIGNER = 'Qwen/Qwen3-ForcedAligner-0.6B'
ALIGNER_REVISION = 'c7cbfc2048c462b0d63a45797104fc9db3ad62b7'
WHISPER = 'openai/whisper-large-v3'
WHISPER_REVISION = '06f233fe06e710322aca913c1bc4249a0d71fce1'
GIB = 1024**3


def manifest(job, name, info, **data):
    payload = {'source_sha256': info['sha256'], **data}
    save_json(job / name, payload)
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def snapshot_weights(job, info):
    from huggingface_hub import snapshot_download

    started = monotonic()
    directory = Path(snapshot_download(WEMM, revision=WEMM_REVISION, local_dir=job / 'wemm-35ba3b', max_workers=8,
                     allow_patterns=['*.safetensors', '*.json', '*.py', '*.txt', '*.jinja', '*.model', '*.tiktoken', '*.yaml']))
    files = list(directory.glob('*.safetensors'))
    size = sum(file.stat().st_size for file in files)
    if len(files) != 17 or size != WEMM_BYTES:
        raise RuntimeError(f'Unexpected checkpoint files: {len(files)} shards, {size} bytes.')
    manifest(job, '03-weights.json', info, model=WEMM, revision=WEMM_REVISION, shards=len(files),
             weight_bytes=size, elapsed_seconds=round(monotonic() - started, 2))


def require_cuda():
    import torch

    if not torch.cuda.is_available():
        raise RuntimeError('Run GPU inference in the assigned Colab GPU runtime.')
    return torch


def transcribe(job, info):
    if not info['has_audio']:
        manifest(job, '02-asr-complete.json', info, status='no_audio')
        return

    import soundfile as sf
    from qwen_asr import Qwen3ASRModel

    torch = require_cuda()
    started = monotonic()
    audio, rate = sf.read(prepare_audio(job, info), dtype='float32')
    model = Qwen3ASRModel.from_pretrained(
        ASR, revision=ASR_REVISION, dtype=torch.bfloat16, device_map='cuda:0',
        max_inference_batch_size=3, max_new_tokens=512,
        forced_aligner=ALIGNER,
        forced_aligner_kwargs={'revision': ALIGNER_REVISION, 'dtype': torch.bfloat16, 'device_map': 'cuda:0'},
    )
    window = 40 * rate
    cores = [(left, min(left + window, len(audio))) for left in range(0, len(audio), window)]
    rows = []
    for i in range(0, len(cores), 3):
        batch = cores[i:i+3]
        audio_windows = [(max(0, left-rate), min(len(audio), right+rate)) for left, right in batch]
        responses = model.transcribe(audio=[(audio[left:right], rate) for left, right in audio_windows],
                                     return_time_stamps=True)
        for response, (start, end), (left, right) in zip(responses, batch, audio_windows, strict=True):
            aligned = []
            for token in response.time_stamps.items if response.time_stamps else []:
                first = left / rate + float(token.start_time)
                last = left / rate + float(token.end_time)
                if start / rate <= (first + last) / 2 < end / rate:
                    aligned.append({'text': token.text, 'start': round(first, 3), 'end': round(last, 3)})
            rows.append({'start': start / rate, 'end': end / rate, 'window_start': left / rate,
                         'window_end': right / rate, 'language': response.language,
                         'text_window': response.text, 'aligned': aligned})
            print('ASR_SEGMENT', start / rate, end / rate, len(aligned), flush=True)
    save_json(job / '02-asr-aligned.json', {'source_sha256': info['sha256'], 'asr': ASR, 'asr_revision': ASR_REVISION,
              'aligner': ALIGNER, 'aligner_revision': ALIGNER_REVISION, 'audio_only': True,
              'duration_seconds': len(audio) / rate, 'segments': rows})
    manifest(job, '02-asr-complete.json', info, status='complete', segments=len(rows),
             elapsed_seconds=round(monotonic() - started, 2))


def make_clip(job, info, index, start, end):
    directory = job / 'clips'
    directory.mkdir(exist_ok=True)
    clip = directory / f'{index:04d}.mp4'
    if clip.is_file():
        return clip
    pending = directory / f'{index:04d}.pending.mp4'
    video = next(stream for stream in info['streams'] if stream['codec_type'] == 'video')
    command = ['ffmpeg', '-nostdin', '-v', 'error', '-y', '-ss', str(start), '-i', info['path'], '-t', str(end-start),
               '-map', f"0:{video['index']}", '-vf', 'pad=ceil(iw/2)*2:ceil(ih/2)*2',
               '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '20',
               '-pix_fmt', 'yuv420p', '-fps_mode', 'vfr', '-threads', '4']
    if info['has_audio']:
        audio = next(stream for stream in info['streams'] if stream['codec_type'] == 'audio')
        command += ['-map', f"0:{audio['index']}", '-af', 'aresample=async=1:first_pts=0', '-c:a', 'aac', '-b:a', '128k']
    subprocess.run(command + [str(pending)], check=True)
    pending.replace(clip)
    return clip


def completed(path, info):
    if not path.exists():
        return {}
    rows = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
    ids = {row['clip'] for row in rows}
    if len(ids) != len(rows) or any(row['source_sha256'] != info['sha256'] for row in rows):
        raise ValueError(f'{path.name} contains duplicate clips or belongs to a different source.')
    return {row['clip']: row.get('status', 'analyzed') for row in rows}


def clip_plan(duration):
    starts = list(range(0, math.ceil(duration), 48))
    if len(starts) > 1 and duration - starts[-1] < 1:
        starts.pop()
    return list(zip(starts, starts[1:] + [duration], strict=True))


def clip_streams(clip):
    probe = subprocess.run(['ffprobe', '-v', 'error', '-of', 'json', '-show_entries',
                            'stream=codec_type,nb_frames', str(clip)], check=True, capture_output=True, text=True)
    return {stream['codec_type']: stream.get('nb_frames')
            for stream in json.loads(probe.stdout).get('streams', []) if stream.get('nb_frames') != '0'}


def missing_media(streams, mode):
    if 'video' not in streams:
        return 'no_video_in_clip'
    if streams['video'] == '1':
        return 'single_frame_use_original_frame'
    if mode == 'av' and 'audio' not in streams:
        return 'no_audio_in_clip'
    return None


def analyze_video(job, info, language):
    from transformers import AutoModelForImageTextToText, AutoProcessor

    torch = require_cuda()
    weights = json.loads((job / '03-weights.json').read_text(encoding='utf-8'))
    if weights['revision'] != WEMM_REVISION or weights['weight_bytes'] != WEMM_BYTES:
        raise RuntimeError('Stage the verified full BF16 checkpoint first.')
    free, _ = torch.cuda.mem_get_info()
    if free < WEMM_BYTES:
        raise RuntimeError(f'Full BF16 weights cannot fit in {free / GIB:.1f} GiB of currently free GPU memory.')
    started = monotonic()
    directory = str(job / 'wemm-35ba3b')
    processor = AutoProcessor.from_pretrained(directory, trust_remote_code=True, local_files_only=True)
    model = AutoModelForImageTextToText.from_pretrained(directory, trust_remote_code=True, local_files_only=True,
        dtype=torch.bfloat16, device_map={'': 'cuda:0'}, attn_implementation='sdpa').eval()
    devices = Counter()
    for parameter in model.parameters():
        devices[f'{parameter.device}|{parameter.dtype}'] += parameter.numel()
    if set(devices) != {'cuda:0|torch.bfloat16'}:
        raise RuntimeError(f'Expected all original model parameters in BF16 on one GPU, found {devices}.')
    manifest(job, '03-model-device.json', info, model=WEMM, revision=WEMM_REVISION, parameter_device_dtype=dict(devices),
             gpu=torch.cuda.get_device_name(0), weight_bytes=WEMM_BYTES,
             weight_loaded_gpu_gib=round(torch.cuda.memory_allocated() / GIB, 2),
             load_seconds=round(monotonic() - started, 2))

    settings = {'fps': 1.5, 'max_frames': 72, 'min_frames': 4, 'total_pixels': 6291456}
    token_limit = 224
    prompts = {'visual': 'Use the frames alone. Give one timecoded visible fact from each half. Include relevant text, '
                         'objects, screen changes, and any visible action and outcome.',
               'av': 'Use the soundtrack and frames. Give one timecoded spoken point and its visible evidence '
                     'from each half. In a final line identify any demonstrated action with visible outcome.'}
    if not info['has_audio']:
        del prompts['av']
    outputs = {mode: job / f'03-{mode}.jsonl' for mode in prompts}
    finished = {mode: completed(path, info) for mode, path in outputs.items()}
    duration = info['duration_seconds']
    ranges = clip_plan(duration)
    expected = set(range(len(ranges)))
    if any(not set(rows) <= expected for rows in finished.values()):
        raise RuntimeError('Saved clip indexes do not match the original timeline.')
    started = monotonic()
    for index, (start, end) in enumerate(ranges):
        if all(index in rows for rows in finished.values()):
            continue
        clip = make_clip(job, info, index, start, end)
        streams = clip_streams(clip)
        for mode, prompt in prompts.items():
            if index in finished[mode]:
                continue
            row = {'source_sha256': info['sha256'], 'clip': index, 'mode': mode, 'absolute_start': start,
                   'absolute_end': end}
            reason = missing_media(streams, mode)
            if reason:
                row.update(status=reason, text='')
            else:
                media = {'type': 'video' if mode == 'visual' else 'video_audio', 'video': str(clip), **settings}
                text = (f'Answer in {language}, in three short lines. {prompt} This is a {end-start:.1f}-second clip. '
                        'Use time from the clip start. Label captions and illustrations as such. Cite only observable details.')
                message = [{'role': 'user', 'content': [media, {'type': 'text', 'text': text}]}]
                then = monotonic()
                inputs = processor.apply_chat_template(message, tokenize=True, return_dict=True, return_tensors='pt',
                                                       add_generation_prompt=True, enable_thinking=False).to('cuda:0')
                preprocess_seconds = round(monotonic() - then, 2)
                then = monotonic()
                torch.cuda.reset_peak_memory_stats()
                with torch.inference_mode():
                    generated = model.generate(**inputs, max_new_tokens=token_limit, do_sample=False)
                answer = generated[0, inputs.input_ids.shape[1]:]
                response = processor.tokenizer.decode(answer, skip_special_tokens=True).strip()
                if not response:
                    raise RuntimeError(f'Empty output for {mode} clip {index}.')
                row.update(status='analyzed', text=response, input_tokens=inputs.input_ids.shape[1],
                           output_tokens=len(answer), output_token_limit=token_limit, sampling=settings,
                           preprocess_seconds=preprocess_seconds, generation_seconds=round(monotonic()-then, 2),
                           peak_gpu_gib=round(torch.cuda.max_memory_allocated() / GIB, 2))
                del inputs, generated, answer
            with outputs[mode].open('a', encoding='utf-8') as output:
                output.write(json.dumps(row, ensure_ascii=False) + '\n')
            finished[mode][index] = row['status']
            print('WEMM_CLIP', index, mode, start, end, row['status'], row.get('output_tokens'), flush=True)
    manifest(job, '03-video-complete.json', info, coverage={name: sorted(rows) for name, rows in finished.items()},
             skipped={name: {index: status for index, status in rows.items() if status != 'analyzed'}
                      for name, rows in finished.items()},
             duration_seconds=duration, elapsed_seconds=round(monotonic()-started, 2))


def spotcheck(job, info, windows, language):
    if not info['has_audio']:
        raise ValueError('This source has no audio track for a spot check.')
    from huggingface_hub import snapshot_download
    import soundfile as sf
    from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor

    torch = require_cuda()
    audio, rate = sf.read(prepare_audio(job, info), dtype='float32')
    if any(not 0 <= start < end <= len(audio) / rate or end-start > 30 for start, end in windows):
        raise ValueError('Use original-audio windows of at most 30 seconds within the source.')
    directory = snapshot_download(WHISPER, revision=WHISPER_REVISION, local_dir=job / 'whisper-large-v3',
                    allow_patterns=['*.json', '*.txt', '*.tiktoken', 'model.safetensors'],
                    ignore_patterns=['*fp32*', 'pytorch_model.bin*'])
    processor = AutoProcessor.from_pretrained(directory, local_files_only=True)
    model = AutoModelForSpeechSeq2Seq.from_pretrained(directory, dtype=torch.float16,
                    device_map={'': 'cuda:0'}, local_files_only=True).eval()
    rows = []
    for start, end in windows:
        samples = audio[round(start*rate):round(end*rate)]
        inputs = processor(samples, sampling_rate=rate, return_tensors='pt', return_attention_mask=True).to('cuda:0')
        with torch.inference_mode():
            ids = model.generate(inputs.input_features.to(torch.float16), attention_mask=inputs.attention_mask,
                                 language=language, task='transcribe', max_new_tokens=180, do_sample=False)
        rows.append({'start': start, 'end': end, 'text': processor.batch_decode(ids, skip_special_tokens=True)[0].strip()})
    manifest(job, '05-whisper-spotcheck.json', info, model=WHISPER, revision=WHISPER_REVISION, audio_only=True, segments=rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--job', type=Path, required=True)
    commands = parser.add_subparsers(dest='stage', required=True)
    commands.add_parser('weights')
    commands.add_parser('asr')
    video = commands.add_parser('video')
    video.add_argument('--language', default='the spoken language of the clip')
    check = commands.add_parser('spotcheck')
    check.add_argument('--window', action='append', required=True, metavar='START:END')
    check.add_argument('--language', help='Whisper language code when known, such as zh or en')
    args = parser.parse_args()
    job = args.job.resolve()
    info = load_media(job)
    if args.stage == 'weights':
        snapshot_weights(job, info)
    elif args.stage == 'asr':
        transcribe(job, info)
    elif args.stage == 'video':
        analyze_video(job, info, args.language)
    else:
        windows = [tuple(map(float, value.split(':'))) for value in args.window]
        if any(len(pair) != 2 for pair in windows):
            parser.error('each --window uses START:END in original-video seconds')
        spotcheck(job, info, windows, args.language)


if __name__ == '__main__':
    main()
