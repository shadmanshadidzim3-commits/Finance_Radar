"""Turn the day's brief into two short vertical videos, English and Bangla.

Faceless format: a synthetic voice reads a script while slides show the figure,
the headline and live subtitles. 1080x1920, so it fits Shorts, Reels and TikTok.

    brief JSON -> script (one small model call, both languages)
               -> number guard (every figure must already be in the brief)
               -> voice (Microsoft Edge neural voices, free; gTTS as fallback)
               -> slides (HTML drawn by headless Chrome/Edge)
               -> MP4 (ffmpeg, shipped inside the imageio-ffmpeg wheel)

Why a browser draws the slides: Pillow cannot shape Bangla without libraqm,
which is missing on Windows, and conjuncts like জ্ব come out as broken pieces.
Chrome and Edge shape Bangla correctly and are already installed on both this
laptop and GitHub's Ubuntu runner, so nothing extra has to be downloaded.

Why the number guard exists: in August 2026 the brief published a taka rate the
market never reached. A video spreads further than a brief and cannot be quietly
corrected, so a script that contains any figure the brief does not is rejected.
"""

from __future__ import annotations

import asyncio
import json
import re
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
W, H = 1080, 1920
FPS = 25
GAP_S = 0.35            # breath between segments

VOICES = {"en": "en-US-AndrewNeural", "bn": "bn-BD-PradeepNeural",
          "banglish": "bn-BD-PradeepNeural"}
GTTS_LANG = {"en": "en", "bn": "bn", "banglish": "bn"}

OUTRO = {
    "en": {"kind": "outro", "label": "60 SECOND FINANCE", "stat": "",
           "on_screen": "Smarter than the cha stall uncle",
           "narration": "And that's your sixty seconds. You now know more than "
                        "the uncle at the cha stall. Follow for tomorrow's episode. "
                        "This is not investment advice."},
    "bn": {"kind": "outro", "label": "60 SECOND FINANCE", "stat": "",
           "on_screen": "কালকের আপডেটের জন্য ফলো করুন",
           "narration": "আজকের ফাইন্যান্স আপডেট এখানেই শেষ। কালকের আপডেট পেতে "
                        "ফলো করুন। এটি বিনিয়োগ পরামর্শ নয়।"},
    "banglish": {"kind": "outro", "label": "60 SECOND FINANCE", "stat": "",
                 "on_screen": "Cha-er dokaner mama ke beat!",
                 "narration": "Bas, sixty second e apni ekhon cha-er dokaner mama-r "
                              "cheye beshi janen. Kalke abar ashben, follow kore rakhun. "
                              "Eta investment advice na.",
                 "speech": "বাস, sixty second এ আপনি এখন চায়ের দোকানের মামার "
                           "চেয়ে বেশি জানেন। কালকে আবার আসবেন, follow করে রাখুন। "
                           "এটা investment advice না।"},
}
DISCLAIMER = {"en": "AI voice · Not investment advice",
              "bn": "এআই ভয়েস · বিনিয়োগ পরামর্শ নয়",
              "banglish": "AI voice · Investment advice na"}
for _o in OUTRO.values():
    _o["icon"] = "people"


class VideoError(RuntimeError):
    pass


# ------------------------------------------------------------------ the script

def _brief_for_script(analysis: dict) -> dict:
    """The slice of the brief the script writer needs, and nothing it could
    misuse. Predictions are left out on purpose: read aloud on a public channel
    they sound like tips."""
    keep = ("rank", "headline", "plain_english", "why_it_matters", "category",
            "bd_impact", "confidence")
    return {
        "top_stories": [{k: s.get(k) for k in keep}
                        for s in (analysis.get("top_stories") or [])[:6]],
        "market_read": analysis.get("market_read"),
        "social_post": analysis.get("social_post"),
        "teaching_note": analysis.get("teaching_note"),
        "jargon_decoder": (analysis.get("jargon_decoder") or [])[:6],
    }


_BN_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")


def _numbers(text: str) -> set[float]:
    t = (text or "").translate(_BN_DIGITS)
    t = re.sub(r"(?<=\d),(?=\d{3})", "", t)          # 1,157 -> 1157
    t = re.sub(r"(?<=\d)\s*[–-]\s*(?=\d)", " ", t)    # ranges are two numbers
    return {float(m) for m in re.findall(r"\d+(?:\.\d+)?", t)}


