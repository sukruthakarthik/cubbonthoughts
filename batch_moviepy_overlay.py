# batch_moviepy_overlay.py
"""
Batch process videos to add styled text overlay using MoviePy.
"""
import os
from moviepy import VideoFileClip, TextClip, CompositeVideoClip

def add_text_overlay(input_path, output_path, text, font='arial.ttf', fontsize=48, color='white', position=('center', 'bottom')):
    video = VideoFileClip(input_path)
    # Ensure text is centered by using 'caption' method if needed, or rely on composite positioning
    # For simple overlays, let's try explicitly setting the position in the composite clip call if possible, 
    # but with_position on the clip itself is the standard way.
    # Let's try adding a margin or using 'caption' method which is more robust for centering.
    # We'll use method='caption' and set the width to the video width to ensure centering.
    
    txt_clip = TextClip(
        text=text, 
        font_size=fontsize, 
        font=font, 
        color=color, 
        method='caption',
        size=(video.w, None),  # Width of video, auto height
        text_align='center'
    )
    txt_clip = txt_clip.with_position(position).with_duration(video.duration)
    result = CompositeVideoClip([video, txt_clip])
    result.write_videofile(output_path, codec='libx264', audio_codec='aac')
    video.close()
    txt_clip.close()
    result.close()

def batch_process_videos(input_dir, output_dir, text, font='arial.ttf', fontsize=48, color='white', position=('center', 'bottom')):
    os.makedirs(output_dir, exist_ok=True)
    for filename in os.listdir(input_dir):
        if filename.lower().endswith(('.mp4', '.mov', '.avi', '.mkv')):
            input_path = os.path.join(input_dir, filename)
            output_path = os.path.join(output_dir, f"overlay_{filename}")
            print(f"Processing {filename}...")
            add_text_overlay(input_path, output_path, text, font, fontsize, color, position)
    print("Batch processing complete.")

if __name__ == "__main__":
    # Example usage
    batch_process_videos(
        input_dir="data/videos",  # Folder with input videos
        output_dir="output", # Folder to save processed videos
        text="Sample Overlay Text macha mine",
        font="arial.ttf",
        fontsize=48,
        color="white",
        position="center"
    )
