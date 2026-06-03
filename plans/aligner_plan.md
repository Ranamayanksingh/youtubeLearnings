# Content Aligner — Plan

## Responsibility

Merge the transcript segments and visual frames by timestamp into a unified timeline.
The output is a single structured document where each entry says:
"At this point in the video, *this* was on screen and *this* is what the teacher was saying."

This is the key data structure that the synthesizer (Component 5) will consume.

---

## The Alignment Problem

Transcript segments and frames are on independent timelines:

```
Transcript:  [0s–4s: "Aaj hum..."] [4s–12s: "Dhoompaan ke baare mein..."] [12s–30s: "..."]
Frames:               [5s: slide A]                        [32s: slide B]
```

A frame at `t=5s` was visible from `5s` until the next frame at `t=32s`.
Any transcript segment that overlaps with `[5s, 32s]` was spoken while slide A was shown.

**Strategy: frame-as-anchor**
- Each frame defines a time window: `[frame.timestamp, next_frame.timestamp)`
- Collect all transcript segments whose `start_sec` falls within that window
- Last frame's window extends to end of video

---

## Inputs & Outputs

| | Detail |
|---|---|
| **Input** | `output/<video_id>/transcript.json` + `output/<video_id>/visual_content.json` + `output/<video_id>/metadata.json` |
| **Output** | `output/<video_id>/aligned_content.json` |

### aligned_content.json shape

```json
{
  "video_id": "abc123",
  "title": "Govind Parikh Page 1 ...",
  "segments": [
    {
      "segment_index": 1,
      "frame": {
        "file": "frames/0002_t00m05s.jpg",
        "timestamp_sec": 5,
        "ocr_text": "धूमपान - Definition ...",
        "vision_description": "",
        "content_type": "slide"
      },
      "transcript": [
        {"index": 3, "start_sec": 5.2, "end_sec": 12.4, "text": "Dhoompaan ke baare mein..."},
        {"index": 4, "start_sec": 12.4, "end_sec": 18.1, "text": "Yeh ek important topic hai..."}
      ],
      "window_start_sec": 5,
      "window_end_sec": 32
    },
    ...
  ]
}
```

---

## Edge Cases

| Scenario | Handling |
|---|---|
| Transcript segment spans two frame windows | Assign to the window where `start_sec` falls |
| No transcript in a frame window (silent section) | `transcript: []` — frame content still included |
| No frames at all | Raise error — cannot align without visual anchor |
| Transcript before first frame | Attach to first frame's window |
| Video with no transcript (silent/music) | Aligned segments will have empty transcript lists |

---

## Module Structure

```
src/
└── aligner/
    ├── __init__.py
    └── aligner.py      # single module — reads both inputs, produces aligned_content.json
```

---

## Integration into Pipeline

`pipeline.py` calls `aligner.align(video_id, out_dir)` as the final step after visual extraction.

Updated pipeline order:
```
download → audio_extract → transcribe → frame_extract → visual_extract → align → metadata update
```

---

## No New Dependencies

Pure Python — no new packages needed.