def _allowed_numbers(analysis: dict, day: str) -> set[float]:
    # Only the text the writer is shown. The full analysis carries URLs, and
    # article IDs like ".../govt-spent-412b-...-4302866" would let "412" through.
    src = _numbers(json.dumps(_brief_for_script(analysis), ensure_ascii=False))
    allowed = set(src)
    # Dropping decimals for speech is fine ("about 109 dollars"); a new figure is not.
    for n in src:
        allowed.update({float(round(n)), round(n, 1), round(n, 2)})
    allowed.update(float(i) for i in range(0, 11))     # counts, "1 of 3"
    allowed.update(_numbers(day))
    allowed.add(60.0)                                  # the channel's name
    return allowed


def check_numbers(script: dict, allowed: set[float]) -> list[str]:
    """Every figure in a language's script that the brief does not contain."""
    bad = []
    for seg in script.get("segments", []):
        for field in ("stat", "on_screen", "narration", "speech"):
            for n in _numbers(seg.get(field, "")):
                if not any(abs(n - a) < 1e-9 for a in allowed):
                    bad.append(f"{n:g} in {seg.get('kind')} {field}: "
                               f"{seg.get(field, '')[:80]!r}")
    return bad


def _valid_shape(script: dict) -> bool:
    segs = script.get("segments")
    return (isinstance(segs, list) and 3 <= len(segs) <= 6 and
            all(isinstance(s, dict) and s.get("narration") for s in segs))


LANGS = ("en", "banglish")


def write_scripts(eng, analysis: dict, day: str, prompt_path: Path,
                  log=print) -> dict:
    """Ask the model for both scripts. Returns {"en": {...}, "bn": {...}} with
    only the languages that passed the number guard. One retry, told exactly
    which figures were rejected."""
    from radar.engine import extract_json

    system = prompt_path.read_text(encoding="utf8")
    user = (f"Date: {day}\n\nToday's brief:\n"
            + json.dumps(_brief_for_script(analysis), ensure_ascii=False, indent=1))
    allowed = _allowed_numbers(analysis, day)

    good: dict = {}
    problems: dict = {}
    for attempt in (1, 2):
        msg = user
        if problems:
            msg += ("\n\nYour previous script was rejected. These figures are not "
                    "in the brief; remove them or copy the brief's exact figure:\n"
                    + "\n".join(f"- [{lang}] {p}"
                                for lang, ps in problems.items() for p in ps))
        data = extract_json(eng.run(system, msg))
        problems = {}
        for lang in LANGS:
            if lang in good:
                continue
            sc = data.get(lang) or {}
            if not _valid_shape(sc) or (lang == "banglish" and not all(
                    s.get("speech") for s in sc.get("segments", []))):
                problems[lang] = ["script missing or malformed"]
                continue
            bad = check_numbers(sc, allowed)
            if bad:
                problems[lang] = bad
            else:
                good[lang] = sc
        if not problems:
            break
        log(f"  video script attempt {attempt} rejected: "
            + "; ".join(f"{k}: {len(v)} issue(s)" for k, v in problems.items()))
        for lang, ps in problems.items():
            for p in ps[:4]:
                log(f"    [{lang}] {p}")

    for sc in good.values():
        sc["segments"] = [s for s in sc["segments"] if s.get("kind") != "outro"]
    return good


# ------------------------------------------------------------------- the voice

def _ffmpeg() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        exe = shutil.which("ffmpeg")
        if not exe:
            raise VideoError("ffmpeg not found: pip install imageio-ffmpeg")
        return exe


def _run(cmd: list[str]) -> None:
    p = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf8", errors="replace")
    if p.returncode != 0:
        raise VideoError(f"ffmpeg failed: {p.stderr[-800:]}")


