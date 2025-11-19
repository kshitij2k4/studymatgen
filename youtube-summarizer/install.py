#!/usr/bin/env python3
"""
Installation script for YouTube Summarizer
Installs all required dependencies and sets up the environment
"""

import subprocess
import sys
import os
import platform

def run_command(command, description):
    """Run a command and handle errors"""
    print(f"📦 {description}...")
    try:
        result = subprocess.run(command, shell=True, check=True, 
                              capture_output=True, text=True)
        print(f"✅ {description} - Success")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {description} - Failed")
        print(f"   Error: {e.stderr}")
        return False

def install_python_packages():
    """Install Python packages from requirements.txt"""
    return run_command(
        f"{sys.executable} -m pip install -r requirements.txt",
        "Installing Python packages"
    )

def check_ffmpeg():
    """Check if FFmpeg is installed"""
    try:
        subprocess.run(['ffmpeg', '-version'], 
                      capture_output=True, check=True)
        print("✅ FFmpeg is already installed")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("❌ FFmpeg not found")
        return False

def install_ffmpeg():
    """Provide FFmpeg installation instructions"""
    system = platform.system().lower()
    
    print("\n📋 FFmpeg Installation Instructions:")
    
    if system == "windows":
        print("1. Download FFmpeg from: https://ffmpeg.org/download.html")
        print("2. Extract to a folder (e.g., C:\\ffmpeg)")
        print("3. Add C:\\ffmpeg\\bin to your PATH environment variable")
        print("4. Restart your command prompt")
    elif system == "darwin":  # macOS
        print("Run: brew install ffmpeg")
        print("(Install Homebrew first if you don't have it: https://brew.sh)")
    else:  # Linux
        print("Ubuntu/Debian: sudo apt update && sudo apt install ffmpeg")
        print("CentOS/RHEL: sudo yum install ffmpeg")
        print("Arch: sudo pacman -S ffmpeg")

def check_ollama():
    """Check if Ollama is installed"""
    try:
        subprocess.run(['ollama', '--version'], 
                      capture_output=True, check=True)
        print("✅ Ollama is already installed")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("❌ Ollama not found")
        return False

def install_ollama():
    """Provide Ollama installation instructions"""
    print("\n📋 Ollama Installation Instructions:")
    print("1. Download Ollama from: https://ollama.ai")
    print("2. Install the application")
    print("3. Run: ollama pull llama3.2:3b")
    print("4. Make sure Ollama is running in the background")

def main():
    """Main installation function"""
    print("🚀 YouTube Summarizer - Installation Script")
    print("=" * 50)
    
    # Install Python packages
    if not install_python_packages():
        print("❌ Failed to install Python packages")
        sys.exit(1)
    
    # Check FFmpeg
    if not check_ffmpeg():
        install_ffmpeg()
        ffmpeg_ok = False
    else:
        ffmpeg_ok = True
    
    # Check Ollama
    if not check_ollama():
        install_ollama()
        ollama_ok = False
    else:
        ollama_ok = True
    
    print("=" * 50)
    
    if ffmpeg_ok and ollama_ok:
        print("✅ Installation complete!")
        print("\n🚀 You can now run the application:")
        print("   python start.py")
        print("\n💡 Or use the CLI:")
        print("   python cli_summarizer.py 'https://youtube.com/watch?v=...'")
    else:
        print("⚠️  Installation partially complete")
        print("\n📋 Next steps:")
        if not ffmpeg_ok:
            print("   • Install FFmpeg (see instructions above)")
        if not ollama_ok:
            print("   • Install Ollama (see instructions above)")
        print("\n   Then run: python start.py")

if __name__ == '__main__':
    main()