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
import base64
import html
import json
import re
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FONTS = ROOT / "assets" / "fonts"
W, H = 1080, 1920
FPS = 30
GAP_S = 0.35            # breath between segments

VOICES = {"en": "en-US-AndrewNeural", "bn": "bn-BD-PradeepNeural"}
GTTS_LANG = {"en": "en", "bn": "bn"}

OUTRO = {
    "en": {"kind": "outro", "label": "60 SECOND FINANCE", "stat": "",
           "on_screen": "Follow for tomorrow's brief",
           "narration": "That's your sixty seconds of finance. Follow for "
                        "tomorrow's brief. This is not investment advice."},
    "bn": {"kind": "outro", "label": "60 SECOND FINANCE", "stat": "",
           "on_screen": "কালকের আপডেটের জন্য ফলো করুন",
           "narration": "আজকের ফাইন্যান্স আপডেট এখানেই শেষ। কালকের আপডেট পেতে "
                        "ফলো করুন। এটি বিনিয়োগ পরামর্শ নয়।"},
}
DISCLAIMER = {"en": "AI voice · Not investment advice",
              "bn": "এআই ভয়েস · বিনিয়োগ পরামর্শ নয়"}


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
        for field in ("stat", "on_screen", "narration"):
            for n in _numbers(seg.get(field, "")):
                if not any(abs(n - a) < 1e-9 for a in allowed):
                    bad.append(f"{n:g} in {seg.get('kind')} {field}: "
                               f"{seg.get(field, '')[:80]!r}")
    return bad


def _valid_shape(script: dict) -> bool:
    segs = script.get("segments")
    return (isinstance(segs, list) and 3 <= len(segs) <= 6 and
            all(isinstance(s, dict) and s.get("narration") for s in segs))


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
        for lang in ("en", "bn"):
            if lang in good:
                continue
            sc = data.get(lang) or {}
            if not _valid_shape(sc):
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
        await edge_tts.Communicate(text, voice, rate="+6%").save(str(mp3))

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


# ------------------------------------------------------------------ the slides

def _font_face(name: str, file: str) -> str:
    data = base64.b64encode((FONTS / file).read_bytes()).decode()
    return (f"@font-face{{font-family:'{name}';"
            f"src:url(data:font/ttf;base64,{data}) format('truetype');"
            f"font-weight:100 900;}}")


PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
FONTFACES
*{box-sizing:border-box;margin:0;padding:0}
html,body{width:1080px;height:1920px;overflow:hidden}
body{background:#0b1220;color:#f4f6fa;
  font-family:'Inter','Noto Sans Bengali',sans-serif;position:relative}
body.bn{font-family:'Noto Sans Bengali','Inter',sans-serif}
.glow{position:absolute;inset:0;
  background:radial-gradient(900px 700px at 85% 8%,rgba(45,212,191,.16),transparent 70%),
             radial-gradient(800px 800px at 0% 100%,rgba(96,165,250,.10),transparent 70%)}