def _speak(text: str, lang: str, voice: str, mp3: Path) -> str:
    """Synthesise one segment. Returns which engine was used."""
    import time
    import edge_tts

    async def go():
        await edge_tts.Communicate(text, voice, rate="+12%").save(str(mp3))

    # Microsoft's endpoint drops the odd request. One voice switching to
    # another halfway through a video sounds broken, so retry before giving up.
    for attempt in range(4):
        try:
            asyncio.run(go())
            if mp3.exists() and mp3.stat().st_size > 1000:
                return "edge"
        except Exception:
            pass
        time.sleep(2 + 3 * attempt)
    # Fallback keeps the video coming if Microsoft's endpoint refuses the
    # runner. The voice is flatter, but the day is not lost.
    from gtts import gTTS
    gTTS(text, lang=GTTS_LANG[lang]).save(str(mp3))
    return "gtts"


def _to_wav(ff: str, mp3: Path, wav: Path) -> float:
    _run([ff, "-y", "-loglevel", "error", "-i", str(mp3),
          "-ar", "44100", "-ac", "1", "-sample_fmt", "s16", str(wav)])
    with wave.open(str(wav)) as w:
        return w.getnframes() / w.getframerate()


def _join_wavs(parts: list[Path], gap_s: float, out: Path) -> None:
    with wave.open(str(parts[0])) as w0:
        params = w0.getparams()
    silence = b"\x00\x00" * int(params.framerate * gap_s)
    with wave.open(str(out), "wb") as o:
        o.setparams(params)
        for i, p in enumerate(parts):
            with wave.open(str(p)) as w:
                o.writeframes(w.readframes(w.getnframes()))
            if i < len(parts) - 1:
                o.writeframes(silence)


# -------------------------------------------------------------------- assembly

def _tone(stat: str) -> str:
    s = (stat or "").strip()
    if s.startswith(("-", "−", "▼")):
        return "down"
    if s.startswith(("+", "▲")):
        return "up"
    return ""


def _chunks(text: str, max_chars: int) -> list[str]:
    """Split narration into subtitle-sized pieces, preferring sentence ends."""
    out: list[str] = []
    for sent in re.split(r"(?<=[.!?।])\s+", text.strip()):
        cur = ""
        for w in sent.split():
            if cur and len(cur) + 1 + len(w) > max_chars:
                out.append(cur)
                cur = w
            else:
                cur = f"{cur} {w}".strip()
        if cur:
            out.append(cur)
    return out or [text]


def _launch(p):
    """Use a Chrome or Edge that is already installed; download nothing."""
    tried = []
    for ch in ("chrome", "msedge"):
        try:
            return p.chromium.launch(channel=ch)
        except Exception as e:
            tried.append(f"{ch}: {str(e).splitlines()[0][:120]}")
    for exe in ("google-chrome", "google-chrome-stable", "chromium",
                "chromium-browser", "msedge"):
        path = shutil.which(exe)
        if path:
            return p.chromium.launch(executable_path=path)
    try:
        return p.chromium.launch()
    except Exception as e:
        tried.append(f"bundled: {str(e).splitlines()[0][:120]}")
    raise VideoError("no Chrome/Edge found for drawing slides:\n  " + "\n  ".join(tried))


