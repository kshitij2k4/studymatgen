#!/usr/bin/env python3
"""
Simplified YouTube Summarizer for Render deployment
Transcription only (no AI summarization to avoid Ollama dependency)
"""

from flask import Flask, render_template, request, jsonify, send_file
import torch
import os
import tempfile
import whisper
import yt_dlp
from datetime import datetime
from pathlib import Path
import threading
import uuid
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)

app = Flask(__name__, static_folder='static', static_url_path='/static')

# Global variables
processing_jobs = {}
whisper_model = None

# Configuration
OUTPUT_FOLDER = 'outputs'
Path(OUTPUT_FOLDER).mkdir(exist_ok=True)

class ProcessingJob:
    def __init__(self, job_id, url, model_size="base"):
        self.job_id = job_id
        self.url = url
        self.model_size = model_size
        self.status = "starting"
        self.progress = 0
        self.result = None
        self.error = None
        self.video_info = None
        self.transcript = None

def load_whisper_model(model_size="base"):
    """Load Whisper model"""
    global whisper_model
    if whisper_model is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"Loading Whisper model: {model_size} on {device}")
        whisper_model = whisper.load_model(model_size, device=device)
    return whisper_model

def download_audio(url, output_path):
    """Download audio from video"""
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
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
            
            for ext in ['mp3', 'm4a', 'webm']:
                audio_file = f"{output_path}.{ext}"
                if os.path.exists(audio_file):
                    return audio_file
        return None
    except Exception as e:
        logging.error(f"Error downloading audio: {e}")
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
                'thumbnail': info.get('thumbnail', ''),
                'view_count': info.get('view_count', 0),
            }
    except Exception as e:
        return None

def process_video_worker(job_id):
    """Background worker for video processing"""
    job = processing_jobs[job_id]
    
    try:
        # Get video info
        job.status = "getting_info"
        job.progress = 10
        
        job.video_info = get_video_info(job.url)
        if not job.video_info:
            raise Exception("Could not get video information")
        
        # Download audio
        job.status = "downloading"
        job.progress = 30
        
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp_file:
            temp_path = tmp_file.name.replace('.mp3', '')
        
        audio_file = download_audio(job.url, temp_path)
        if not audio_file:
            raise Exception("Could not download audio")
        
        # Transcribe
        job.status = "transcribing"
        job.progress = 60
        
        model = load_whisper_model(job.model_size)
        result = model.transcribe(audio_file, fp16=False)  # Use fp16=False for CPU
        
        job.transcript = result['text']
        
        # Save results
        job.status = "saving"
        job.progress = 90
        
        # Save transcript
        safe_title = "".join(c for c in job.video_info['title'] if c.isalnum() or c in (' ', '-', '_')).strip()[:30]
        filename = f"{safe_title}_{job_id}_transcript.txt"
        filepath = Path(OUTPUT_FOLDER) / filename
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(f"Title: {job.video_info['title']}\n")
            f.write(f"Duration: {job.video_info['duration']//60}:{job.video_info['duration']%60:02d}\n")
            f.write("-" * 50 + "\n\n")
            f.write(job.transcript)
        
        job.result = {
            'transcript': job.transcript,
            'language': result['language'],
            'filename': filename
        }
        
        # Clean up
        try:
            os.unlink(audio_file)
        except:
            pass
        
        job.status = "completed"
        job.progress = 100
        
    except Exception as e:
        job.status = "error"
        job.error = str(e)
        job.progress = 0

