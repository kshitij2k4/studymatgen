#!/usr/bin/env python3
"""
Hugging Face Spaces version of YouTube Summarizer
Optimized for Gradio interface
"""

import gradio as gr
import torch
import os
import tempfile
import whisper
import yt_dlp
import ollama
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO)

# Global variables
whisper_model = None

def load_whisper_model(model_size="base"):
    """Load Whisper model"""
    global whisper_model
    if whisper_model is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"Loading Whisper model: {model_size} on {device}")
        whisper_model = whisper.load_model(model_size, device=device)
    return whisper_model

def download_audio(url):
    """Download audio from video"""
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': 'temp_audio.%(ext)s',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'quiet': True,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
            
            for ext in ['mp3', 'm4a', 'webm']:
                audio_file = f"temp_audio.{ext}"
                if os.path.exists(audio_file):
                    return audio_file
        return None
    except Exception as e:
        return None

def get_video_info(url):
    """Get video information"""
    try:
        ydl_opts = {'quiet': True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return {
                'title': info.get('title', 'Unknown'),
                'duration': info.get('duration', 0),
                'uploader': info.get('uploader', 'Unknown'),
            }
    except:
        return None

def generate_summary(text, title):
    """Generate summary using Ollama"""
    try:
        prompt = f"""Summarize this video content about "{title}":

{text[:3000]}...

Create a clear summary with:
**Main Topic:** [What this is about]

**Key Points:**
• [Point 1]
• [Point 2] 
• [Point 3]
• [Point 4]

**Key Takeaways:**
[Main conclusions]"""

        response = ollama.generate(
            model="llama3.2:1b",  # Use smaller model for HF Spaces
            prompt=prompt,
            options={'temperature': 0.7}
        )
        
        return response['response']
    except Exception as e:
        return f"Summary generation failed: {str(e)}"

def process_video(url, model_size, progress=gr.Progress()):
    """Main processing function"""
    if not url:
        return "Please enter a video URL", "", ""
    
    try:
        # Get video info
        progress(0.1, desc="Getting video info...")
        video_info = get_video_info(url)
        if not video_info:
            return "Could not get video information", "", ""
        
        # Download audio
        progress(0.3, desc="Downloading audio...")
        audio_file = download_audio(url)
        if not audio_file:
            return "Could not download audio", "", ""
        
        # Transcribe
        progress(0.6, desc="Transcribing...")
        model = load_whisper_model(model_size)
        result = model.transcribe(audio_file, fp16=torch.cuda.is_available())
        
        transcript = result['text']
        
        # Generate summary
        progress(0.9, desc="Generating summary...")
        summary = generate_summary(transcript, video_info['title'])
        
        # Cleanup
        try:
            os.unlink(audio_file)
        except:
            pass
        
        progress(1.0, desc="Complete!")
        
        return (
            f"**Title:** {video_info['title']}\n**Duration:** {video_info['duration']//60}:{video_info['duration']%60:02d}",
            transcript,
            summary
        )
        
    except Exception as e:
        return f"Error: {str(e)}", "", ""

# Create Gradio interface
with gr.Blocks(title="YouTube Summarizer", theme=gr.themes.Soft()) as demo:
    gr.Markdown("# 🎥 YouTube Summarizer")
    gr.Markdown("Enter a YouTube URL to get AI-powered transcription and summary")
    
    with gr.Row():
        with gr.Column():
            url_input = gr.Textbox(
                label="Video URL",
                placeholder="https://www.youtube.com/watch?v=...",
                lines=1
            )
            model_select = gr.Dropdown(
                choices=["tiny", "base", "small"],
                value="base",
                label="Whisper Model"
            )
            process_btn = gr.Button("Process Video", variant="primary")
    
    with gr.Row():
        with gr.Column():
            info_output = gr.Markdown(label="Video Info")
            transcript_output = gr.Textbox(
                label="Transcript",
                lines=10,
                max_lines=20
            )
        with gr.Column():
            summary_output = gr.Markdown(label="AI Summary")
    
    process_btn.click(
        fn=process_video,
        inputs=[url_input, model_select],
        outputs=[info_output, transcript_output, summary_output]
    )

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860)