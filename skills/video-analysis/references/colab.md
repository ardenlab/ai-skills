# Colab workflow

## Drive preflight

Complete [the Google Drive setup](drive.md) before requesting a runtime. Keep the verified video folder ID for stage outputs and the verified `TMP` link for source uploads.

## Provision and configure

Use the installed Colab Operator skill when available, or inspect `colab --help`. Keep one isolated local session-state file for the job. Request `colab --config <state-file> new -s <session> --gpu G4` first. After allocation, use `nvidia-smi --query-gpu=name,memory.total,memory.free,driver_version --format=csv,noheader` and check actual filesystem space. The full checkpoint alone occupies 67.39 GiB. Media, Python environments and model staging need additional disk, and frame encoding and generation need additional GPU memory.

If G4 is unavailable, try an eligible H100 or A100 with sufficient actual memory and verify the same full BF16 checkpoint on a representative clip before the whole run. Read the assigned A100 capacity explicitly. End the GPU attempt with a concrete blocker if it cannot fit. A smaller or quantized model requires a user-approved change to the analysis plan. Premium hardware is subject to account availability. [Colab CLI accelerator options](https://github.com/googlecolab/google-colab-cli/blob/main/docs/01_session_management.md) · [Colab resource limits](https://research.google.com/colaboratory/faq.html#resource-limits)

Create a workspace such as `/content/video-analysis/<video-id>` and upload `media.py` and `analyze.py` to a common helper directory on that VM. Use a separate local working directory for downloads and local report authoring. Verify FFmpeg and FFprobe are installed. Use the same source and job directory for dependent stages.

The successful G4 trial used the runtime's installed CUDA PyTorch, TorchCodec and FFmpeg. The WeMM process used an isolated `uv venv --system-site-packages` with `transformers==5.2.0` and `tokenizers==0.22.2`. Install these exact two packages with `uv pip install --python <wemm-venv>/bin/python --no-deps transformers==5.2.0 tokenizers==0.22.2` after checking the runtime's inherited dependencies. If the current image differs, test PyTorch CUDA, TorchCodec and the processor in that environment before a long run. The independent ASR process used a different environment with `qwen-asr==0.0.6`; its Transformers version differs. Whisper used the runtime's base Transformers. Always check CUDA in the interpreter that will actually perform inference. [WeMM official checkpoint](https://huggingface.co/tencent/WeMM-Video-35BA3B) · [Qwen3-ASR](https://github.com/QwenLM/Qwen3-ASR) · [Whisper large-v3](https://huggingface.co/openai/whisper-large-v3)

## Run and monitor individual stages

The following are commands on the Colab VM. `job` is the absolute job directory, `helpers` contains the uploaded scripts, and `source` is the exact user URL or a file already uploaded to the VM.

```bash
python3 "$helpers/media.py" --job "$job" fetch "$source"
python3 "$helpers/analyze.py" --job "$job" weights
"$asr_python" "$helpers/analyze.py" --job "$job" asr
"$wemm_python" "$helpers/analyze.py" --job "$job" video --language 'Simplified Chinese'
python3 "$helpers/media.py" --job "$job" frames --interval 8
```

Use the language appropriate to the user and video. Run the download first to avoid fetching weights for an inaccessible source. Install `yt-dlp[default]` for YouTube, with a supported JavaScript runtime such as Node 22+ or Deno as applicable. Use `gdown` for a public Drive file. FFprobe validates actual media before a download is counted successful. The helper defaults to a 1080-pixel height preference. Use `--max-height 0` if a higher-resolution original is needed for legibility. [yt-dlp JavaScript setup](https://github.com/yt-dlp/yt-dlp/wiki/EJS) · [gdown](https://github.com/wkentaro/gdown)

For long stages, run `scripts/launch.py` via `colab exec -f` to detach execution from the notebook connection. It accepts an environment value named `VIDEO_STAGE_SPEC` with `job`, `name`, and an `argv` array. Pass paths and URLs as individual arguments. The following example runs the fetch stage on the configured session.

```bash
spec=$(python3 -c 'import json,sys; print(json.dumps(dict(job=sys.argv[1],name=sys.argv[2],argv=sys.argv[3:])))' \
  "$job" fetch python3 "$helpers/media.py" --job "$job" fetch "$source")
colab --config "$state_file" exec -s "$session" --env "VIDEO_STAGE_SPEC=$spec" -f "$skill_dir/scripts/launch.py"
```

Poll `<stage>.status.json` and `<stage>.log` inside the job directory, using Colab file download if the kernel websocket briefly disconnects. `complete` with exit code zero and the expected stage artifacts indicate completion. A socket disconnect alone does not establish that a detached worker stopped. Confirm its state before relaunching. Logs are appended and status is updated atomically. Run the WeMM weight download and audio work concurrently when that helps. On one G4, release the ASR process before loading the large video model and perform optional Whisper checks after WeMM frees the GPU. Use distinct sessions for parallel inference when the current quota allows it.

When the fetch status shows exit code `20`, save the failure detail in the video's Drive folder and tell the user the YouTube download failed in Colab. Give them the verified `Video Interpretation Studio/TMP` link and ask them to upload the video there and provide the individual file's public link. Resume using that file link under the same video result directory. Exit `21` indicates the Drive file download failed. Check the file ID, public access and the recorded diagnostic. Fix local dependency errors before attributing a problem to the media source. Release the job's runtime while waiting for a user upload.

## Verify coverage and audio-video evidence

The weights stage verifies the pinned 17 weight shards. The video stage checks the on-GPU BF16 parameter mapping and produces `03-visual.jsonl`, `03-av.jsonl` for sources with audio, `03-model-device.json`, and `03-video-complete.json`. Default processing uses roughly 48-second windows, 1.5 fps, a 72-frame cap, and concise output capped at 224 tokens. The completion record lists the processed intervals and any `skipped` clip-mode pairs. An audio-only or silent tail can lack evidence for one pass. Use aligned audio for an audio-only tail and original frames for a still-frame interval. Read the first result to check that the model described both halves and kept text on screen distinct from observable action. Revisit incomplete or ambiguous portions using the original video.

The ASR stage produces `02-asr-aligned.json` with absolute, aligned word or character times. It uses 40-second cores with one second of context on each side. For a source without audio, the ASR stage records `no_audio` and the main pass is visual only. The audio extraction normalizes the original playback origin and pads a delayed stream. Check first PTS or stream offsets when a difference is consequential, and use original FFprobe times and source frames for precise claims. A model's clip-local textual timestamps are approximate and must be offset by `absolute_start`. [FFprobe documentation](https://ffmpeg.org/ffprobe.html)

Use focused checks when the same number, phrase, interface element, or action needs stronger evidence. The frames helper accepts `--start`, `--end`, and `--interval` in original-video seconds. For hard-to-read interface text, extract a full-resolution frame at the relevant source PTS in Colab as well. To replay a disputed speech window, run `python3 "$helpers/analyze.py" --job "$job" spotcheck --window 55:68 --language zh` in a CUDA-enabled environment. Use multiple `--window START:END` arguments for selected short passages. Compare that independent result with the full transcript and visible labels.

For measured audiovisual offset, use SyncNet on a visible speaking face or Synchformer on short clips with an observable sound-event cue. TalkNet can help identify which visible face is speaking. Use the general timeline and original media when the question is about what the narration refers to. [SyncNet](https://www.robots.ox.ac.uk/~vgg/software/lipsync/) · [Synchformer](https://github.com/v-iashin/Synchformer) · [TalkNet](https://github.com/TaoRuijie/TalkNet-ASD)

## Close the job

Check visual coverage and, for audio sources, combined and ASR coverage through the end of the original source. Save available intermediate artifacts to Drive as they complete. Once all needed evidence is retrieved, stop the session created for the job with `colab --config <state-file> stop -s <session>`. Verify the final Drive report and index separately. Report cold download and model setup times separately from warm inference when reporting performance.

The successful validation case ran one 9-minute-29-second video on a G4. The full model remained on one GPU. The two 12-segment passes took 206.22 seconds after setup, with 69.20 GiB peak PyTorch allocation. Use this as a measured example for these settings. New videos and Colab assignments require their own measurements.
