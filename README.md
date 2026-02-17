# CubbonThoughts – Video Text Overlay Tool

Streamlit app + helper scripts to overlay styled text on top of a video.

It supports:
- Manual overlay text (multi-line)
- Optional slide-in animation (from top/bottom/left/right)
- Styling: font family, bold/italic variants (Windows font mapping), custom font upload, outline, shadow, background box
- Optional AI captions generated from audio (OpenAI Whisper)

## Quick start (Streamlit UI)

1) Create + activate a virtual environment

Windows (PowerShell):

`python -m venv .venv`

`./.venv/Scripts/Activate.ps1`

2) Install dependencies

`pip install streamlit moviepy pillow imageio-ffmpeg openai-whisper`

Notes:
- `openai-whisper` may also require installing PyTorch (`torch`). If installation fails, install PyTorch first (CPU or CUDA) and then re-run the Whisper install.

3) Run the app

`streamlit run app.py`

Then:
- Upload a video (`.mov`, `.mp4`, `.avi`, `.mkv`)
- Choose either manual text or **Generate Captions from Audio (AI)**
- Click **Generate Preview** (short clip) or **Process Full Video**
- Download the resulting `.mp4`

## Batch processing (script)

The script [batch_moviepy_overlay.py](batch_moviepy_overlay.py) can process all videos in a folder and write outputs to `output/`.

Default example (edit the parameters in the `__main__` block):

`python batch_moviepy_overlay.py`

By default it reads from `data/videos/` and writes `overlay_<filename>` into `output/`.

## Folder layout

- `app.py`: Streamlit UI + video processing pipeline
- `batch_moviepy_overlay.py`: batch overlay helper
- `data/videos/`: (optional) place input videos for batch processing
- `output/`: sample/produced outputs (often gitignored)

## ffmpeg: do I commit ffmpeg.exe?

No.

This project uses `imageio-ffmpeg` to locate/download an ffmpeg binary and, on Windows, `app.py` creates a small shim copy at:

- `.ffmpeg_bin/ffmpeg.exe`

That file is machine-generated and is already excluded by `.gitignore`. Committing ffmpeg binaries is usually unnecessary and can introduce repo bloat and licensing obligations.

If you prefer, you can also install ffmpeg system-wide and ensure it’s on `PATH`.

## Using Arial on Streamlit Cloud

Streamlit Community Cloud runs on Linux and typically won’t have Windows fonts like Arial installed.

You have two ways to use Arial:

1) Upload at runtime
- Use **Custom Font (.ttf/.otf)** in the UI and upload `arial.ttf`.
- For bold/italic, upload the corresponding font files (e.g., `arialbd.ttf`, `ariali.ttf`, `arialbi.ttf`).

2) Bundle fonts into the repo (auto-detected)
- Create a folder `fonts/` in the project.
- Copy your font files into it (example paths on Windows: `C:\\Windows\\Fonts\\arial.ttf`, `arialbd.ttf`, etc.).
- Commit + push.

The app will prefer `fonts/` on non-Windows so Streamlit Cloud can load them.

Important: Arial is typically proprietary. Only bundle/redistribute it if you have the rights. For public apps, consider bundling an open alternative such as Liberation Sans/Arimo instead.

## Troubleshooting

- **“ffmpeg was not found on PATH”**
	- Restart `streamlit run app.py` (the app attempts to add a shim ffmpeg to `PATH` at runtime).
	- Or install ffmpeg system-wide and ensure `ffmpeg.exe` is available on `PATH`.

- **Uploaded .mov doesn’t play in the browser**
	- Streamlit may not preview `.mov` reliably, but processing should still work. Use **Process Full Video** and download the result.

- **Invalid font `arial.ttf` / `cannot open resource` (Streamlit Cloud/Linux)**
	- Some Windows font files (like `arial.ttf`) don’t exist on Linux.
	- The app auto-falls back to common Linux fonts (DejaVu/Liberation) when available.
	- If you need a specific font, upload a `.ttf`/`.otf` using **Custom Font** in the UI.

## Git notes

- If Git asks for a GPG key when committing, commit signing is enabled in your Git/VS Code settings. To disable for this repo:
	- `git config commit.gpgsign false`
