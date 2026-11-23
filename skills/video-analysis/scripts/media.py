"""Acquire and inspect source media, and extract original-timestamp frame evidence."""

import argparse
from hashlib import file_digest
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from time import monotonic
from urllib.parse import parse_qs, urlencode, urlsplit


YOUTUBE = {'youtu.be', 'youtube.com', 'www.youtube.com', 'm.youtube.com'}
DRIVE = {'drive.google.com', 'drive.usercontent.google.com'}
MEDIA_INFO = '01-media.json'


class DownloadError(RuntimeError):
    def __init__(self, provider, message):
        super().__init__(message)
        self.provider = provider


def save_json(path, payload):
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


def load_media(job):
    return json.loads((job / MEDIA_INFO).read_text(encoding='utf-8'))


def get_provider(source):
    url = urlsplit(source)
    if not url.scheme and not url.netloc:
        return 'file'
    if url.scheme != 'https' or url.username or url.password or url.port not in (None, 443):
        raise ValueError('Supply an HTTPS YouTube or Google Drive link, or an uploaded file path.')
    if url.hostname in YOUTUBE:
        return 'youtube'
    if url.hostname in DRIVE:
        return 'drive'
    raise ValueError('Supply a YouTube URL, a Google Drive file link, or an uploaded file path.')


def drive_file_id(source):
    url = urlsplit(source)
    match = re.fullmatch(r'/file/d/([A-Za-z0-9_-]+)(?:/(?:view|preview|edit))?/?', url.path)
    value = match[1] if match else ''
    if not value and url.path in ('/open', '/uc', '/download'):
        ids = parse_qs(url.query).get('id', [])
        value = ids[0] if len(ids) == 1 else ''
    if not re.fullmatch(r'[A-Za-z0-9_-]+', value):
        raise ValueError('Use the public link for a single Google Drive video file.')
    return value


def video_download(source, directory, height):
    if not shutil.which('ffmpeg'):
        raise RuntimeError('FFmpeg must be available before downloading video.')
    command = [sys.executable, '-m', 'yt_dlp', '--ignore-config', '--no-playlist',
               '--no-simulate', '--no-progress', '--socket-timeout', '20',
               '--retries', '1', '--fragment-retries', '1', '--merge-output-format', 'mp4',
               '--print', 'after_move:filepath', '-o', str(directory / 'source.%(ext)s')]
    if height:
        command += ['-f', f'bv*[height<={height}][ext=mp4]+ba[ext=m4a]/b[height<={height}]/b']
    node = shutil.which('node')
    if node:
        version = subprocess.check_output([node, '--version'], text=True, timeout=10).strip()
        if int(version.lstrip('v').split('.')[0]) >= 22:
            command += ['--js-runtimes', 'node']
    try:
        result = subprocess.run(command + ['--', source], capture_output=True, text=True, timeout=900)
    except subprocess.TimeoutExpired as error:
        raise DownloadError('youtube', 'YouTube download timed out on the Colab runtime.') from error
    if result.returncode:
        diagnostic = result.stderr.strip().splitlines()
        message = diagnostic[-1] if diagnostic else 'yt-dlp could not download this video.'
        if 'No module named yt_dlp' in message:
            raise RuntimeError('Install yt-dlp[default] in the Colab runtime.')
        raise DownloadError('youtube', message)
    paths = result.stdout.strip().splitlines()
    downloaded = Path(paths[-1]).resolve() if paths else None
    if not downloaded or downloaded.parent != directory or not downloaded.is_file():
        raise DownloadError('youtube', 'yt-dlp returned without a completed media file.')
    return downloaded


def drive_download(source, directory):
    parameters = {'id': drive_file_id(source)}
    keys = parse_qs(urlsplit(source).query).get('resourcekey')
    if keys:
        parameters['resourcekey'] = keys[0]
    download_url = 'https://drive.google.com/uc?' + urlencode(parameters)
    path = directory / 'source.media'
    try:
        result = subprocess.run([sys.executable, '-m', 'gdown', download_url, '-O', str(path)],
                                capture_output=True, text=True, timeout=900)
    except subprocess.TimeoutExpired as error:
        raise DownloadError('drive', 'Google Drive download timed out on the Colab runtime.') from error
    if result.returncode or not path.is_file():
        diagnostic = result.stderr.strip().splitlines()
        message = diagnostic[-1] if diagnostic else 'Google Drive did not return a file.'
        if 'No module named gdown' in message:
            raise RuntimeError('Install gdown in the Colab runtime.')
        raise DownloadError('drive', message)
    return path


def probe(path):
    result = subprocess.run(['ffprobe', '-v', 'error', '-of', 'json', '-show_format',
                             '-show_streams', str(path)], capture_output=True, text=True, timeout=90)
    if result.returncode:
        raise ValueError('FFprobe could not read this file as media.')
    raw = json.loads(result.stdout)
    fields = ('index', 'codec_type', 'codec_name', 'start_time', 'time_base',
              'width', 'height', 'avg_frame_rate', 'sample_rate', 'channels')
    streams = [{k: stream[k] for k in fields if k in stream} for stream in raw.get('streams', [])
               if not stream.get('disposition', {}).get('attached_pic')]
    if not any(stream['codec_type'] == 'video' for stream in streams):
        raise ValueError('The source has no playable video stream.')
    try:
        duration = float(raw['format']['duration'])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError('A finite source duration is required for the playback timeline.') from error
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError('The source duration must be positive and finite.')
    return {'duration_seconds': duration, 'format_start_time': raw['format'].get('start_time'),
            'size_bytes': path.stat().st_size, 'streams': streams,
            'has_audio': any(stream['codec_type'] == 'audio' for stream in streams)}


