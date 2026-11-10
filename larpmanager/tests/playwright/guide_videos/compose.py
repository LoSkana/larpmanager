# LarpManager - https://larpmanager.com
# Copyright (C) 2025 Scanagatta Mauro
#
# This file is part of LarpManager and is dual-licensed:
#
# 1. Under the terms of the GNU Affero General Public License (AGPL) version 3,
#    as published by the Free Software Foundation. You may use, modify, and
#    distribute this file under those terms.
#
# 2. Under a commercial license, allowing use in closed-source or proprietary
#    environments without the obligations of the AGPL.
#
# If you have obtained this file under the AGPL, and you make it available over
# a network, you must also make the complete source code available under the same license.
#
# For more information or to purchase a commercial license, contact:
# commercial@larpmanager.com
#
# SPDX-License-Identifier: AGPL-3.0-or-later OR Proprietary

"""Turn a raw guide capture and its timeline into the final video, captions and description."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

WIDTH = 1920
HEIGHT = 1080
FRAME_RATE = 30
INTRO_SECONDS = 3.5
OUTRO_SECONDS = 4.0
RECAP_BASE_SECONDS = 2.0
RECAP_STEP_SECONDS = 0.5
RECAP_LINE_DELAY = 0.3
RECAP_LINE_HEIGHT = 92
RECAP_LEFT = 0.28
MIN_CHAPTER_SECONDS = 10
CARD_COLOR = "0x12303c"
LOGO_WIDTH = 280
LOGO_TOP = 0.13
TITLE_TOP = 0.54
SUBTITLE_TOP = 0.72
INTRO_SUBTITLE_TOP = 0.78
FONT = "Lato"
MUSIC_FADE_IN = 1.0
MUSIC_FADE_OUT = 3.0
MUSIC_LOUDNESS = -18

MUSIC_CREDIT = (
    "Inspired Kevin MacLeod (incompetech.com)\n"
    "Licensed under Creative Commons: By Attribution 4.0\n"
    "https://creativecommons.org/licenses/by/4.0/\n"
    "Trimmed and faded for this video."
)

ASS_HEADER = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {WIDTH}
PlayResY: {HEIGHT}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, \
StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: caption,{FONT},40,&H00FFFFFF,&H00FFFFFF,&H28302012,&H00000000,-1,0,0,0,100,100,0,0,3,18,0,2,160,160,56,1
Style: step,{FONT},54,&H00FFFFFF,&H00FFFFFF,&H10806000,&H00000000,-1,0,0,0,100,100,0,0,3,24,0,2,160,160,56,1
Style: role_organizer,{FONT},30,&H00FFFFFF,&H00FFFFFF,&H103C3012,&H00000000,-1,0,0,0,100,100,0,0,3,12,0,3,40,40,44,1
Style: role_player,{FONT},30,&H00FFFFFF,&H00FFFFFF,&H10005AA8,&H00000000,-1,0,0,0,100,100,0,0,3,12,0,3,40,40,44,1
Style: role_collaborator,{FONT},30,&H00FFFFFF,&H00FFFFFF,&H103A6B2F,&H00000000,-1,0,0,0,100,100,0,0,3,12,0,3,40,40,44,1
Style: title,{FONT},112,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,0,0,5,120,120,0,1
Style: subtitle,{FONT},56,&H00D8E8EE,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,5,120,120,0,1
Style: intro_title,{FONT},146,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,0,0,5,120,120,0,1
Style: intro_subtitle,{FONT},73,&H00D8E8EE,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,5,120,120,0,1
Style: recap_title,{FONT},64,&H00D8E8EE,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,0,0,4,120,120,0,1
Style: recap,{FONT},54,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,4,120,120,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def run_ffmpeg(arguments: list[str], cwd: Path) -> None:
    """Run ffmpeg quietly, failing on any error."""
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *arguments], cwd=cwd, check=True)  # noqa: S603, S607


def media_duration(path: Path) -> float:
    """Return the duration of a media file."""
    result = subprocess.run(  # noqa: S603
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],  # noqa: S607
        check=True,
        capture_output=True,
        text=True,
    )
    return float(result.stdout)


def align_to_recording(timeline: dict, raw_duration: float) -> dict:
    """Shift the timeline onto the recording, which starts before the capture reports its first bytes."""
    offset = raw_duration - timeline["duration"]
    captions = [{**c, "start": c["start"] + offset, "end": c["end"] + offset} for c in timeline["captions"]]
    cuts = [[0.0, offset], *([start + offset, end + offset] for start, end in timeline["cuts"])]
    return {**timeline, "duration": raw_duration, "captions": captions, "cuts": cuts}


def step_title(text: str) -> str:
    """Return a step heading without its number, in sentence case."""
    title = re.sub(r"^Step \d+:\s*", "", text)
    return title[:1].upper() + title[1:]


def lead_seconds(timeline: dict) -> float:
    """Return the length of the title and recap cards before the capture."""
    steps = [caption for caption in timeline["captions"] if caption["kind"] == "step"]
    return INTRO_SECONDS + RECAP_BASE_SECONDS + RECAP_STEP_SECONDS * len(steps)


def to_final_time(raw_time: float, cuts: list[list[float]], lead: float) -> float:
    """Map a raw recording time to the final video, after removing cuts and adding the leading cards."""
    removed = 0.0
    for cut_start, cut_end in cuts:
        if raw_time >= cut_end:
            removed += cut_end - cut_start
        elif raw_time > cut_start:
            removed += raw_time - cut_start
    return raw_time - removed + lead


def body_duration(timeline: dict) -> float:
    """Return the capture length left after removing cuts."""
    return timeline["duration"] - sum(cut_end - cut_start for cut_start, cut_end in timeline["cuts"])


def ass_time(seconds: float) -> str:
    """Format seconds for an ASS event."""
    centiseconds = round(seconds * 100)
    minutes, remainder = divmod(centiseconds, 6000)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02d}:{remainder / 100:05.2f}"


def srt_time(seconds: float) -> str:
    """Format seconds for an SRT entry."""
    milliseconds = round(seconds * 1000)
    minutes, remainder = divmod(milliseconds, 60000)
    hours, minutes = divmod(minutes, 60)
    whole_seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d},{milliseconds:03d}"


def final_captions(timeline: dict) -> list[dict]:
    """Return the captions with final timings, skipping those fully inside a cut."""
    captions = []
    lead = lead_seconds(timeline)
    for caption in timeline["captions"]:
        start = to_final_time(caption["start"], timeline["cuts"], lead)
        end = to_final_time(caption["end"], timeline["cuts"], lead)
        if end > start:
            captions.append({"start": start, "end": end, "text": caption["text"], "kind": caption["kind"]})
    return captions


def recap_events(captions: list[dict], lead: float) -> list[str]:
    """Return the ASS events of the card listing the steps, shown one after the other."""
    steps = [step_title(caption["text"]) for caption in captions if caption["kind"] == "step"]
    left = WIDTH * RECAP_LEFT
    top = (HEIGHT - RECAP_LINE_HEIGHT * (len(steps) + 1)) / 2
    start = INTRO_SECONDS + 0.1
    events = [
        f"Dialogue: 0,{ass_time(start)},{ass_time(lead)},recap_title,,0,0,0,,"
        f"{{\\fad(250,250)\\pos({left},{top})}}In this guide"
    ]
    for index, title in enumerate(steps, start=1):
        line_start = start + RECAP_LINE_DELAY * index
        line_top = top + RECAP_LINE_HEIGHT * index
        events.append(
            f"Dialogue: 0,{ass_time(line_start)},{ass_time(lead)},recap,,0,0,0,,"
            f"{{\\fad(250,250)\\pos({left},{line_top})}}{index}.  {title}"
        )
    return events


def chapter_lines(captions: list[dict]) -> list[str]:
    """Return one video chapter per step: the first starts at zero, too short ones are merged into the previous."""
    lines = []
    chapter_start = 0.0
    for caption in captions:
        if caption["kind"] != "step":
            continue
        start = caption["start"] if lines else 0.0
        if lines and start - chapter_start < MIN_CHAPTER_SECONDS:
            continue
        chapter_start = start
        minutes, seconds = divmod(int(start), 60)
        lines.append(f"{minutes}:{seconds:02d} {step_title(caption['text'])}")
    return lines


def write_captions(output_dir: Path, timeline: dict, captions: list[dict]) -> None:
    """Write the burned-in ASS captions and the SRT file for the video platform."""
    lead = lead_seconds(timeline)
    total = lead + body_duration(timeline) + OUTRO_SECONDS
    events = [
        f"Dialogue: 0,{ass_time(0.2)},{ass_time(INTRO_SECONDS)},intro_title,,0,0,0,,"
        f"{{\\fad(300,300)\\pos({WIDTH / 2},{HEIGHT * TITLE_TOP})}}{timeline['title']}",
        f"Dialogue: 0,{ass_time(0.6)},{ass_time(INTRO_SECONDS)},intro_subtitle,,0,0,0,,"
        f"{{\\fad(300,300)\\pos({WIDTH / 2},{HEIGHT * INTRO_SUBTITLE_TOP})}}LarpManager Guide",
        f"Dialogue: 0,{ass_time(total - OUTRO_SECONDS + 0.2)},{ass_time(total)},title,,0,0,0,,"
        f"{{\\fad(300,0)\\pos({WIDTH / 2},{HEIGHT * TITLE_TOP})}}larpmanager.com",
        f"Dialogue: 0,{ass_time(total - OUTRO_SECONDS + 0.6)},{ass_time(total)},subtitle,,0,0,0,,"
        f"{{\\fad(300,0)\\pos({WIDTH / 2},{HEIGHT * SUBTITLE_TOP})}}Manage your LARP events",
        *recap_events(captions, lead),
    ]
    srt_entries = []
    for caption in captions:
        events.append(
            f"Dialogue: 1,{ass_time(caption['start'])},{ass_time(caption['end'])},{caption['kind']},,0,0,0,,"
            f"{{\\fad(180,180)}}{caption['text']}"
        )
        if not caption["kind"].startswith("role_"):
            entry = f"{srt_time(caption['start'])} --> {srt_time(caption['end'])}\n{caption['text']}\n"
            srt_entries.append(f"{len(srt_entries) + 1}\n{entry}")
    (output_dir / "captions.ass").write_text(ASS_HEADER + "\n".join(events) + "\n")
    (output_dir / "captions.srt").write_text("\n".join(srt_entries))


def render(output_dir: Path, timeline: dict, music: Path, logo: Path) -> None:
    """Assemble intro, trimmed capture and outro, then burn captions and add music."""
    body = body_duration(timeline)
    lead = lead_seconds(timeline)
    total = lead + body + OUTRO_SECONDS

    keep = "+".join(f"between(t,{cut_start:.3f},{cut_end:.3f})" for cut_start, cut_end in timeline["cuts"])
    select = f"select='not({keep})'," if keep else ""
    logo_position = f"(W-w)/2:{int(HEIGHT * LOGO_TOP)}"
    video_filter = (
        f"[0:v]{select}setpts=N/{FRAME_RATE}/TB,format=yuv420p,trim=duration={body:.3f}[main];"
        f"[1:v]scale={LOGO_WIDTH}:-1,split[logo_intro][logo_outro];"
        f"color=c={CARD_COLOR}:s={WIDTH}x{HEIGHT}:r={FRAME_RATE}:d={lead}[intro_bg];"
        f"color=c={CARD_COLOR}:s={WIDTH}x{HEIGHT}:r={FRAME_RATE}:d={OUTRO_SECONDS}[outro_bg];"
        f"[intro_bg][logo_intro]overlay={logo_position}:enable='lt(t,{INTRO_SECONDS})',format=yuv420p,setsar=1[intro];"
        f"[outro_bg][logo_outro]overlay={logo_position},format=yuv420p,setsar=1[outro];"
        f"[main]setsar=1[body];"
        f"[intro][body][outro]concat=n=3:v=1:a=0,ass=captions.ass[video];"
        f"[2:a]atrim=duration={total:.3f},asetpts=PTS-STARTPTS,"
        f"afade=t=in:d={MUSIC_FADE_IN},afade=t=out:st={total - MUSIC_FADE_OUT:.3f}:d={MUSIC_FADE_OUT},"
        f"loudnorm=I={MUSIC_LOUDNESS}:TP=-1.5:LRA=11,aresample=48000[audio]"
    )
    run_ffmpeg(
        [
            "-i", "raw.mkv",
            "-i", str(logo.resolve()),
            "-i", str(music.resolve()),
            "-filter_complex", video_filter,
            "-map", "[video]", "-map", "[audio]",
            "-c:v", "libx264", "-preset", "slow", "-crf", "20", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            "guide.mp4",
        ],  # fmt: skip
        output_dir,
    )
    run_ffmpeg(["-ss", str(INTRO_SECONDS / 2), "-i", "guide.mp4", "-frames:v", "1", "thumbnail.png"], output_dir)


def main() -> None:
    """Compose the video found in the given output directory."""
    output_dir, music, logo = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    timeline = json.loads((output_dir / "timeline.json").read_text())
    timeline = align_to_recording(timeline, media_duration(output_dir / "raw.mkv"))
    captions = final_captions(timeline)
    write_captions(output_dir, timeline, captions)
    render(output_dir, timeline, music, logo)
    chapters = "\n".join(chapter_lines(captions))
    description = f"{timeline['title']} - LarpManager\n\nChapters:\n{chapters}\n\nMusic:\n{MUSIC_CREDIT}\n"
    (output_dir / "description.txt").write_text(description)


if __name__ == "__main__":
    main()
