import os
import shutil
import tempfile
from typing import Callable

import imageio_ffmpeg
import streamlit as st
import whisper
from PIL import Image, ImageDraw, ImageFont
from moviepy import ColorClip, CompositeVideoClip, TextClip, VideoFileClip


def _ensure_ffmpeg_on_path() -> None:
    """Whisper calls `ffmpeg` via subprocess; ensure it is reachable."""
    try:
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        # Whisper looks for an executable named `ffmpeg` / `ffmpeg.exe` on PATH.
        # The bundled imageio binary is usually named like `ffmpeg-win-x86_64-*.exe`,
        # so we create a stable shim copy in a writable folder and add it to PATH.
        shim_dir = os.path.join(os.path.dirname(__file__), ".ffmpeg_bin")
        os.makedirs(shim_dir, exist_ok=True)

        shim_name = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
        shim_exe = os.path.join(shim_dir, shim_name)

        if not os.path.exists(shim_exe) and os.path.exists(ffmpeg_exe):
            shutil.copyfile(ffmpeg_exe, shim_exe)

        path = os.environ.get("PATH", "")
        if shim_dir and shim_dir not in path:
            os.environ["PATH"] = f"{shim_dir}{os.pathsep}{path}"
    except Exception:
        # If this fails, Whisper may still work if ffmpeg is already on PATH.
        pass


@st.cache_resource
def load_whisper_model():
    _ensure_ffmpeg_on_path()
    return whisper.load_model("base")


def _y_for_position(position_sel: str, video_h: int, text_h: int, margin: int = 24) -> int:
    if position_sel == "top":
        return margin
    if position_sel == "bottom":
        return max(margin, video_h - text_h - margin)
    # center / left / right -> center vertically
    return max(margin, int((video_h - text_h) / 2))


def _target_xy(position_sel: str, video_w: int, video_h: int, text_w: int, text_h: int, margin: int = 24) -> tuple[int, int]:
    if position_sel == "bottom":
        return (max(margin, int((video_w - text_w) / 2)), max(margin, video_h - text_h - margin))
    if position_sel == "top":
        return (max(margin, int((video_w - text_w) / 2)), margin)
    if position_sel == "left":
        return (margin, max(margin, int((video_h - text_h) / 2)))
    if position_sel == "right":
        return (max(margin, video_w - text_w - margin), max(margin, int((video_h - text_h) / 2)))
    # center
    return (max(margin, int((video_w - text_w) / 2)), max(margin, int((video_h - text_h) / 2)))


def _slide_in_position_fn(
    *,
    start_x: int,
    start_y: int,
    target_x: int,
    target_y: int,
    anim_duration: float,
):
    anim_duration = max(0.05, float(anim_duration))

    def pos(t: float) -> tuple[float, float]:
        if t <= 0:
            return (float(start_x), float(start_y))
        if t >= anim_duration:
            return (float(target_x), float(target_y))
        p = float(t) / anim_duration
        x = float(start_x) + (float(target_x) - float(start_x)) * p
        y = float(start_y) + (float(target_y) - float(start_y)) * p
        return (x, y)

    return pos


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    hex_color = (hex_color or "").strip()
    if hex_color.startswith("#"):
        hex_color = hex_color[1:]
    if len(hex_color) != 6:
        return (0, 0, 0)
    try:
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        return (r, g, b)
    except Exception:
        return (0, 0, 0)


def _hex_to_rgba(hex_color: str, alpha: float) -> tuple[int, int, int, int]:
    r, g, b = _hex_to_rgb(hex_color)
    a = int(max(0.0, min(1.0, float(alpha))) * 255)
    return (r, g, b, a)