def fetch(job, source, max_height):
    if max_height < 0:
        raise ValueError('Set max-height to 0 for the best available format, or a positive height.')
    if (job / MEDIA_INFO).is_file():
        saved = load_media(job)
        if saved['source'] == source and Path(saved['path']).is_file():
            return saved
        raise ValueError('This job already has a source. Use its original file or a new job directory.')
    provider = get_provider(source)
    if provider == 'drive':
        drive_file_id(source)
    job.mkdir(parents=True, exist_ok=True)
    started = monotonic()
    with TemporaryDirectory(dir=job, prefix='download-') as scratch:
        directory = Path(scratch)
        if provider == 'youtube':
            downloaded = video_download(source, directory, max_height)
        elif provider == 'drive':
            downloaded = drive_download(source, directory)
        else:
            original = Path(source).resolve(strict=True)
            if not original.is_file():
                raise ValueError('Supply an uploaded video file.')
            downloaded = shutil.copyfile(original, directory / ('source' + original.suffix))
        try:
            info = probe(downloaded)
        except ValueError as error:
            if provider in ('youtube', 'drive'):
                raise DownloadError(provider, str(error)) from error
            raise
        with downloaded.open('rb') as stream:
            info['sha256'] = file_digest(stream, 'sha256').hexdigest()
        target = job / downloaded.name
        downloaded.replace(target)
    info.update(source=source, provider=provider, path=str(target), elapsed_seconds=round(monotonic() - started, 2))
    save_json(job / MEDIA_INFO, info)
    return info


def prepare_audio(job, info):
    stream = next(stream for stream in info['streams'] if stream['codec_type'] == 'audio')
    target = job / 'source-16k.wav'
    if target.is_file():
        return target
    pending = job / 'audio-pending.wav'
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-copyts', '-start_at_zero',
                    '-i', info['path'], '-map', f"0:{stream['index']}",
                    '-af', 'aresample=16000:async=1:first_pts=0', '-ac', '1',
                    '-c:a', 'pcm_s16le', str(pending)], check=True)
    pending.replace(target)
    return target


def extract_frames(job, start, end, interval):
    from PIL import Image, ImageDraw

    info = load_media(job)
    end = info['duration_seconds'] if end is None else end
    if not all(math.isfinite(num) for num in (start, end, interval)) or not 0 <= start < end <= info['duration_seconds'] or interval <= 0:
        raise ValueError('Use a positive frame interval and valid original-video start and end seconds.')
    target = job / f'evidence-{start:g}-{end:g}-{interval:g}'
    target.mkdir(exist_ok=True)
    video = next(stream for stream in info['streams'] if stream['codec_type'] == 'video')
    select = f'select=between(t\\,{start:g}\\,{end:g})*(isnan(prev_selected_t)+gte(t-prev_selected_t\\,{interval:g}))'
    with TemporaryDirectory(dir=target, prefix='frames-') as scratch:
        directory = Path(scratch)
        output = subprocess.run(['ffmpeg', '-nostdin', '-nostats', '-loglevel', 'info', '-copyts', '-start_at_zero',
                                 '-i', info['path'], '-map', f"0:{video['index']}", '-t', str(end),
                                 '-vf', f'{select},scale=352:-2,showinfo', '-fps_mode', 'vfr',
                                 '-q:v', '3', str(directory / 'frame-%05d.jpg')],
                                check=True, capture_output=True, text=True)
        pts = [float(value) for value in re.findall(r'\bn:\s*\d+\s+pts:\s*-?\d+\s+pts_time:([0-9.eE+-]+)', output.stderr)]
        frames = sorted(directory.glob('frame-*.jpg'))
        if not frames or len(frames) != len(pts):
            raise RuntimeError('Could not match saved frames to original presentation timestamps.')
        index = []
        for offset in range(0, len(frames), 20):
            page = f'page-{offset // 20 + 1:03}.jpg'
            sheet = Image.new('RGB', (1440, 1450), (22, 24, 28))
            draw = ImageDraw.Draw(sheet)
            for slot, (path, seconds) in enumerate(zip(frames[offset:offset+20], pts[offset:offset+20], strict=True)):
                column, row = slot % 4 + 1, slot // 4 + 1
                x, y = (column - 1) * 360 + 4, (row - 1) * 290 + 4
                with Image.open(path) as image:
                    image.thumbnail((352, 258))
                    sheet.paste(image, (x, y + 18))
                draw.text((x, y), f'{int(seconds) // 60:02d}:{seconds % 60:06.3f}', fill=(250, 250, 250))
                index.append({'seconds': seconds, 'page': page, 'row': row, 'column': column})
            sheet.save(target / page, quality=88)
    save_json(target / 'index.json', index)
    return {'directory': str(target), 'frames': len(index)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--job', type=Path, required=True)
    commands = parser.add_subparsers(dest='command', required=True)
    download = commands.add_parser('fetch')
    download.add_argument('source')
    download.add_argument('--max-height', type=int, metavar='PIXELS', default=1080)
    frames = commands.add_parser('frames')
    frames.add_argument('--start', type=float, default=0)
    frames.add_argument('--end', type=float)
    frames.add_argument('--interval', type=float, default=8)
    args = parser.parse_args()
    job = args.job.resolve()
    try:
        if args.command == 'fetch':
            data = fetch(job, args.source, args.max_height)
        else:
            data = extract_frames(job, args.start, args.end, args.interval)
        print(json.dumps(data, ensure_ascii=False))
    except DownloadError as error:
        failure = {'provider': error.provider, 'status': 'download_failed', 'diagnostic': str(error)}
        save_json(job / f'01-download-{error.provider}.json', failure)
        print(json.dumps(failure, ensure_ascii=False), file=sys.stderr)
        return 20 if error.provider == 'youtube' else 21
    except (RuntimeError, ValueError, OSError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
