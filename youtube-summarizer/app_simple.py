#!/usr/bin/env python3
"""
Simple Cloud-Ready YouTube Summarizer
Optimized for deployment on cloud platforms
"""

import gradio as gr
import torch
import os
import tempfile
import whisper
import yt_dlp
import logging
from datetime import datetime
import subprocess
import time

# Configure logging
logging.basicConfig(level=logging.INFO)

# Global variables
whisper_model = None
ollama_ready = False

def setup_ollama():
    """Setup Ollama service"""
    global ollama_ready
    try:
        # Start Ollama service
        subprocess.Popen(['ollama', 'serve'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(10)  # Wait for service to start
        
        # Pull model
        result = subprocess.run(['ollama', 'pull', 'llama3.2:1b'], 
                              capture_output=True, text=True, timeout=300)
        
        if result.returncode == 0:
            ollama_ready = True
            return "✅ Ollama ready"
        else:
            return f"❌ Ollama setup failed: {result.stderr}"
    except Exception as e:
        return f"❌ Ollama error: {str(e)}"

def load_whisper_model(model_size="base"):
    """Load Whisper model"""
    global whisper_model
    try:
        if whisper_model is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"
            whisper_model = whisper.load_model(model_size, device=device)
        return whisper_model
    except Exception as e:
        logging.error(f"Error loading Whisper: {e}")
        return None

def download_audio(url):
    """Download audio from video"""
    try:
        output_path = f"temp_audio_{int(time.time())}"
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': f'{output_path}.%(ext)s',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'quiet': True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
            
            # Find the downloaded file
            for ext in ['mp3', 'm4a', 'webm', 'ogg']:
                audio_file = f"{output_path}.{ext}"
                if os.path.exists(audio_file):
                    return audio_file
        return None
    except Exception as e:
        logging.error(f"Download error: {e}")
        return None

def get_video_info(url):
    """Get video information"""
    try:
        ydl_opts = {'quiet': True, 'no_warnings': True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return {
                'title': info.get('title', 'Unknown'),
                'duration': info.get('duration', 0),
                'uploader': info.get('uploader', 'Unknown'),
            }
    except Exception as e:
        logging.error(f"Info error: {e}")
        return None

def generate_summary_simple(text, title):
    """Generate summary using simple method if Ollama fails"""
    try:
        if not ollama_ready:
            # Fallback: Simple extractive summary
            sentences = text.split('. ')
            # Take first few sentences and some from middle/end
            summary_sentences = sentences[:3] + sentences[len(sentences)//2:len(sentences)//2+2] + sentences[-2:]
            return f"**Summary of: {title}**\n\n" + '. '.join(summary_sentences)
        
        # Try Ollama
        import ollama
        prompt = f"Summarize this video '{title}' in bullet points:\n\n{text[:2000]}"
        
        response = ollama.generate(
            model="llama3.2:1b",
            prompt=prompt,
            options={'temperature': 0.7, 'num_predict': 200}
        )
        
        return f"**AI Summary: {title}**\n\n{response['response']}"
        
    except Exception as e:
        # Fallback summary
        sentences = text.split('. ')[:5]
        return f"**Summary: {title}**\n\n• " + '\n• '.join(sentences)

def process_video(url, model_size, progress=gr.Progress()):
    """Main processing function"""
    if not url.strip():
        return "❌ Please enter a video URL", "", ""
    
    try:
        # Validate URL
        if not any(domain in url for domain in ['youtube.com', 'youtu.be', 'vimeo.com']):
            return "❌ Please enter a valid YouTube or Vimeo URL", "", ""
        
        # Get video info
        progress(0.1, desc="📹 Getting video info...")
        video_info = get_video_info(url)
        if not video_info:
            return "❌ Could not access video. Check URL and try again.", "", ""
        
        # Download audio
        progress(0.3, desc="⬇️ Downloading audio...")
        audio_file = download_audio(url)
        if not audio_file:
            return "❌ Could not download audio. Video might be private or restricted.", "", ""
        
        # Transcribe
        progress(0.6, desc="🎤 Transcribing (this may take a while)...")
        model = load_whisper_model(model_size)
        if not model:
            return "❌ Could not load Whisper model", "", ""
        
        result = model.transcribe(audio_file, fp16=torch.cuda.is_available())
        transcript = result['text'].strip()
        
        if not transcript:
            return "❌ Could not transcribe audio. Video might have no speech.", "", ""
        
        # Generate summary
        progress(0.9, desc="🤖 Generating summary...")
        summary = generate_summary_simple(transcript, video_info['title'])
        
        # Cleanup
        try:
            os.unlink(audio_file)
        except:
            pass
        
        progress(1.0, desc="✅ Complete!")
        
        # Format info
        duration_str = f"{video_info['duration']//60}:{video_info['duration']%60:02d}" if video_info['duration'] else "Unknown"
        info_text = f"""**📹 Video Info:**
- **Title:** {video_info['title']}
- **Duration:** {duration_str}
- **Channel:** {video_info['uploader']}
- **Processed:** {datetime.now().strftime('%Y-%m-%d %H:%M')}"""
        
        return info_text, transcript, summary
        
    except Exception as e:
        error_msg = str(e)
        logging.error(f"Processing error: {error_msg}")
        return f"❌ Error: {error_msg}", "", ""

# Setup Ollama on startup
setup_status = setup_ollama()

# Create Gradio interface
with gr.Blocks(
    title="StudyMatGen - YouTube Summarizer",
    theme=gr.themes.Soft(),
    css="""
    .gradio-container {
        max-width: 1200px !important;
    }
    .main-header {
        text-align: center;
        margin-bottom: 30px;
    }
    """
) as demo:
    
    gr.HTML("""
    <div class="main-header">
        <h1>🎥 StudyMatGen</h1>
        <h3>AI-Powered YouTube Summarizer</h3>
        <p>Transform any YouTube video into study materials with AI transcription and summarization</p>
    </div>
    """)
    
    # Show setup status
    gr.Markdown(f"**System Status:** {setup_status}")
    
    with gr.Row():
        with gr.Column(scale=2):
            url_input = gr.Textbox(
                label="🔗 YouTube Video URL",
                placeholder="https://www.youtube.com/watch?v=...",
                lines=1,
                info="Paste any YouTube or Vimeo URL here"
            )
            
            with gr.Row():
                model_select = gr.Dropdown(
                    choices=["tiny", "base", "small"],
                    value="base",
                    label="🎤 Whisper Model",
                    info="base = good quality & speed, small = better quality"
                )
                process_btn = gr.Button("🚀 Process Video", variant="primary", scale=1)
        
        with gr.Column(scale=1):
            gr.Markdown("""
            **💡 Tips:**
            - Use 'base' model for best speed/quality balance
            - Processing time depends on video length
            - Works with YouTube, Vimeo, and more
            - Free to use!
            """)
    
    with gr.Row():
        with gr.Column():
            info_output = gr.Markdown(label="📋 Video Information")
            transcript_output = gr.Textbox(
                label="📝 Full Transcript",
                lines=15,
                max_lines=25,
                show_copy_button=True
            )
        
        with gr.Column():
            summary_output = gr.Markdown(
                label="🤖 AI Summary",
                show_copy_button=True
            )
    
    # Examples
    gr.Examples(
        examples=[
            ["https://www.youtube.com/watch?v=dQw4w9WgXcQ", "base"],
            ["https://www.youtube.com/watch?v=jNQXAC9IVRw", "base"],
        ],
        inputs=[url_input, model_select],
        label="📚 Try these examples"
    )
    
    process_btn.click(
        fn=process_video,
        inputs=[url_input, model_select],
        outputs=[info_output, transcript_output, summary_output],
        show_progress=True
    )

# Launch configuration
if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0",
        server_port=int(os.environ.get("PORT", 7860)),
        share=False,
        show_error=True
    )