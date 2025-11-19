#!/usr/bin/env python3
"""
Ultra-simple test version for Render
"""

from flask import Flask
import os

app = Flask(__name__)

@app.route('/')
def hello():
    return '''
    <h1>🎥 StudyMatGen is Live!</h1>
    <p>Your YouTube Summarizer is successfully deployed on Render!</p>
    <p>This is a test version. The full app will be available soon.</p>
    <style>
        body { font-family: Arial, sans-serif; text-align: center; margin-top: 100px; }
        h1 { color: #007bff; }
    </style>
    '''

@app.route('/health')
def health():
    return {'status': 'healthy'}

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)