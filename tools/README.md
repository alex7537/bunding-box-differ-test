# Additional tools

## Review PF/SAM bbox conflicts in the GUI

`build_sam2_bbox_review_queue.py` converts the per-episode `review_manifest.json`
files into one prioritized clip queue. Overrides can mark a confirmed bad anchor as
`reanchor_required`, or a confirmed good SAM result as `sam_candidate_preferred`.

```commandline
python tools/build_sam2_bbox_review_queue.py \
  downloads/parcel_sorting_annotation_latest_20260807_rerun_20260810/review_v4 \
  downloads/parcel_sorting_annotation_latest_20260807_rerun_20260810/bbox_adjustment_queue.json \
  --overrides downloads/parcel_sorting_annotation_latest_20260807_rerun_20260810/bbox_review_overrides.json
```

`sam2_bbox_review_gui.py` shows the PF box in green, the SAM box in blue, and the
operator-selected anchor box in orange. The final choice is clip-level: select the
whole PF or SAM track once, and the GUI writes `final_bbox_tracks/<episode>/<clip>.json`.
Current-frame PF/SAM selection and drawing are only for correcting an anchor.
Rerunning SAM writes a separate `*_sam2.1_tiny_human_raw.json`; it does not overwrite
the original PF-anchor propagation.

`export_final_bbox_tracks.py` completes the batch after GUI review. It preserves
human PF/SAM selections and emits PF for every unselected clip. A flagged but
unreviewed clip remains `review_pending=true` even though its exported fallback is PF.
It also writes `final_bbox_manifest.json` and `.csv` for pipeline consumption.

The SAM service currently listens on the development machine loopback interface.
The macOS launcher creates an SSH tunnel, opens the current 17-clip queue, and
closes the tunnel when the GUI exits:

```commandline
./run-sam2-review-gui.command
```

For another batch, invoke `sam2_bbox_review_gui.py` directly with its dataset,
result, review, and queue roots. When the service and GUI see different filesystem
paths, pass `--service-dataset-root` so the API receives the remote frames path.

## Propagate a human parcel box and side label

`run_remote_tracker_sequence.py` turns one trusted human annotation into a
reviewable per-frame draft. The human anchor may be any frame. The tool launches
separate backward and forward tracker sessions, preserves the human label, and
writes YOLO files plus `annotation_manifest.json`. It computes every frame before
publishing output, so a remote tracking failure does not leave a partial result.

Use the canonical classes in `config/parcel_side_classes.txt`:

```text
parcel_front
parcel_back
```

Put exactly one YOLO annotation beside its anchor image, or select an annotated
frame explicitly with `--anchor-frame` (1-based):

```commandline
python tools/run_remote_tracker_sequence.py \
  /path/to/frames \
  /path/to/draft-labels \
  --classes config/parcel_side_classes.txt \
  --anchor-frame 18 \
  --base-url http://tracker-service:5000
```

Tracker output is a draft, not a human fact. Review and correct the propagated
boxes before downstream import. The manifest marks the anchor as `human` and all
propagated frames as `tracker`.

## Review a sustained PF/SAM conflict and re-anchor SAM2

`generate_sam2_review_pack.py` marks a clip as `clip_level_conflict` when either
the configured share of eligible, non-anchor frames has PF/SAM IoU below the
threshold, or a continuous low-IoU run reaches the configured minimum length.
The default trigger is `low_iou_ratio >= 0.6` with at least five evaluated
frames, **or** a continuous run of at least eight frames.

This status is deliberately neutral: disagreement does not prove that PF or SAM
is wrong. The generated five-image card shows the anchor, lowest-IoU frame,
frames before and after the anchor, and the start of the longest disagreement
run. The operator should first confirm the anchor and attribution instead of
reviewing every flagged frame independently.

If the anchor is wrong, draw one tight parcel bbox on a clear frame and rerun
SAM2 with pixel `xyxy` coordinates:

After drawing a tight parcel bbox, rerun the clip with pixel `xyxy` coordinates:

```commandline
python tools/rerun_sam2_with_human_anchor.py \
  /share_data/zhangyurui/dataset/episode_id \
  /share_data/zhangyurui/sam_results/episode_id \
  clip_002 \
  --anchor-frame 31 \
  --bbox X1 Y1 X2 Y2 \
  --anchor-review-result anchor_corrected \
  --attribution sam_identity_switch \
  --error-content robot_arm \
  --multi-parcel true \
  --reviewed-by zhangyurui \
  --sam2-url http://127.0.0.1:5001
```

The original PF-anchor result is preserved. The new result is written as
`clip_002_sam2.1_tiny_human_raw.json` with `anchor_source=human`. Run
`generate_sam2_review_pack.py` again; it automatically prefers this human-anchor
result and recalculates the review decisions. Use `--force` only when replacing
an earlier human-anchor retry.

## Convert the label files to CSV

### Introduction
To train the images on [Google Cloud AutoML](https://cloud.google.com/automl), we should prepare the specific csv files follow [this format](https://cloud.google.com/vision/automl/object-detection/docs/csv-format).

`label_to_csv.py` can convert the `txt` or `xml` label files to csv file. The labels files should strictly follow to below structure.

### Structures
* Images
    To train the object detection tasks, all the images should upload to the cloud storage and access it by its name. All the images should stay in the **same buckets** in cloud storage. Also, different classes should have their own folder as below.
    ```
    <bucket_name> (on the cloud storage)
    | -- class1
    |    | -- class1_01.jpg
    |    | -- class1_02.jpg
    |    | ...
    | -- class2
    |    | -- class2_01.jpg
    |    | -- class2_02.jpg
    |    | ...
    | ...
    ```
    Note, URI of the `class1_01.jpg` is `gs://<bucket_name>/class1/class1_01.jpg`
* Labels
    There are four types of training data - `TRAINING`, `VALIDATION`, `TEST` and `UNASSIGNED`. To assign different categories, we should create four directories.
    Inside each folder, users should create the class folders with the same name in cloud storage (see below structure).
    ```
    labels (on PC)
    | -- TRAINING
    |    | -- class1
    |    |    | -- class1_01.txt (or .xml)
    |    |    | ...
    |    | -- class2
    |    |    | -- class2_01.txt (or .xml)
    |    |    | ...
    |    | ...
    | -- VALIDATION
    |    | -- class1
    |    |    | -- class1_02.txt (or .xml)
    |    |    | ...
    |    | -- class2
    |    |    | -- class2_02.txt (or .xml)
    |    |    | ...
    |    | ...
    | -- TEST
    |    | (same as TRAINING and VALIDATION)
    | -- UNASSIGNED
    |    | (same as TRAINING and VALIDATION)
    ```

### Usage

To see the argument of `label_to_csv.py`,
```commandline
python label_to_csv.py -h
```

```commandline
usage: label_to_csv.py [-h] -p PREFIX -l LOCATION -m MODE [-o OUTPUT]
                       [-c CLASSES]

optional arguments:
  -h, --help            show this help message and exit
  -p PREFIX, --prefix PREFIX
                        Bucket of the cloud storage path
  -l LOCATION, --location LOCATION
                        Parent directory of the label files
  -m MODE, --mode MODE  'xml' for converting from xml and 'txt' for converting
                        from txt
  -o OUTPUT, --output OUTPUT
                        Output name of csv file
  -c CLASSES, --classes CLASSES
                        Label classes path
```

For example, if mine bucket name is **test**, the location of the label directory is **/User/test/labels**, the mode I choose from is **txt**, the output name and the class path is same as default.
```commandline
python label_to_csv.py \
-p test\
-l /User/test/labels \
-m txt
```

The output file is `res.csv` by default. Afterwards, upload the csv file to the cloud storage and you can start training!
