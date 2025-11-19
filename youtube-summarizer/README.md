# Video Summarizer

A complete video processing system that downloads videos from various platforms, transcribes them using OpenAI Whisper, and generates AI-powered summaries and study materials using Ollama.

## 🚀 Features

- **🎥 Video Processing**: Download and process videos from multiple platforms
- **🎤 AI Transcription**: High-quality transcription using OpenAI Whisper
- **📚 Study Material Generation**: Comprehensive educational content with multiple sections
- **📝 AI Summarization**: Quick summaries using Ollama
- **⚡ GPU Acceleration**: Automatic GPU detection for faster processing
- **🌐 Web Interface**: User-friendly web interface
- **💻 CLI Tool**: Command-line interface for batch processing
- **📄 Multiple Formats**: Export as TXT, SRT, Markdown, and JSON

### Study Material Includes:
- **Overview** - Topic description and importance
- **Learning Outcomes** - What students will achieve
- **Concept Explanations** - Detailed content breakdown
- **Examples** - Real-world applications
- **Key Takeaways** - Essential points to remember
- **Practice Exercises** - Hands-on activities
- **Quiz Questions** - Self-assessment tools

## 📋 Prerequisites

1. **Python 3.8+**
2. **FFmpeg** (for audio processing)
3. **Ollama** (for AI summarization)

## 🛠️ Installation

### 1. Install Python Dependencies
```bash
pip install -r requirements.txt
```

### 2. Install FFmpeg
- **Windows**: Download from [FFmpeg website](https://ffmpeg.org/download.html)
- **macOS**: `brew install ffmpeg`
- **Linux**: `sudo apt install ffmpeg`

### 3. Install and Setup Ollama
- Download from [Ollama website](https://ollama.ai)
- Pull the required model:
```bash
ollama pull llama3.2:3b
```

## 🎯 Usage

### Web Interface

1. **Start the application:**
```bash
python app.py
```

2. **Open your browser:**
```
http://localhost:5000
```

3. **Process a video:**
   - Enter video URL (YouTube, Vimeo, etc.)
   - Select Whisper model (turbo recommended)
   - Choose content type:
     - **Quick Summary**: Brief overview
     - **Complete Study Material**: Comprehensive educational content
   - Click "Process Video"
   - Download results when complete

### Command Line Interface

**Basic usage:**
```bash
python cli_summarizer.py "https://www.youtube.com/watch?v=VIDEO_ID"
```

**Advanced options:**
```bash
# Use different Whisper model
python cli_summarizer.py "URL" --model base

# Use different Ollama model
python cli_summarizer.py "URL" --ollama-model llama2:latest

# Skip summary generation (transcript only)
python cli_summarizer.py "URL" --no-summary

# Custom output directory
python cli_summarizer.py "URL" --output-dir my_outputs
```

## ⚙️ Configuration

### Whisper Models
Choose based on your needs:
- **tiny**: Fastest, lower quality
- **base**: Good balance
- **small**: Better quality
- **medium**: High quality
- **turbo**: Recommended - Fast & accurate
- **large**: Best quality, slower

### GPU Support
The system automatically detects and uses GPU acceleration when available:
- NVIDIA GPUs with CUDA support
- Significantly faster transcription
- Automatic memory management

## 📁 Output Files

For each processed video, you'll get:

1. **`*_transcript.txt`**: Full transcript
2. **`*_summary.txt`**: AI-generated summary (if summary mode)
3. **`*_study_material.md`**: Complete educational content (if study material mode)
4. **`*.srt`**: Subtitle file with timestamps
5. **`*_complete.json`**: Complete data in JSON format

## 🏗️ Project Structure

```
youtube-summarizer/
├── app.py                 # Web application
├── cli_summarizer.py      # Command-line tool
├── requirements.txt       # Python dependencies
├── templates/            # Web interface templates
│   ├── base.html
│   ├── index.html
│   └── files.html
├── outputs/              # Generated output files
├── uploads/              # Temporary uploads
└── static/               # Static web assets
```

## 🔧 Troubleshooting

### Common Issues:

1. **"No module named 'whisper'"**
   ```bash
   pip install openai-whisper
   ```

2. **"FFmpeg not found"**
   - Install FFmpeg and ensure it's in your PATH

3. **"Ollama connection error"**
   - Make sure Ollama is running: `ollama serve`
   - Pull the required model: `ollama pull llama3.2:3b`

4. **GPU not detected**
   - Install CUDA-compatible PyTorch
   - Check GPU drivers

### Performance Tips:

- Use GPU acceleration for faster processing
- Choose appropriate Whisper model for your needs
- For long videos, consider using smaller models first
- Ensure sufficient disk space for temporary files

## 🌐 API Endpoints

### Web API:
- `POST /process`: Start video processing
- `GET /status/<job_id>`: Check processing status
- `GET /download/<filename>`: Download result files
- `GET /files`: List all processed files
- `GET /gpu-status`: Check GPU availability
- `GET /health`: Health check

## 📄 License

This project uses several open-source libraries:
- OpenAI Whisper: MIT License
- yt-dlp: Unlicense
- Flask: BSD License
- Ollama: MIT License

## 🤝 Contributing

Feel free to submit issues and enhancement requests!

## 🎉 Getting Started

1. Clone or download this project
2. Install dependencies: `pip install -r requirements.txt`
3. Install FFmpeg and Ollama
4. Run: `python app.py`
5. Open http://localhost:5000
6. Paste a YouTube URL and start processing!

---

**Happy Learning! 🎓**