.top{position:absolute;left:72px;right:72px;top:96px}
.brand{display:flex;justify-content:space-between;align-items:baseline}
.brand b{font-size:34px;letter-spacing:.16em;color:#2dd4bf;font-weight:800;font-family:'Inter'}
.brand span{font-size:30px;color:#94a3b8;font-family:'Inter'}
.bars{display:flex;gap:12px;margin-top:30px}
.bars i{flex:1;height:8px;border-radius:4px;background:rgba(148,163,184,.25)}
.bars i.on{background:#2dd4bf}
.main{position:absolute;left:72px;right:72px;top:330px}
.label{display:inline-block;font-size:32px;font-weight:700;letter-spacing:.1em;
  color:#0b1220;background:#2dd4bf;padding:10px 24px;border-radius:10px}
.stat{font-size:200px;font-weight:800;line-height:1.05;margin-top:56px;
  letter-spacing:-.02em;color:#2dd4bf;font-family:'Inter','Noto Sans Bengali'}
.stat.up{color:#60a5fa}.stat.down{color:#f87171}
.head{font-size:76px;font-weight:800;line-height:1.18;margin-top:44px}
body.bn .head{line-height:1.4}
.sub{position:absolute;left:72px;right:72px;top:1270px;min-height:250px;
  background:rgba(15,23,42,.88);border-left:10px solid #2dd4bf;border-radius:18px;
  padding:34px 40px;font-size:56px;font-weight:600;line-height:1.32;color:#fff}
body.bn .sub{line-height:1.5}
.foot{position:absolute;left:72px;right:72px;top:1580px;font-size:28px;color:#94a3b8}
</style></head><body>
<div class="glow"></div>
<div class="top"><div class="brand"><b>BRAND</b><span id="date"></span></div>
  <div class="bars" id="bars"></div></div>
<div class="main"><div class="label" id="label"></div>
  <div class="stat" id="stat"></div><div class="head" id="head"></div></div>
<div class="sub" id="sub"></div>
<div class="foot" id="foot"></div>
<script>
// Shrink only on real overflow: width for the one-line figure, the height cap
// for the headline. Comparing scrollHeight to clientHeight misfires, because
// tall glyphs poke past the line box and every figure shrank to the minimum.
function fit(el,max,min,capH){let s=max;el.style.fontSize=s+'px';
  const over=()=>el.scrollWidth>el.clientWidth+1||(capH&&el.scrollHeight>capH);
  while(over()&&s>min){s-=6;el.style.fontSize=s+'px'}}
window.paint=function(f){
  document.body.className=f.lang;
  document.getElementById('date').textContent=f.date;
  document.getElementById('bars').innerHTML=Array.from({length:f.n},(_,i)=>
    '<i class="'+(i<=f.i?'on':'')+'"></i>').join('');
  const l=document.getElementById('label');l.textContent=f.label;l.style.display=f.label?'inline-block':'none';
  const s=document.getElementById('stat');s.textContent=f.stat;s.className='stat '+f.tone;
  s.style.display=f.stat?'block':'none';s.style.whiteSpace='nowrap';s.style.width='936px';fit(s,200,90);
  const h=document.getElementById('head');h.textContent=f.head;
  fit(h,f.stat?76:96,48,f.stat?560:820);
  const b=document.getElementById('sub');b.textContent=f.sub;
  b.style.visibility=f.sub?'visible':'hidden';
  document.getElementById('foot').textContent=f.foot;
}
</script></body></html>"""


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


# -------------------------------------------------------------------- assembly

def build_video(script: dict, lang: str, day: str, out_path: Path,
                brand: str = "60 SECOND FINANCE", voice: str | None = None,
                log=print) -> dict:
    from playwright.sync_api import sync_playwright

    ff = _ffmpeg()
    segs = list(script["segments"]) + [OUTRO[lang]]
    voice = voice or VOICES[lang]
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=f"radar_video_{lang}_"))

    try:
        # 1. Voice, one file per segment, so each slide knows its exact length.
        wavs, durs, engines = [], [], set()
        for i, seg in enumerate(segs):
            mp3, wav = work / f"v{i}.mp3", work / f"v{i}.wav"
            engines.add(_speak(seg["narration"], lang, voice, mp3))
            durs.append(_to_wav(ff, mp3, wav))
            wavs.append(wav)
        audio = work / "voice.wav"
        _join_wavs(wavs, GAP_S, audio)

        # 2. Slides: one image per subtitle chunk, timed by its share of the
        #    segment's characters. Close enough to speech pace to read along.
        max_chars = 30 if lang == "en" else 30
        frames: list[tuple[Path, float]] = []
        faces = _font_face("Inter", "Inter.ttf") + _font_face("Noto Sans Bengali",
                                                              "NotoSansBengali.ttf")
        page_html = PAGE.replace("FONTFACES", faces).replace("BRAND", html.escape(brand))
        n_content = len(segs)
        with sync_playwright() as p:
            browser = _launch(p)
            page = browser.new_page(viewport={"width": W, "height": H})
            page.set_content(page_html)
            page.evaluate("document.fonts.ready")
            k = 0
            for i, (seg, dur) in enumerate(zip(segs, durs)):
                pieces = _chunks(seg["narration"], max_chars)
                weights = [len(c) + 3 for c in pieces]
                total = sum(weights)
                for j, (chunk, wgt) in enumerate(zip(pieces, weights)):
                    t = dur * wgt / total
                    if j == len(pieces) - 1 and i < len(segs) - 1:
                        t += GAP_S
                    page.evaluate("f => window.paint(f)", {
                        "lang": lang, "date": day, "n": n_content, "i": i,
                        "label": seg.get("label", ""), "stat": seg.get("stat", ""),
                        "tone": _tone(seg.get("stat", "")),
                        "head": seg.get("on_screen", ""), "sub": chunk,
                        "foot": DISCLAIMER[lang]})
                    img = work / f"f{k:03d}.png"
                    page.screenshot(path=str(img))
                    frames.append((img, t))
                    k += 1
            browser.close()

        # 3. Stitch. The concat demuxer needs the last image listed twice.
        lst = work / "frames.txt"
        lines = []
        for img, t in frames:
            lines += [f"file '{img.as_posix()}'", f"duration {t:.3f}"]
        lines.append(f"file '{frames[-1][0].as_posix()}'")
        lst.write_text("\n".join(lines), encoding="utf8")
        _run([ff, "-y", "-loglevel", "error",
              "-f", "concat", "-safe", "0", "-i", str(lst), "-i", str(audio),
              "-vf", f"fps={FPS},format=yuv420p", "-c:v", "libx264",
              "-preset", "medium", "-crf", "23", "-tune", "stillimage",
              "-c:a", "aac", "-b:a", "128k", "-shortest",
              "-movflags", "+faststart", str(out_path)])

        seconds = sum(durs) + GAP_S * (len(durs) - 1)
        words = sum(len(s["narration"].split()) for s in segs)
        return {"path": out_path, "seconds": round(seconds, 1), "words": words,
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
    for lang in cfg.get("languages", ["en", "bn"]):
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