@app.route('/')
def index():
    """Main page"""
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>StudyMatGen - YouTube Transcriber</title>
        <style>
            body { font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }
            .container { background: #f5f5f5; padding: 20px; border-radius: 10px; }
            input[type="url"] { width: 100%; padding: 10px; margin: 10px 0; }
            button { background: #007bff; color: white; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; }
            button:hover { background: #0056b3; }
            .result { margin-top: 20px; padding: 15px; background: white; border-radius: 5px; }
            .progress { width: 100%; height: 20px; background: #ddd; border-radius: 10px; overflow: hidden; }
            .progress-bar { height: 100%; background: #28a745; transition: width 0.3s; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🎥 StudyMatGen - YouTube Transcriber</h1>
            <p>Enter a YouTube URL to get AI-powered transcription</p>
            
            <input type="url" id="videoUrl" placeholder="https://www.youtube.com/watch?v=..." />
            <select id="modelSize">
                <option value="tiny">Tiny (Fastest)</option>
                <option value="base" selected>Base (Recommended)</option>
                <option value="small">Small (Better Quality)</option>
            </select>
            <button onclick="processVideo()">Process Video</button>
            
            <div id="result" class="result" style="display:none;">
                <div id="progress" class="progress">
                    <div id="progressBar" class="progress-bar" style="width: 0%"></div>
                </div>
                <div id="status"></div>
                <div id="output"></div>
            </div>
        </div>
        
        <script>
            let currentJobId = null;
            
            function processVideo() {
                const url = document.getElementById('videoUrl').value;
                const model = document.getElementById('modelSize').value;
                
                if (!url) {
                    alert('Please enter a video URL');
                    return;
                }
                
                fetch('/process', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({url: url, model: model})
                })
                .then(response => response.json())
                .then(data => {
                    if (data.job_id) {
                        currentJobId = data.job_id;
                        document.getElementById('result').style.display = 'block';
                        checkStatus();
                    } else {
                        alert('Error: ' + data.error);
                    }
                });
            }
            
            function checkStatus() {
                if (!currentJobId) return;
                
                fetch('/status/' + currentJobId)
                .then(response => response.json())
                .then(data => {
                    document.getElementById('progressBar').style.width = data.progress + '%';
                    document.getElementById('status').innerHTML = 'Status: ' + data.status + ' (' + data.progress + '%)';
                    
                    if (data.status === 'completed') {
                        document.getElementById('output').innerHTML = 
                            '<h3>✅ Transcription Complete!</h3>' +
                            '<p><strong>Title:</strong> ' + data.video_info.title + '</p>' +
                            '<textarea style="width:100%;height:300px;">' + data.result.transcript + '</textarea>' +
                            '<p><a href="/download/' + data.result.filename + '">Download Transcript</a></p>';
                    } else if (data.status === 'error') {
                        document.getElementById('output').innerHTML = '<p style="color:red;">Error: ' + data.error + '</p>';
                    } else {
                        setTimeout(checkStatus, 2000);
                    }
                });
            }
        </script>
    </body>
    </html>
    '''

@app.route('/process', methods=['POST'])
def start_processing():
    """Start video processing"""
    data = request.json
    url = data.get('url', '').strip()
    model_size = data.get('model', 'base')
    
    if not url:
        return jsonify({'error': 'URL is required'}), 400
    
    # Create job
    job_id = str(uuid.uuid4())[:8]
    job = ProcessingJob(job_id, url, model_size)
    processing_jobs[job_id] = job
    
    # Start background worker
    thread = threading.Thread(target=process_video_worker, args=(job_id,))
    thread.daemon = True
    thread.start()
    
    return jsonify({'job_id': job_id})

@app.route('/status/<job_id>')
def get_status(job_id):
    """Get processing status"""
    job = processing_jobs.get(job_id)
    if not job:
        return jsonify({'error': 'Job not found'}), 404
    
    response = {
        'status': job.status,
        'progress': job.progress,
        'video_info': job.video_info,
    }
    
    if job.status == 'completed' and job.result:
        response['result'] = job.result
    elif job.status == 'error':
        response['error'] = job.error
    
    return jsonify(response)

@app.route('/download/<filename>')
def download_file(filename):
    """Download result file"""
    file_path = Path(OUTPUT_FOLDER) / filename
    if file_path.exists():
        return send_file(file_path, as_attachment=True)
    return "File not found", 404

@app.route('/health')
def health():
    """Health check"""
    return jsonify({'status': 'healthy'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"🚀 Starting StudyMatGen on port {port}")
    app.run(debug=False, host='0.0.0.0', port=port)