def build_video(script: dict, lang: str, day: str, out_path: Path,
                brand: str = "60 SECOND FINANCE", voice: str | None = None,
                log=print) -> dict:
    from playwright.sync_api import sync_playwright
    from radar import whiteboard

    ff = _ffmpeg()
    segs = list(script["segments"]) + [OUTRO[lang]]
    voice = voice or VOICES[lang]
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=f"radar_video_{lang}_"))

    try:
        # 1. Voice, one file per segment, so each slide knows its exact length.
        #    Banglish is spoken from `speech` (Bangla script, English words in
        #    English letters) and subtitled from `narration` (Roman letters).
        wavs, durs, engines = [], [], set()
        for i, seg in enumerate(segs):
            mp3, wav = work / f"v{i}.mp3", work / f"v{i}.wav"
            engines.add(_speak(seg.get("speech") or seg["narration"], lang, voice, mp3))
            durs.append(_to_wav(ff, mp3, wav))
            wavs.append(wav)
        audio = work / "voice.wav"
        _join_wavs(wavs, GAP_S, audio)

        # 2. The timeline: each slide lasts its voice plus the breath after it;
        #    subtitles are timed by their share of the segment's characters.
        scenes, start = [], 0.0
        for i, (seg, dur) in enumerate(zip(segs, durs)):
            span = dur + (GAP_S if i < len(segs) - 1 else 0.6)
            pieces = _chunks(seg["narration"], 30)
            weights = [len(c) + 3 for c in pieces]
            subs, acc = [], 0.0
            for c, w in zip(pieces, weights):
                d = dur * w / sum(weights)
                subs.append({"t0": acc, "t1": acc + d, "text": c})
                acc += d
            subs[-1]["t1"] = span
            icon = seg.get("icon")
            if icon not in whiteboard.ICONS:
                icon = whiteboard.DEFAULT_ICON.get(seg.get("kind"), "document")
            scenes.append({
                "label": seg.get("label", ""), "head": seg.get("on_screen", ""),
                "stat": seg.get("stat", ""), "tone": _tone(seg.get("stat", "")),
                "icon": icon, "start": start, "dur": span, "subs": subs})
            start += span
        total = start

        # 3. Draw it.
        with sync_playwright() as p:
            browser = _launch(p)
            page = browser.new_page(viewport={"width": W, "height": H})
            page.set_content(whiteboard.page_html(lang))
            page.evaluate("document.fonts.ready")
            frames = whiteboard.render_frames(
                page, {"brand": brand, "date": day, "foot": DISCLAIMER[lang],
                       "scenes": scenes}, total, FPS, work, log=log)
            browser.close()

        # 4. Stitch. The concat demuxer needs the last image listed twice.
        lst = work / "frames.txt"
        lines = []
        for img, t in frames:
            lines += [f"file '{img.as_posix()}'", f"duration {t:.4f}"]
        lines.append(f"file '{frames[-1][0].as_posix()}'")
        lst.write_text("\n".join(lines), encoding="utf8")
        _run([ff, "-y", "-loglevel", "error",
              "-f", "concat", "-safe", "0", "-i", str(lst), "-i", str(audio),
              "-vf", f"fps={FPS},format=yuv420p", "-c:v", "libx264",
              "-preset", "medium", "-crf", "24",
              "-c:a", "aac", "-b:a", "128k", "-shortest",
              "-movflags", "+faststart", str(out_path)])

        words = sum(len(s["narration"].split()) for s in segs)
        return {"path": out_path, "seconds": round(total, 1), "words": words,
                "voice": voice if engines == {"edge"} else "/".join(sorted(engines)),
                "mb": round(out_path.stat().st_size / 1e6, 2)}
    finally:
        shutil.rmtree(work, ignore_errors=True)


def caption_text(script: dict) -> str:
    tags = " ".join("#" + t.lstrip("#").replace(" ", "") for t in script.get("hashtags", []))
    return f"{script.get('title', '')}\n\n{script.get('caption', '')}\n\n{tags}".strip()


def make_videos(eng, analysis: dict, day: str, out_dir: Path, cfg: dict,
                brand: str, prompt_path: Path, log=print) -> list[dict]:
    """Script both languages and render each one that passed the guard.
    Never raises: a failed video must not cost the day's brief."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        scripts = write_scripts(eng, analysis, day, prompt_path, log=log)
    except Exception as e:
        log(f"  video script failed ({type(e).__name__}: {e})")
        return []

    # Kept as a small text file in git: what was said, for checking later.
    (out_dir / f"{day}_script.json").write_text(
        json.dumps(scripts, ensure_ascii=False, indent=1), encoding="utf8")

    voices = cfg.get("voices") or {}
    results = []
    for lang in cfg.get("languages", list(LANGS)):
        if lang not in scripts:
            log(f"  [{lang}] no video today: script failed the number check twice")
            continue
        try:
            info = build_video(scripts[lang], lang, day, out_dir / f"{day}_{lang}.mp4",
                               brand=brand, voice=voices.get(lang), log=log)
            cap = out_dir / f"{day}_{lang}_caption.txt"
            cap.write_text(caption_text(scripts[lang]), encoding="utf8")
            info.update(lang=lang, caption=cap)
            results.append(info)
            log(f"  [{lang}] {info['seconds']}s · {info['words']} words · "
                f"{info['mb']} MB · voice {info['voice']} → {info['path']}")
        except Exception as e:
            log(f"  [{lang}] video failed ({type(e).__name__}: {e})")
    return results