def render_font_sample(
    *,
    font_path: str,
    text: str,
    font_size: int,
    text_color: str,
    stroke_width: int,
    stroke_color: str,
    shadow_enabled: bool,
    shadow_color: str,
    shadow_opacity: float,
    shadow_dx: int,
    shadow_dy: int,
    box_enabled: bool,
    box_color: str,
    box_opacity: float,
    box_padding: int,
    width: int = 900,
    height: int = 220,
):
    """Render a small sample image showing the current font + styling."""
    sample_text = (text or "").strip() or "The quick brown fox 123"
    sample_text = sample_text.replace("\n", " ")
    if len(sample_text) > 60:
        sample_text = sample_text[:57] + "..."

    img = Image.new("RGBA", (int(width), int(height)), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    try:
        pil_font = ImageFont.truetype(font_path, int(font_size))
    except Exception:
        pil_font = ImageFont.load_default()

    # Measure
    bbox = draw.textbbox((0, 0), sample_text, font=pil_font, stroke_width=int(stroke_width))
    text_w = max(1, bbox[2] - bbox[0])
    text_h = max(1, bbox[3] - bbox[1])

    x = max(10, int((width - text_w) / 2))
    y = max(10, int((height - text_h) / 2))

    if box_enabled and box_opacity > 0:
        pad = max(0, int(box_padding))
        bx0 = max(0, x - pad)
        by0 = max(0, y - pad)
        bx1 = min(width, x + text_w + pad)
        by1 = min(height, y + text_h + pad)
        draw.rectangle([bx0, by0, bx1, by1], fill=_hex_to_rgba(box_color, box_opacity))

    if shadow_enabled and shadow_opacity > 0:
        draw.text(
            (x + int(shadow_dx), y + int(shadow_dy)),
            sample_text,
            font=pil_font,
            fill=_hex_to_rgba(shadow_color, shadow_opacity),
            stroke_width=0,
        )

    # Main text (stroke/outline supported by Pillow)
    draw.text(
        (x, y),
        sample_text,
        font=pil_font,
        fill=_hex_to_rgba(text_color, 1.0),
        stroke_width=int(stroke_width) if stroke_width else 0,
        stroke_fill=_hex_to_rgba(stroke_color, 1.0) if stroke_width else None,
    )

    return img


def _resolve_font_style(
    *,
    font_key: str,
    bold: bool,
    italic: bool,
    custom_font_path: str | None,
) -> str:
    """Return a font path/name suitable for MoviePy+Pillow.

    On Windows we map to actual files in C:\\Windows\\Fonts.
    Custom font upload takes precedence; in that case bold/italic are not auto-derived.
    """
    if custom_font_path:
        return custom_font_path

    variants = {
        "Arial": {
            "regular": "arial.ttf",
            "bold": "arialbd.ttf",
            "italic": "ariali.ttf",
            "bold_italic": "arialbi.ttf",
        },
        "Helvetica": {
            "regular": "arial.ttf",
            "bold": "arialbd.ttf",
            "italic": "ariali.ttf",
            "bold_italic": "arialbi.ttf",
        },
        "Courier": {
            "regular": "cour.ttf",
            "bold": "courbd.ttf",
            "italic": "couri.ttf",
            "bold_italic": "courbi.ttf",
        },
        "Times New Roman": {
            "regular": "times.ttf",
            "bold": "timesbd.ttf",
            "italic": "timesi.ttf",
            "bold_italic": "timesbi.ttf",
        },
        "Georgia": {
            "regular": "georgia.ttf",
            "bold": "georgiab.ttf",
            "italic": "georgiai.ttf",
            "bold_italic": "georgiaz.ttf",
        },
        "Verdana": {
            "regular": "verdana.ttf",
            "bold": "verdanab.ttf",
            "italic": "verdanai.ttf",
            "bold_italic": "verdanaz.ttf",
        },
        "Impact": {
            "regular": "impact.ttf",
            "bold": "impact.ttf",
            "italic": "impact.ttf",
            "bold_italic": "impact.ttf",
        },
    }

    chosen = variants.get(font_key, variants["Arial"])
    if bold and italic:
        font_filename = chosen.get("bold_italic") or chosen["regular"]
    elif bold:
        font_filename = chosen.get("bold") or chosen["regular"]
    elif italic:
        font_filename = chosen.get("italic") or chosen["regular"]
    else:
        font_filename = chosen["regular"]

    if os.name == "nt":
        font_path = os.path.join("C:\\Windows\\Fonts", font_filename)
        return font_path if os.path.exists(font_path) else chosen["regular"]

    # Non-Windows (e.g., Streamlit Community Cloud on Linux):
    # Prefer a font file bundled with the app if present.
    # Users can copy their own fonts into `fonts/` (see README) if they have rights.
    repo_dir = os.path.dirname(__file__)
    bundled_dir = os.path.join(repo_dir, "fonts")
    if os.path.isdir(bundled_dir):
        # Prefer common Arial-style names first to make it easy.
        # Supported variant naming examples:
        # - arial.ttf / arialbd.ttf / ariali.ttf / arialbi.ttf
        # - Arial.ttf / Arial Bold.ttf / Arial Italic.ttf / Arial Bold Italic.ttf
        desired: list[str] = []
        if font_key in {"Arial", "Helvetica"}:
            if bold and italic:
                desired += ["arialbi.ttf", "Arial Bold Italic.ttf", "Arial-BoldItalic.ttf"]
            elif bold:
                desired += ["arialbd.ttf", "Arial Bold.ttf", "Arial-Bold.ttf"]
            elif italic:
                desired += ["ariali.ttf", "Arial Italic.ttf", "Arial-Italic.ttf"]
            else:
                desired += ["arial.ttf", "Arial.ttf"]
        # Also try the Windows filename we would have chosen for this font family.
        desired.append(font_filename)

        for name in desired:
            candidate = os.path.join(bundled_dir, name)
            if os.path.exists(candidate):
                return candidate

    # Linux/Streamlit Cloud: Windows font filenames like "arial.ttf" may not exist.
    # Prefer commonly available system fonts (DejaVu/Liberation) when present.
    linux_candidates: list[str] = []

    def add_if(*paths: str) -> None:
        for p in paths:
            if p and p not in linux_candidates:
                linux_candidates.append(p)

    # DejaVu
    if font_key in {"Arial", "Helvetica", "Verdana", "Impact"}:
        add_if(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-BoldOblique.ttf",
        )
    elif font_key in {"Courier"}:
        add_if(
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Oblique.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-BoldOblique.ttf",
        )
    else:  # Times New Roman / Georgia
        add_if(
            "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSerif-BoldItalic.ttf",
        )

    # Liberation (common on many distros)
    add_if(
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Italic.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-BoldItalic.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
    )

    for candidate in linux_candidates:
        if os.path.exists(candidate):
            return candidate

    # As a last resort, return empty string so callers can omit font.
    return ""


def _as_pos_fn(pos: tuple[int, int] | Callable[[float], tuple[float, float]]):
    if callable(pos):
        return pos
    x0, y0 = pos

    def fn(_t: float) -> tuple[float, float]:
        return (float(x0), float(y0))

    return fn


def _make_styled_layers(
    *,
    base_clip: VideoFileClip,
    text: str,
    fontsize: int,
    color: str,
    font: str,
    text_box_w: int,
    text_box_h: int,
    text_align: str,
    pos: tuple[int, int] | Callable[[float], tuple[float, float]],
    start: float,
    duration: float,
    stroke_width: int,
    stroke_color: str,
    shadow_enabled: bool,
    shadow_color: str,
    shadow_opacity: float,
    shadow_dx: int,
    shadow_dy: int,
    box_enabled: bool,
    box_color: str,
    box_opacity: float,
    box_padding: int,
):
    """Returns (layers_to_add, text_clip_created)."""
    duration = max(0.05, float(duration))
    pos_fn = _as_pos_fn(pos)

    def clamp_xy(
        x: float,
        y: float,
        clip_w: int,
        clip_h: int,
        *,
        edge: int = 1,
    ) -> tuple[float, float]:
        """Clamp to ensure at least 1px overlaps the base frame.

        MoviePy can throw broadcasting errors if a layer is fully off-screen.
        """
        base_w = int(getattr(base_clip, "w", 0) or 0)
        base_h = int(getattr(base_clip, "h", 0) or 0)
        cw = max(1, int(clip_w))
        ch = max(1, int(clip_h))
        bw = max(1, base_w)
        bh = max(1, base_h)

        min_x = -cw + edge
        max_x = bw - edge
        min_y = -ch + edge
        max_y = bh - edge

        cx = float(min(max(float(x), float(min_x)), float(max_x)))
        cy = float(min(max(float(y), float(min_y)), float(max_y)))
        return (cx, cy)

    txt_clip = TextClip(
        **{
            "text": text,
            "font_size": fontsize,
            **({"font": font} if font else {}),
            "color": color,
            "method": "caption",
            "size": (max(1, int(text_box_w)), max(1, int(text_box_h))),
            "text_align": text_align,
            "stroke_color": stroke_color if stroke_width > 0 else None,
            "stroke_width": int(stroke_width) if stroke_width > 0 else 0,
        }
    ).with_start(float(start)).with_duration(duration)

    layers: list = []

    if box_enabled and box_opacity > 0:
        pad = max(0, int(box_padding))
        box_rgb = _hex_to_rgb(box_color)
        box_clip = (
            ColorClip(
                size=(max(1, txt_clip.w + pad * 2), max(1, txt_clip.h + pad * 2)),
                color=box_rgb,
            )
            .with_opacity(float(box_opacity))
            .with_start(float(start))
            .with_duration(duration)
        )

        def box_pos(t: float, pad=pad) -> tuple[float, float]:
            x, y = pos_fn(t)
            return clamp_xy(x - pad, y - pad, box_clip.w, box_clip.h)

        layers.append(box_clip.with_position(box_pos))

    if shadow_enabled and shadow_opacity > 0:
        shadow_clip = TextClip(
            **{
                "text": text,
                "font_size": fontsize,
                **({"font": font} if font else {}),
                "color": shadow_color,
                "method": "caption",
                "size": (max(1, int(text_box_w)), max(1, int(text_box_h))),
                "text_align": text_align,
            }
        ).with_start(float(start)).with_duration(duration).with_opacity(float(shadow_opacity))

        def shadow_pos(t: float, dx=int(shadow_dx), dy=int(shadow_dy)) -> tuple[float, float]:
            x, y = pos_fn(t)
            return clamp_xy(x + dx, y + dy, shadow_clip.w, shadow_clip.h)

        layers.append(shadow_clip.with_position(shadow_pos))

    def main_pos(t: float) -> tuple[float, float]:
        x, y = pos_fn(t)
        return clamp_xy(x, y, txt_clip.w, txt_clip.h)

    layers.append(txt_clip.with_position(main_pos))
    return layers, txt_clip


def process_video_clip(
    input_path: str,
    output_path: str,
    text: str | None,
    fontsize: int,
    color: str,
    font: str,
    position_sel: str,
    limit_duration: int | None = None,
    use_captions: bool = False,
    animate_in: bool = False,
    animate_from: str = "bottom",
    animate_duration: float = 0.6,
    stroke_width: int = 0,
    stroke_color: str = "#000000",
    shadow_enabled: bool = False,
    shadow_color: str = "#000000",
    shadow_opacity: float = 0.4,
    shadow_dx: int = 2,
    shadow_dy: int = 2,
    box_enabled: bool = False,
    box_color: str = "#000000",
    box_opacity: float = 0.25,
    box_padding: int = 16,
):
    try:
        _ensure_ffmpeg_on_path()
        clip = VideoFileClip(input_path)

        final_dur = clip.duration
        if limit_duration and limit_duration < final_dur:
            final_dur = float(limit_duration)
            clip = clip.subclipped(0, final_dur)

        final_clips: list = [clip]
        created_text_clips: list[TextClip] = []
        created_other_clips: list = []

        if use_captions:
            if clip.audio is None:
                return False, "No audio track found to generate captions."

            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                audio_path = f.name
            clip.audio.write_audiofile(audio_path, logger=None)

            model = load_whisper_model()
            result = model.transcribe(audio_path)
            segments = result.get("segments", [])

            if os.path.exists(audio_path):
                os.remove(audio_path)

            for segment in segments:
                start_time = float(segment.get("start", 0.0))
                end_time = float(segment.get("end", 0.0))
                seg_text = (segment.get("text", "") or "").strip()

                if not seg_text:
                    continue

                seg_duration = max(0.05, end_time - start_time)

                text_box_w = int(clip.w * 0.9)
                text_box_h = max(1, int(clip.h * 0.25))

                # Compute target position based on resulting rendered text size.
                # Create a temporary clip just to get (w,h) reliably with our box size.
                measure_clip = TextClip(
                    **{
                        "text": seg_text,
                        "font_size": fontsize,
                        **({"font": font} if font else {}),
                        "color": color,
                        "method": "caption",
                        "size": (text_box_w, text_box_h),
                        "text_align": "center",
                    }
                )
                measure_w, measure_h = int(measure_clip.w), int(measure_clip.h)
                target_x, target_y = _target_xy(position_sel, clip.w, clip.h, measure_w, measure_h)
                try:
                    measure_clip.close()
                except Exception:
                    pass

                if animate_in:
                    edge = 1
                    if animate_from == "top":
                        start_x, start_y = target_x, -measure_h + edge
                    elif animate_from == "left":
                        start_x, start_y = -measure_w + edge, target_y
                    elif animate_from == "right":
                        start_x, start_y = clip.w - edge, target_y
                    else:
                        start_x, start_y = target_x, clip.h - edge
                    pos: tuple[int, int] | Callable[[float], tuple[float, float]] = _slide_in_position_fn(
                        start_x=start_x,
                        start_y=start_y,
                        target_x=target_x,
                        target_y=target_y,
                        anim_duration=min(float(animate_duration), seg_duration),
                    )
                else:
                    pos = (target_x, target_y)

                layers, main_text = _make_styled_layers(
                    base_clip=clip,
                    text=seg_text,
                    fontsize=fontsize,
                    color=color,
                    font=font,
                    text_box_w=text_box_w,
                    text_box_h=text_box_h,
                    text_align="center",
                    pos=pos,
                    start=start_time,
                    duration=seg_duration,
                    stroke_width=stroke_width,
                    stroke_color=stroke_color,
                    shadow_enabled=shadow_enabled,
                    shadow_color=shadow_color,
                    shadow_opacity=shadow_opacity,
                    shadow_dx=shadow_dx,
                    shadow_dy=shadow_dy,
                    box_enabled=box_enabled,
                    box_color=box_color,
                    box_opacity=box_opacity,
                    box_padding=box_padding,
                )

                for layer in layers:
                    final_clips.append(layer)
                    if isinstance(layer, TextClip):
                        created_text_clips.append(layer)
                    else:
                        created_other_clips.append(layer)
                created_text_clips.append(main_text)

        else:
            if not text:
                return False, "Overlay text is empty."

            text_box_w = int(clip.w)
            text_box_h = max(1, int(clip.h * 0.25))

            measure_clip = TextClip(
                **{
                    "text": text,
                    "font_size": fontsize,
                    **({"font": font} if font else {}),
                    "color": color,
                    "method": "caption",
                    "size": (text_box_w, text_box_h),
                    "text_align": "center",
                }
            )
            measure_w, measure_h = int(measure_clip.w), int(measure_clip.h)
            target_x, target_y = _target_xy(position_sel, clip.w, clip.h, measure_w, measure_h)
            try:
                measure_clip.close()
            except Exception:
                pass

            if animate_in:
                edge = 1
                if animate_from == "top":
                    start_x, start_y = target_x, -measure_h + edge
                elif animate_from == "left":
                    start_x, start_y = -measure_w + edge, target_y
                elif animate_from == "right":
                    start_x, start_y = clip.w - edge, target_y
                else:
                    start_x, start_y = target_x, clip.h - edge
                pos = _slide_in_position_fn(
                    start_x=start_x,
                    start_y=start_y,
                    target_x=target_x,
                    target_y=target_y,
                    anim_duration=float(animate_duration),
                )
            else:
                pos = (target_x, target_y)

            layers, main_text = _make_styled_layers(
                base_clip=clip,
                text=text,
                fontsize=fontsize,
                color=color,
                font=font,
                text_box_w=text_box_w,
                text_box_h=text_box_h,
                text_align="center",
                pos=pos,
                start=0.0,
                duration=final_dur,
                stroke_width=stroke_width,
                stroke_color=stroke_color,
                shadow_enabled=shadow_enabled,
                shadow_color=shadow_color,
                shadow_opacity=shadow_opacity,
                shadow_dx=shadow_dx,
                shadow_dy=shadow_dy,
                box_enabled=box_enabled,
                box_color=box_color,
                box_opacity=box_opacity,
                box_padding=box_padding,
            )

            for layer in layers:
                final_clips.append(layer)
                if isinstance(layer, TextClip):
                    created_text_clips.append(layer)
                else:
                    created_other_clips.append(layer)
            created_text_clips.append(main_text)

        result = CompositeVideoClip(final_clips)

        result.write_videofile(
            output_path,
            codec="libx264",
            audio_codec="aac",
            temp_audiofile="temp-audio.m4a",
            remove_temp=True,
            fps=clip.fps,
            logger=None,
        )

        # Cleanup
        for c in created_text_clips:
            try:
                c.close()
            except Exception:
                pass
        for c in created_other_clips:
            try:
                c.close()
            except Exception:
                pass
        try:
            result.close()
        except Exception:
            pass
        try:
            clip.close()
        except Exception:
            pass

        return True, ""
    except FileNotFoundError as e:
        # Most common on Windows: ffmpeg isn't on PATH when Whisper/MoviePy spawns it.
        try:
            ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            ffmpeg_exe = "(unknown)"
        return (
            False,
            f"{e}.\n\nffmpeg was not found on PATH. This app uses the bundled ffmpeg at:\n{ffmpeg_exe}\n\nTry restarting `streamlit run app.py` after this fix, or install ffmpeg system-wide.",
        )
    except Exception as e:
        return False, str(e)


st.set_page_config(page_title="Video Text Overlay Tool", layout="wide")
st.title("Video Text Overlay Tool")
st.markdown("Upload a video file (e.g., .mov), customize the text overlay, and preview the result.")

uploaded_file = st.file_uploader("Upload a video file", type=["mov", "mp4", "avi", "mkv"])
col1, col2 = st.columns([1, 2])

if uploaded_file is None:
    st.info("Upload a video to get started.")
    raise SystemExit

file_ext = os.path.splitext(uploaded_file.name)[1] or ".mov"
with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tfile:
    tfile.write(uploaded_file.read())
    video_path = tfile.name

with col1:
    st.subheader("Original Video")
    if file_ext.lower() == ".mov":
        st.warning("Note: .mov files might not play in the browser, but will be processed correctly.")
    st.video(video_path)

with col2:
    st.subheader("Overlay Settings")

    font_preview_placeholder = None

    use_captions = st.checkbox("Generate Captions from Audio (AI)", value=False)
    animate_in = False
    animate_from = "bottom"
    animate_duration = 0.6
    if use_captions:
        st.info("Captions are generated from audio using Whisper; first run may take longer.")
        overlay_text = None
    else:
        overlay_text = st.text_area("Overlay Text", "Sample Overlay Text\nMulti-line is supported")
        animate_in = st.checkbox("Animate text onto the screen", value=False)
        if animate_in:
            animate_from = st.selectbox("Animate From", options=["bottom", "top", "left", "right"], index=0)
            animate_duration = st.slider("Animation Duration (seconds)", 0.1, 3.0, 0.6)

    c1, c2 = st.columns(2)
    with c1:
        font_size = st.slider("Font Size", min_value=10, max_value=200, value=50)
        font_color = st.color_picker("Font Color", "#FFFFFF")
    with c2:
        font_key = st.selectbox(
            "Font Family",
            ["Arial", "Helvetica", "Courier", "Times New Roman", "Impact", "Georgia", "Verdana"],
            index=0,
        )

        b1, b2 = st.columns(2)
        with b1:
            font_bold = st.checkbox("Bold", value=False)
        with b2:
            font_italic = st.checkbox("Italic", value=False)

        custom_font_path: str | None = None
        custom_font = st.file_uploader("Custom Font (.ttf/.otf)", type=["ttf", "otf"], key="custom_font")
        if custom_font is not None:
            custom_ext = os.path.splitext(custom_font.name)[1] or ".ttf"
            with tempfile.NamedTemporaryFile(delete=False, suffix=custom_ext) as f:
                f.write(custom_font.read())
                custom_font_path = f.name

        font_style = _resolve_font_style(
            font_key=font_key,
            bold=font_bold,
            italic=font_italic,
            custom_font_path=custom_font_path,
        )

        if custom_font_path and (font_bold or font_italic):
            st.caption("Note: Bold/Italic aren't auto-derived for a custom font file. Upload the bold/italic variant as a separate font file if needed.")

        # Keep font family + preview together in the UI.
        with st.expander("Font Preview", expanded=True):
            font_preview_placeholder = st.empty()

    st.markdown("Text Style")
    stroke_width = st.slider("Outline Width", 0, 12, 2)
    stroke_color = st.color_picker("Outline Color", "#000000")
    shadow_enabled = st.checkbox("Shadow", value=True)
    shadow_color = st.color_picker("Shadow Color", "#000000")
    shadow_opacity = st.slider("Shadow Opacity", 0.0, 1.0, 0.5)
    shadow_dx = st.slider("Shadow Offset X", -20, 20, 2)
    shadow_dy = st.slider("Shadow Offset Y", -20, 20, 2)
    box_enabled = st.checkbox("Background Box", value=False)
    box_color = st.color_picker("Box Color", "#000000")
    box_opacity = st.slider("Box Opacity", 0.0, 1.0, 0.25)
    box_padding = st.slider("Box Padding", 0, 80, 16)

    # Render the preview into the placeholder that sits next to Font Family.
    if font_preview_placeholder is not None:
        preview_text = overlay_text.splitlines()[0] if isinstance(overlay_text, str) and overlay_text.strip() else "The quick brown fox 123"
        preview_img = render_font_sample(
            font_path=font_style,
            text=preview_text,
            font_size=font_size,
            text_color=font_color,
            stroke_width=stroke_width,
            stroke_color=stroke_color,
            shadow_enabled=shadow_enabled,
            shadow_color=shadow_color,
            shadow_opacity=shadow_opacity,
            shadow_dx=shadow_dx,
            shadow_dy=shadow_dy,
            box_enabled=box_enabled,
            box_color=box_color,
            box_opacity=box_opacity,
            box_padding=box_padding,
        )
        font_preview_placeholder.image(preview_img)

    position_sel = st.selectbox("Position", ["bottom", "center", "top", "left", "right"], index=1)
    preview_duration = st.slider("Preview Duration (seconds)", 1, 10, 5)

    if st.button("Generate Preview"):
        with st.spinner("Processing Preview..."):
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as out:
                output_path = out.name
            success, error = process_video_clip(
                video_path,
                output_path,
                overlay_text,
                font_size,
                font_color,
                font_style,
                position_sel,
                limit_duration=preview_duration,
                use_captions=use_captions,
                animate_in=animate_in,
                animate_from=animate_from,
                animate_duration=animate_duration,
                stroke_width=stroke_width,
                stroke_color=stroke_color,
                shadow_enabled=shadow_enabled,
                shadow_color=shadow_color,
                shadow_opacity=shadow_opacity,
                shadow_dx=shadow_dx,
                shadow_dy=shadow_dy,
                box_enabled=box_enabled,
                box_color=box_color,
                box_opacity=box_opacity,
                box_padding=box_padding,
            )
            if success:
                st.success("Preview Ready!")
                st.video(output_path)
            else:
                st.error(f"Error: {error}")

    if st.button("Process Full Video"):
        with st.spinner("Processing Full Video..."):
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as out:
                output_path = out.name
            success, error = process_video_clip(
                video_path,
                output_path,
                overlay_text,
                font_size,
                font_color,
                font_style,
                position_sel,
                limit_duration=None,
                use_captions=use_captions,
                animate_in=animate_in,
                animate_from=animate_from,
                animate_duration=animate_duration,
                stroke_width=stroke_width,
                stroke_color=stroke_color,
                shadow_enabled=shadow_enabled,
                shadow_color=shadow_color,
                shadow_opacity=shadow_opacity,
                shadow_dx=shadow_dx,
                shadow_dy=shadow_dy,
                box_enabled=box_enabled,
                box_color=box_color,
                box_opacity=box_opacity,
                box_padding=box_padding,
            )
            if success:
                st.success("Full Video Processed!")
                st.video(output_path)
                with open(output_path, "rb") as f:
                    st.download_button("Download Video", f, file_name="output_video.mp4")
            else:
                st.error(f"Error: {error}")
