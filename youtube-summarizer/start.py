#!/usr/bin/env python3
"""
Quick start script for YouTube Summarizer
Checks dependencies and starts the application
"""

import sys
import subprocess
import importlib
import os
from pathlib import Path

def check_python_version():
    """Check if Python version is compatible"""
    if sys.version_info < (3, 8):
        print("❌ Python 3.8 or higher is required")
        print(f"   Current version: {sys.version}")
        return False
    print(f"✅ Python {sys.version.split()[0]} - OK")
    return True

def check_dependencies():
    """Check if required packages are installed"""
    required_packages = [
        'flask',
        'torch',
        'whisper',
        'yt_dlp',
        'ollama'
    ]
    
    missing_packages = []
    
    for package in required_packages:
        try:
            importlib.import_module(package)
            print(f"✅ {package} - OK")
        except ImportError:
            print(f"❌ {package} - Missing")
            missing_packages.append(package)
    
    if missing_packages:
        print(f"\n📦 Missing packages: {', '.join(missing_packages)}")
        print("   Run: pip install -r requirements.txt")
        return False
    
    return True

def check_ffmpeg():
    """Check if FFmpeg is available"""
    try:
        result = subprocess.run(['ffmpeg', '-version'], 
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            print("✅ FFmpeg - OK")
            return True
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    
    print("❌ FFmpeg - Not found")
    print("   Install FFmpeg: https://ffmpeg.org/download.html")
    return False

def check_ollama():
    """Check if Ollama is available"""
    try:
        import ollama
        # Try to list models to check if Ollama is running
        models = ollama.list()
        print("✅ Ollama - OK")
        
        # Check if required model is available
        model_names = [model['name'] for model in models.get('models', [])]
        if any('llama3.2' in name for name in model_names):
            print("✅ Llama3.2 model - OK")
        else:
            print("⚠️  Llama3.2 model not found")
            print("   Run: ollama pull llama3.2:3b")
        
        return True
        
    except Exception as e:
        print("❌ Ollama - Not available")
        print("   Make sure Ollama is installed and running")
        print("   Download: https://ollama.ai")
        return False

def check_gpu():
    """Check GPU availability"""
    try:
        import torch
        if torch.cuda.is_available():
            gpu_name = torch.cuda.get_device_name(0)
            print(f"🚀 GPU: {gpu_name} - Available")
            return True
        else:
            print("⚠️  GPU: Not available (CPU mode)")
            return True
    except ImportError:
        print("⚠️  PyTorch not available for GPU check")
        return True

def create_directories():
    """Create necessary directories"""
    directories = ['outputs', 'uploads', 'static/images', 'templates']
    
    for directory in directories:
        Path(directory).mkdir(parents=True, exist_ok=True)
    
    print("✅ Directories created")

def main():
    """Main startup function"""
    print("🚀 YouTube Summarizer - Startup Check")
    print("=" * 50)
    
    # Check all requirements
    checks = [
        check_python_version(),
        check_dependencies(),
        check_ffmpeg(),
        check_ollama(),
        check_gpu()
    ]
    
    # Create directories
    create_directories()
    
    print("=" * 50)
    
    if all(checks[:4]):  # First 4 checks are critical
        print("✅ All critical dependencies are ready!")
        print("\n🌐 Starting web application...")
        print("📱 Open http://localhost:5000 in your browser")
        print("\n💡 Tips:")
        print("   • Use 'turbo' model for best speed/quality balance")
        print("   • GPU acceleration will be used if available")
        print("   • Check /files page to see all generated content")
        print("\n" + "=" * 50)
        
        # Start the application
        try:
            from app import app
            app.run(debug=False, host='0.0.0.0', port=5000, use_reloader=False)
        except KeyboardInterrupt:
            print("\n👋 Goodbye!")
        except Exception as e:
            print(f"\n❌ Error starting application: {e}")
            sys.exit(1)
    else:
        print("❌ Some dependencies are missing. Please install them first.")
        print("\n📋 Quick setup:")
        print("1. pip install -r requirements.txt")
        print("2. Install FFmpeg: https://ffmpeg.org/download.html")
        print("3. Install Ollama: https://ollama.ai")
        print("4. Run: ollama pull llama3.2:3b")
        sys.exit(1)

if __name__ == '__main__':
    main()