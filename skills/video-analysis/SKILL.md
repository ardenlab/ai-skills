---
name: video-analysis
description: Analyze the actual audio and visuals of a YouTube, Google Drive, or uploaded video on Colab GPUs. Use for timecoded content analysis, visual or spoken evidence checks, and detailed reports that support later questions. Use existing analysis artifacts to answer follow-ups.
---

# Video analysis

Give the user a content conclusion and a detailed, evidence-linked report that another agent can use to answer specific questions about the original video. Keep GPU inference on Colab. Use Google Drive for the job's intermediate results, final report, and machine-readable evidence index.

## Choose the entry point

- **New analysis.** Read [the Drive setup](references/drive.md), [the Colab workflow](references/colab.md), and [the report and evidence requirements](references/report.md). Use an existing user-specified file or URL. Take a general content-analysis goal when the user has supplied no narrower question.
- **Follow-up about a finished analysis.** Use a supplied report or folder link, or [look up the results folder](references/drive.md) and find the video's subfolder. Read its evidence index and return to the relevant timecodes or raw analysis. Use existing evidence before provisioning another runtime.

## Run the analysis

1. Verify Google Drive access before requesting Colab resources. In the connected user's My Drive, find or create `Video Interpretation Studio` as a direct child of the root, then find or create its direct child `TMP`. Use `TMP` for manual video uploads. Create or reuse the video's result subfolder directly under `Video Interpretation Studio` and save the intake before requesting a GPU. Follow [the Drive setup](references/drive.md) for exact lookup and permission handling.
2. Request a G4 Colab runtime first and verify the assigned GPU, memory, and disk. Use the tested open-weight WeMM-Video-35B-A3B BF16 checkpoint by default. Verify that the full checkpoint fits on the GPU. If needed, try another eligible high-memory Colab GPU with the same checkpoint, and report the hardware constraint if it cannot run safely. Each parallel session gets its own GPU memory.
3. Download the exact source inside Colab. If a YouTube download fails after addressing ordinary setup errors, record the download failure, release any idle runtime from this job, and give the user the verified `TMP` folder link. Ask for a public **individual file** URL after upload. Continue the same job and result folder when the file arrives.
4. Run a visual-only pass and, when audio exists, a combined audio-visual pass with WeMM. Transcribe original audio independently using Qwen3-ASR and its forced aligner. Use a second audio model or denser original frames for meaningful disagreements. Compare evidence on one source timeline and resolve claims about actions with actual frames. Add specialist sync models only when the user needs a physical timing or active-speaker determination.
5. Write a substantial report and the evidence index before completing the task. Give the user the substantive content conclusion and report link in the response. Verify that the report, index, and evidence files are in the correct Drive subfolder. Release the job's runtime when its files are secured.

## What the report must let someone answer

- Which part of the video supports a specific claim, action, screen label, or spoken example?
- What do each number, comparison, and year refer to in the video?
- What was actually visible, what did the narrator describe, and what was inferred by a model or the agent?
- Which exact details can be retrieved from the saved evidence, and which questions need another look at the media or original sources?

For the report structure, index schema, and validation command, use [the report and evidence requirements](references/report.md). For the open-weight checkpoints, runtime stages, and fallback details, use [the Colab workflow](references/colab.md).
