#!/usr/bin/env python3
"""
Enhanced Command Line Interface for YouTube Summarizer
Process videos from command line with comprehensive options
"""

import argparse
import sys
import os
import tempfile
import json
from pathlib import Path
import whisper
import yt_dlp
import torch
import ollama
from datetime import datetime
from simple_summarizer import SimpleSummarizer

class CLISummarizer:
    def __init__(self, model_size="turbo", ollama_model="llama3.2:3b"):
        self.model_size = model_size
        self.ollama_model = ollama_model
        self.whisper_model = None
        
    def load_whisper_model(self):
        """Load Whisper model"""
        if self.whisper_model is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"
            print(f"Loading Whisper model: {self.model_size} on {device}")
            self.whisper_model = whisper.load_model(self.model_size, device=device)
            print("✅ Model loaded successfully!")
        return self.whisper_model
    
    def download_audio(self, url, output_path):
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
            'no_warnings': True,
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
                
                for ext in ['mp3', 'm4a', 'webm', 'ogg']:
                    audio_file = f"{output_path}.{ext}"
                    if os.path.exists(audio_file):
                        return audio_file
                return None
                
        except Exception as e:
            print(f"❌ Error downloading audio: {e}")
            return None
    
    def get_video_info(self, url):
        """Get video information"""
        ydl_opts = {'quiet': True, 'no_warnings': True}
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                return {
                    'title': info.get('title', 'Unknown'),
                    'duration': info.get('duration', 0),
                    'uploader': info.get('uploader', 'Unknown'),
                    'view_count': info.get('view_count', 0),
                }
        except Exception as e:
            print(f"❌ Error getting video info: {e}")
            return None
    
    def transcribe_audio(self, audio_file):
        """Transcribe audio file"""
        print("🎤 Transcribing audio...")
        model = self.load_whisper_model()
        
        result = model.transcribe(
            audio_file,
            word_timestamps=True,
            verbose=False,
            fp16=torch.cuda.is_available()
        )
        
        print("✅ Transcription complete!")
        return result
    
    def generate_summary(self, text, title, summary_type="comprehensive"):
        """Generate summary using SimpleSummarizer"""
        print(f"🤖 Generating {summary_type} summary...")
        
        try:
            summarizer = SimpleSummarizer(self.ollama_model)
            
            if summary_type == "quick":
                summary = summarizer.quick_summary(text)
            elif summary_type == "detailed":
                summary = summarizer.detailed_summary(text)
            elif summary_type == "key_points":
                result = summarizer.summarize_with_key_points(text)
                summary = f"SUMMARY:\n{result['summary']}\n\nKEY POINTS:\n{result['key_points']}"
            else:  # comprehensive
                summary = summarizer.summarize_text(text, max_length=800)
            
            print("✅ Summary generated!")
            return summary
            
        except Exception as e:
            print(f"❌ Error generating summary: {e}")
            return None
    
    def generate_study_material(self, text, title, sections=None):
        """Generate comprehensive study material"""
        print("📚 Generating study material...")
        
        try:
            # Import here to avoid circular imports
            from app import EContentGenerator, generate_selective_study_material, format_selective_study_material
            
            content_generator = EContentGenerator(self.ollama_model)
            
            # Default sections if none provided
            if not sections:
                sections = ['overview', 'concept_explanation', 'examples', 'key_takeaways', 'practice_exercises']
            
            # Generate sections
            generated_sections = generate_selective_study_material(
                content_generator, text, title, sections
            )
            
            # Format into complete study material
            study_material = format_selective_study_material(generated_sections, title)
            
            print("✅ Study material generated!")
            return study_material
            
        except Exception as e:
            print(f"❌ Error generating study material: {e}")
            return None
    
    def save_results(self, video_info, transcript_result, summary, output_dir, study_material=None):
        """Save results to files"""
        output_dir = Path(output_dir)
        output_dir.mkdir(exist_ok=True)
        
        # Clean title for filename
        title = video_info['title']
        safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).strip()
        safe_title = safe_title[:30]
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_name = f"{safe_title}_{timestamp}"
        
        files_created = []
        
        # 1. Transcript file
        txt_file = output_dir / f"{base_name}_transcript.txt"
        with open(txt_file, 'w', encoding='utf-8') as f:
            f.write(f"Title: {video_info['title']}\n")
            f.write(f"Duration: {video_info['duration']//60}:{video_info['duration']%60:02d}\n")
            f.write(f"Language: {transcript_result['language']}\n")
            f.write("-" * 50 + "\n\n")
            f.write("TRANSCRIPT:\n")
            f.write(transcript_result['text'].strip())
        files_created.append(str(txt_file))
        
        # 2. Summary file
        if summary:
            summary_file = output_dir / f"{base_name}_summary.txt"
            with open(summary_file, 'w', encoding='utf-8') as f:
                f.write(f"Title: {video_info['title']}\n")
                f.write(f"Duration: {video_info['duration']//60}:{video_info['duration']%60:02d}\n")
                f.write("-" * 50 + "\n\n")
                f.write("SUMMARY:\n")
                f.write(summary)
            files_created.append(str(summary_file))
        
        # 3. Study Material file
        if study_material:
            study_file = output_dir / f"{base_name}_study_material.md"
            with open(study_file, 'w', encoding='utf-8') as f:
                f.write(study_material)
            files_created.append(str(study_file))
        
        # 4. SRT file
        srt_file = output_dir / f"{base_name}.srt"
        with open(srt_file, 'w', encoding='utf-8') as f:
            for i, segment in enumerate(transcript_result['segments'], 1):
                start = self.format_srt_time(segment['start'])
                end = self.format_srt_time(segment['end'])
                text = segment['text'].strip()
                f.write(f"{i}\n{start} --> {end}\n{text}\n\n")
        files_created.append(str(srt_file))
        
        # 5. JSON file
        json_file = output_dir / f"{base_name}_complete.json"
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump({
                'video_info': video_info,
                'transcript': transcript_result,
                'summary': summary,
                'study_material': study_material,
                'timestamp': datetime.now().isoformat()
            }, f, indent=2, ensure_ascii=False)
        files_created.append(str(json_file))
        
        return files_created
    
    def format_srt_time(self, seconds):
        """Convert seconds to SRT timestamp format"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millisecs = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millisecs:03d}"
    
    def process_video(self, url, output_dir="outputs", content_type="summary", summary_type="comprehensive", study_sections=None):
        """Process a video from URL with enhanced options"""
        print(f"🎥 Processing video: {url}")
        
        # Get video info
        print("📋 Getting video information...")
        video_info = self.get_video_info(url)
        if not video_info:
            print("❌ Failed to get video information")
            return False
        
        print(f"📺 Title: {video_info['title']}")
        print(f"⏱️  Duration: {video_info['duration']//60}:{video_info['duration']%60:02d}")
        
        # Download audio
        print("⬇️  Downloading audio...")
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp_file:
            temp_path = tmp_file.name.replace('.mp3', '')
        
        audio_file = self.download_audio(url, temp_path)
        if not audio_file:
            print("❌ Failed to download audio")
            return False
        
        print("✅ Audio downloaded successfully!")
        
        try:
            # Transcribe
            transcript_result = self.transcribe_audio(audio_file)
            
            # Generate content based on type
            summary = None
            study_material = None
            
            if content_type == "summary":
                summary = self.generate_summary(transcript_result['text'], video_info['title'], summary_type)
            elif content_type == "study_material":
                study_material = self.generate_study_material(transcript_result['text'], video_info['title'], study_sections)
            elif content_type == "both":
                summary = self.generate_summary(transcript_result['text'], video_info['title'], summary_type)
                study_material = self.generate_study_material(transcript_result['text'], video_info['title'], study_sections)
            
            # Save results
            print("💾 Saving results...")
            files_created = self.save_results(video_info, transcript_result, summary, output_dir, study_material)
            
            print("✅ Processing complete!")
            print("\n📁 Files created:")
            for file_path in files_created:
                print(f"   • {file_path}")
            
            return True
            
        finally:
            # Clean up
            try:
                os.unlink(audio_file)
            except:
                pass

def main():
    parser = argparse.ArgumentParser(description='Enhanced Video Summarizer CLI')
    parser.add_argument('url', help='Video URL (YouTube, Vimeo, etc.)')
    parser.add_argument('--model', default='turbo', 
                       choices=['tiny', 'base', 'small', 'medium', 'turbo', 'large'],
                       help='Whisper model size (default: turbo)')
    parser.add_argument('--ollama-model', default='llama3.2:3b',
                       help='Ollama model for content generation (default: llama3.2:3b)')
    parser.add_argument('--output-dir', default='outputs',
                       help='Output directory (default: outputs)')
    parser.add_argument('--content-type', default='summary',
                       choices=['summary', 'study_material', 'both'],
                       help='Type of content to generate (default: summary)')
    parser.add_argument('--summary-type', default='comprehensive',
                       choices=['quick', 'comprehensive', 'detailed', 'key_points'],
                       help='Type of summary to generate (default: comprehensive)')
    parser.add_argument('--study-sections', nargs='*',
                       choices=['overview', 'concept_explanation', 'examples', 'case_studies', 
                               'key_takeaways', 'practice_exercises', 'quiz_questions'],
                       help='Study material sections to generate')
    parser.add_argument('--no-content', action='store_true',
                       help='Skip content generation (transcript only)')
    
    args = parser.parse_args()
    
    # Validate URL
    supported_domains = ['youtube.com', 'youtu.be', 'vimeo.com', 'dailymotion.com', 'twitch.tv']
    if not any(domain in args.url for domain in supported_domains):
        print("❌ Please provide a valid video URL (YouTube, Vimeo, etc.)")
        sys.exit(1)
    
    # Check GPU
    if torch.cuda.is_available():
        gpu_name = torch.cuda.get_device_name(0)
        print(f"🚀 GPU detected: {gpu_name}")
    else:
        print("⚠️  No GPU detected, using CPU mode")
    
    # Create summarizer and process
    summarizer = CLISummarizer(args.model, args.ollama_model)
    
    # Determine content type
    content_type = "transcript_only" if args.no_content else args.content_type
    
    success = summarizer.process_video(
        args.url, 
        args.output_dir, 
        content_type=content_type,
        summary_type=args.summary_type,
        study_sections=args.study_sections
    )
    
    if success:
        print("\n🎉 All done! Check the output directory for your files.")
        print(f"\n💡 Usage examples:")
        print(f"   • Quick summary: --content-type summary --summary-type quick")
        print(f"   • Study material: --content-type study_material --study-sections overview examples key_takeaways")
        print(f"   • Both: --content-type both")
        sys.exit(0)
    else:
        print("\n❌ Processing failed!")
        sys.exit(1)

if __name__ == '__main__':
    main()