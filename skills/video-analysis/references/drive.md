# Google Drive setup

The standard layout belongs to the Google account connected for the analysis. Resolve the folder IDs from that account on each new job.

```text
My Drive
└── Video Interpretation Studio
    ├── TMP
    └── <video title and stable video ID>
```

`TMP` receives source videos the user uploads after direct download fails. The video-specific folder holds the intake, intermediate evidence, report, and follow-up index.

## Find or create the two folders

1. Use an authorized Google Drive connector or authenticated Drive API for the intended account. Read the user's My Drive root by its `root` alias and confirm access to list its direct children. If the connection is known to expose only selected files, obtain access that can list the relevant parent before treating zero matches as absence. If authorization or the necessary access is missing, ask the user to connect or authorize Drive before allocating a Colab runtime. Colab authentication alone does not establish Drive access.
2. Look up the exact folder name `Video Interpretation Studio` under My Drive root. A Drive v3 query can use `'root' in parents and name = 'Video Interpretation Studio' and mimeType = 'application/vnd.google-apps.folder' and trashed = false`. Follow any next-page token. The match must be a live folder with the resolved root as its parent.
3. When setup is requested or a new video analysis needs it, reuse the single verified match or create the folder under `root` after a successful, complete lookup returns zero matches. With `create_folder`, pass `name` and `parent_folder`. Read back the folder metadata and record its verified ID and link. Confirm the parent after creation.
4. Repeat the same direct-child lookup for the exact folder name `TMP`, using the verified `Video Interpretation Studio` ID as the parent. Reuse it or create it there on setup or a new analysis. Verify its metadata and parent, then keep its link for the fallback instructions.

If multiple exact-name folders exist under the same parent, resolve the intended folder using a verified ID already supplied in the task, or present the matched links for selection. If lookup fails, is incomplete, or lacks access, fix the access or lookup first. If a create response is uncertain, recheck the parent before retrying. Refresh the lookup if the first result is inconclusive. This also lets a retry reuse the studio when the first attempt created it but did not finish setting up `TMP`.

## Create a video job folder

Use the same parent lookup, creation, and retry rules for the video job folder. Create a child named with the video title and stable video ID directly under `Video Interpretation Studio`. For an interrupted run, use the stable video ID and verified parent to find its existing folder, even if the video title has changed. Use a run suffix when the user needs distinct repeat results. Verify the parent and write the real intake record there before requesting a GPU. Use `canAddChildren` when the connector exposes it and treat an unsuccessful authorized folder or intake write as a Drive access blocker.

Save each completed stage to that video folder as it becomes available. The agent can collect Colab files with `colab download` and upload them through the authorized Drive connector. Verify the final report and evidence index in the expected video folder before returning links. Preserve the account's folder-sharing defaults. If a source upload is needed, request the accessible link to that individual video file.

For a follow-up on existing results, read the supplied artifact or locate `Video Interpretation Studio` using the same exact-parent lookup. Then find the existing video folder and its evidence index. Folder creation is part of setup and new analysis.
