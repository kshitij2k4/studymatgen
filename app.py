#!/usr/bin/env python3
"""
YouTube Summarizer - Complete Video Processing System
Downloads videos, transcribes with Whisper, and generates AI summaries/study materials
"""

from flask import Flask, render_template, request, jsonify, send_file
import torch
import os
import tempfile
import json
import whisper
import yt_dlp
from datetime import datetime
from pathlib import Path
import threading
import uuid
import ollama
import logging
from typing import Optional, List, Dict
import pdfplumber
import fitz
import io
from PIL import Image
import shutil
from werkzeug.utils import secure_filename
import markdown
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image as RLImage
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
import re

# Configure logging
logging.basicConfig(level=logging.INFO)

# Suppress CUDA warnings
import warnings
warnings.filterwarnings("ignore", message=".*CUDA toolkit.*")
warnings.filterwarnings("ignore", message=".*Triton kernels.*")

app = Flask(__name__, static_folder='static', static_url_path='/static')

# Custom template filter
@app.template_filter('timestamp_to_date')
def timestamp_to_date(timestamp):
    return datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M')

# Global variables
processing_jobs = {}
whisper_model = None

# Configuration
OUTPUT_FOLDER = 'outputs'
UPLOAD_FOLDER = 'uploads'
STATIC_IMAGES_FOLDER = 'static/images'

# Create directories
Path(OUTPUT_FOLDER).mkdir(exist_ok=True)
Path(UPLOAD_FOLDER).mkdir(exist_ok=True)
Path(STATIC_IMAGES_FOLDER).mkdir(parents=True, exist_ok=True)

# File upload configuration
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max
ALLOWED_EXTENSIONS = {'pdf'}
ALLOWED_IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp'}

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

class ProcessingJob:
    def __init__(self, job_id, url, model_size="turbo", content_type="summary", pdf_file=None, selected_sections=None):
        self.job_id = job_id
        self.url = url
        self.model_size = model_size
        self.content_type = content_type
        self.pdf_file = pdf_file
        self.selected_sections = selected_sections or []
        self.status = "starting"
        self.progress = 0
        self.result = None
        self.error = None
        self.video_info = None
        self.transcript = None
        self.summary = None
        self.study_material = None
        self.extracted_images = []
        self.files = {}

class ImageAnalyzer:
    """Analyzes images and determines their relevance to educational content"""
    
    def __init__(self, model_name: str = "llama3.2:3b"):
        self.model_name = model_name
        self.supported_formats = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}
    
    def analyze_image_content(self, image_path: str, topic_context: str = "") -> Dict[str, str]:
        """Analyze image content and determine its educational relevance"""
        try:
            filename = os.path.basename(image_path).lower()
            
            image_info = {
                'path': image_path,
                'filename': os.path.basename(image_path),
                'description': self._generate_description_from_filename(filename),
                'relevance_score': self._calculate_relevance_score(filename, topic_context),
                'suggested_placement': self._suggest_placement(filename),
                'alt_text': self._generate_alt_text(filename)
            }
            
            return image_info
            
        except Exception as e:
            logging.error(f"Error analyzing image {image_path}: {e}")
            return {
                'path': image_path,
                'filename': os.path.basename(image_path),
                'description': 'Educational illustration',
                'relevance_score': 0.5,
                'suggested_placement': 'concept_explanation',
                'alt_text': f'Educational image: {os.path.basename(image_path)}'
            }
    
    def _generate_description_from_filename(self, filename: str) -> str:
        """Generate description based on filename keywords"""
        keywords = {
            'diagram': 'A diagram illustrating key concepts',
            'chart': 'A chart showing data relationships',
            'graph': 'A graph displaying quantitative information',
            'flowchart': 'A flowchart showing process steps',
            'model': 'A model demonstrating the concept',
            'example': 'An example illustration',
            'process': 'A process visualization',
            'structure': 'A structural representation',
            'algorithm': 'An algorithm visualization',
            'network': 'A network diagram',
            'architecture': 'An architectural diagram',
            'comparison': 'A comparison illustration',
            'timeline': 'A timeline representation',
            'cycle': 'A cycle diagram',
            'hierarchy': 'A hierarchical structure',
            'workflow': 'A workflow diagram',
            'concept': 'A conceptual illustration',
            'theory': 'A theoretical representation',
            'practical': 'A practical example',
            'real': 'A real-world example'
        }
        
        for keyword, description in keywords.items():
            if keyword in filename:
                return description
        
        return 'An educational illustration'
    
    def _calculate_relevance_score(self, filename: str, topic_context: str) -> float:
        """Calculate relevance score based on filename and context"""
        score = 0.5  # Base score
        
        # Boost score for educational keywords
        educational_keywords = ['diagram', 'chart', 'graph', 'example', 'model', 'process']
        for keyword in educational_keywords:
            if keyword in filename:
                score += 0.2
        
        # Boost score if filename contains topic-related words
        if topic_context:
            topic_words = topic_context.lower().split()
            for word in topic_words:
                if len(word) > 3 and word in filename:
                    score += 0.1
        
        return min(score, 1.0)  # Cap at 1.0
    
    def _suggest_placement(self, filename: str) -> str:
        """Suggest where to place the image in the content"""
        placement_keywords = {
            'overview': ['overview', 'introduction', 'summary'],
            'concept_explanation': ['diagram', 'model', 'structure', 'theory', 'concept'],
            'examples': ['example', 'sample', 'demo', 'practical', 'real'],
            'key_takeaways': ['key', 'important', 'summary', 'conclusion'],
            'practice_exercises': ['exercise', 'practice', 'activity', 'quiz']
        }
        
        for placement, keywords in placement_keywords.items():
            if any(keyword in filename for keyword in keywords):
                return placement
        
        return 'concept_explanation'  # Default placement
    
    def _generate_alt_text(self, filename: str) -> str:
        """Generate alt text for accessibility"""
        alt_text = os.path.splitext(filename)[0]
        alt_text = alt_text.replace('_', ' ').replace('-', ' ')
        alt_text = ' '.join(word.capitalize() for word in alt_text.split())
        return f"Educational illustration: {alt_text}"
    
    def select_relevant_images(self, image_folder: str, topic_context: str, max_images: int = 6) -> List[Dict[str, str]]:
        """Select the most relevant images for the educational content"""
        if not os.path.exists(image_folder):
            return []
        
        image_files = []
        for filename in os.listdir(image_folder):
            if any(filename.lower().endswith(ext) for ext in self.supported_formats):
                image_files.append(os.path.join(image_folder, filename))
        
        if not image_files:
            return []
        
        # Analyze all images
        analyzed_images = []
        for image_path in image_files:
            image_info = self.analyze_image_content(image_path, topic_context)
            analyzed_images.append(image_info)
        
        # Sort by relevance score and select top images
        analyzed_images.sort(key=lambda x: x['relevance_score'], reverse=True)
        
        return analyzed_images[:max_images]

class PDFExtractor:
    """Extracts images from PDF files"""
    
    def __init__(self):
        pass
    
    def sanitize_filename(self, text: str) -> str:
        """Sanitizes a string to be used as a filename"""
        text = text.replace('\n', '').strip()
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            text = text.replace(char, '')
        text = ' '.join(text.split())
        return text
    
    def resize_image(self, image: Image.Image, max_size: int = None) -> Image.Image:
        """Resize image to 70% of original size or max_size"""
        if max_size:
            image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        else:
            new_width = int(image.width * 0.7)
            new_height = int(image.height * 0.7)
            image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
        return image
    
    def extract_images_from_pdf(self, pdf_path: str, output_dir: str, img_format: str = "PNG", img_quality: int = 90) -> List[Dict[str, str]]:
        """Extract images from PDF file"""
        try:
            # Create output directory
            os.makedirs(output_dir, exist_ok=True)
            
            extracted_images = []
            
            # Open PDF with both libraries
            pdf_document = fitz.open(pdf_path)
            
            with pdfplumber.open(pdf_path) as pdf:
                for page_num, page in enumerate(pdf.pages):
                    # Extract text for filename
                    text = page.extract_text() or f"Page_{page_num + 1}"
                    text_lines = text.split('\n')[:3]  # First 3 lines
                    page_reference = ' '.join(text_lines).strip()[:50]
                    
                    if not page_reference:
                        page_reference = f"Page_{page_num + 1}"
                    
                    # Extract images using PyMuPDF
                    pdf_page = pdf_document.load_page(page_num)
                    images = pdf_page.get_images(full=True)
                    
                    for img_index, img in enumerate(images):
                        try:
                            xref = img[0]
                            base_image = pdf_document.extract_image(xref)
                            image_bytes = base_image["image"]
                            
                            # Convert to PIL Image
                            image = Image.open(io.BytesIO(image_bytes))
                            
                            # Filter small images
                            if image.width < 300 or image.height < 300:
                                continue
                            
                            # Resize image
                            image = self.resize_image(image)
                            
                            # Create filename
                            safe_reference = self.sanitize_filename(page_reference)
                            image_filename = f"{safe_reference}_{page_num + 1}_{img_index + 1}.{img_format.lower()}"
                            image_path = os.path.join(output_dir, image_filename)
                            
                            # Save image
                            image.save(image_path, img_format, quality=img_quality)
                            
                            extracted_images.append({
                                'filename': image_filename,
                                'path': image_path,
                                'page': page_num + 1,
                                'size': f"{image.width}x{image.height}",
                                'page_text': page_reference
                            })
                            
                        except Exception as e:
                            logging.error(f"Error extracting image {img_index} from page {page_num + 1}: {e}")
                            continue
            
            pdf_document.close()
            return extracted_images
            
        except Exception as e:
            logging.error(f"Error extracting images from PDF: {e}")
            return []

class PDFGenerator:
    """Generate PDF documents with embedded images"""
    
    def __init__(self):
        self.styles = getSampleStyleSheet()
        self.setup_custom_styles()
    
    def setup_custom_styles(self):
        """Setup custom paragraph styles for PDF"""
        # Title style
        self.styles.add(ParagraphStyle(
            name='CustomTitle',
            parent=self.styles['Title'],
            fontSize=24,
            spaceAfter=30,
            textColor=colors.darkblue,
            alignment=1  # Center alignment
        ))
        
        # Heading styles
        self.styles.add(ParagraphStyle(
            name='CustomHeading1',
            parent=self.styles['Heading1'],
            fontSize=18,
            spaceAfter=12,
            spaceBefore=20,
            textColor=colors.darkblue
        ))
        
        self.styles.add(ParagraphStyle(
            name='CustomHeading2',
            parent=self.styles['Heading2'],
            fontSize=14,
            spaceAfter=10,
            spaceBefore=15,
            textColor=colors.darkgreen
        ))
        
        # Body text with better spacing
        self.styles.add(ParagraphStyle(
            name='CustomBody',
            parent=self.styles['Normal'],
            fontSize=11,
            spaceAfter=8,
            leading=14
        ))
        
        # Figure caption style
        self.styles.add(ParagraphStyle(
            name='FigureCaption',
            parent=self.styles['Normal'],
            fontSize=9,
            textColor=colors.grey,
            alignment=1,  # Center alignment
            spaceAfter=15,
            fontName='Helvetica-Oblique'
        ))
    
    def convert_markdown_formatting(self, text):
        """Convert basic Markdown formatting to ReportLab HTML"""
        import re
        
        # Convert **bold** to <b>bold</b>
        text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
        
        # Convert *italic* to <i>italic</i>
        text = re.sub(r'\*(.*?)\*', r'<i>\1</i>', text)
        
        # Convert `code` to monospace
        text = re.sub(r'`(.*?)`', r'<font name="Courier">\1</font>', text)
        
        # Convert [link](url) to just the link text for PDF
        text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
        
        return text
    
    def markdown_to_pdf_elements(self, markdown_text, images_info=None):
        """Convert markdown text to PDF elements with embedded images"""
        elements = []
        images_info = images_info or []
        
        # Split content by lines
        lines = markdown_text.split('\n')
        current_paragraph = []
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            
            if not line:
                # Empty line - end current paragraph
                if current_paragraph:
                    para_text = ' '.join(current_paragraph)
                    if para_text.strip():
                        formatted_text = self.convert_markdown_formatting(para_text)
                        elements.append(Paragraph(formatted_text, self.styles['CustomBody']))
                    current_paragraph = []
                i += 1
                continue
            
            # Check for headers
            if line.startswith('# '):
                # Finish current paragraph
                if current_paragraph:
                    para_text = ' '.join(current_paragraph)
                    formatted_text = self.convert_markdown_formatting(para_text)
                    elements.append(Paragraph(formatted_text, self.styles['CustomBody']))
                    current_paragraph = []
                
                # Add title
                title_text = line[2:].strip()
                formatted_title = self.convert_markdown_formatting(title_text)
                elements.append(Paragraph(formatted_title, self.styles['CustomTitle']))
                elements.append(Spacer(1, 12))
                
            elif line.startswith('## '):
                # Finish current paragraph
                if current_paragraph:
                    para_text = ' '.join(current_paragraph)
                    formatted_text = self.convert_markdown_formatting(para_text)
                    elements.append(Paragraph(formatted_text, self.styles['CustomBody']))
                    current_paragraph = []
                
                # Add heading 1
                heading_text = line[3:].strip()
                formatted_heading = self.convert_markdown_formatting(heading_text)
                elements.append(Paragraph(formatted_heading, self.styles['CustomHeading1']))
                
            elif line.startswith('### '):
                # Finish current paragraph
                if current_paragraph:
                    para_text = ' '.join(current_paragraph)
                    formatted_text = self.convert_markdown_formatting(para_text)
                    elements.append(Paragraph(formatted_text, self.styles['CustomBody']))
                    current_paragraph = []
                
                heading_text = line[4:].strip()
                formatted_heading = self.convert_markdown_formatting(heading_text)
                
                # Check if this is a "Visual Illustrations" section
                if "Visual Illustrations" in heading_text:
                    elements.append(Paragraph(formatted_heading, self.styles['CustomHeading2']))
                    # Add images for this section
                    self.add_images_to_elements(elements, images_info)
                else:
                    elements.append(Paragraph(formatted_heading, self.styles['CustomHeading2']))
                
            elif line.startswith('- ') or line.startswith('* '):
                # Finish current paragraph
                if current_paragraph:
                    para_text = ' '.join(current_paragraph)
                    formatted_text = self.convert_markdown_formatting(para_text)
                    elements.append(Paragraph(formatted_text, self.styles['CustomBody']))
                    current_paragraph = []
                
                # Handle bullet points
                bullet_text = line[2:].strip()
                formatted_bullet = self.convert_markdown_formatting(bullet_text)
                elements.append(Paragraph(f"• {formatted_bullet}", self.styles['CustomBody']))
                
            elif re.match(r'^\d+\. ', line):
                # Finish current paragraph
                if current_paragraph:
                    para_text = ' '.join(current_paragraph)
                    formatted_text = self.convert_markdown_formatting(para_text)
                    elements.append(Paragraph(formatted_text, self.styles['CustomBody']))
                    current_paragraph = []
                
                # Handle numbered lists
                formatted_line = self.convert_markdown_formatting(line)
                elements.append(Paragraph(formatted_line, self.styles['CustomBody']))
                
            else:
                # Regular text - add to current paragraph
                current_paragraph.append(line)
            
            i += 1
        
        # Add final paragraph if exists
        if current_paragraph:
            para_text = ' '.join(current_paragraph)
            if para_text.strip():
                formatted_text = self.convert_markdown_formatting(para_text)
                elements.append(Paragraph(formatted_text, self.styles['CustomBody']))
        
        return elements
    
    def add_images_to_elements(self, elements, images_info):
        """Add images to PDF elements"""
        for img_info in images_info:
            try:
                # Get image path
                image_path = os.path.join(STATIC_IMAGES_FOLDER, img_info['filename'])
                
                if os.path.exists(image_path):
                    # Add image with proper sizing
                    img = RLImage(image_path, width=4*inch, height=3*inch)
                    elements.append(img)
                    
                    # Add caption
                    caption = img_info.get('description', 'Educational illustration')
                    elements.append(Paragraph(f"<b>Figure:</b> {caption}", self.styles['FigureCaption']))
                    elements.append(Spacer(1, 12))
                    
            except Exception as e:
                logging.error(f"Error adding image {img_info['filename']} to PDF: {e}")
                # Add placeholder text instead
                elements.append(Paragraph(f"<i>[Image: {img_info.get('description', 'Educational illustration')}]</i>", self.styles['FigureCaption']))
    
    def generate_pdf(self, content, title, output_path, images_info=None):
        """Generate PDF from markdown content with embedded images"""
        try:
            # Create PDF document
            doc = SimpleDocTemplate(
                output_path,
                pagesize=A4,
                rightMargin=72,
                leftMargin=72,
                topMargin=72,
                bottomMargin=18
            )
            
            # Convert markdown to PDF elements
            elements = self.markdown_to_pdf_elements(content, images_info)
            
            # Build PDF
            doc.build(elements)
            return True
            
        except Exception as e:
            logging.error(f"Error generating PDF: {e}")
            return False

class EContentGenerator:
    """
    Educational Content Generator that creates comprehensive study materials
    from transcripts using AI-powered content expansion
    """
    
    def __init__(self, model_name: str = "llama3.2:3b"):
        """
        Initialize the content generator with a specified model.
        
        Args:
            model_name: The Ollama model to use for content generation
        """
        self.model_name = model_name
        
    def generate_study_material(self, content: str, topic_title: str = "Educational Topic") -> dict:
        """
        Generate comprehensive study material from content
        
        Args:
            content: The source content (from transcript)
            topic_title: Title for the study material
            
        Returns:
            Dict containing all sections of the study material
        """
        
        # Generate each section separately for better quality
        sections = {}
        
        # 1. Overview
        sections['overview'] = self._generate_overview(content, topic_title)
        
        # 2. Learning Outcomes
        sections['learning_outcomes'] = self._generate_learning_outcomes(content, topic_title)
        
        # 3. Concept Explanation
        sections['concept_explanation'] = self._generate_concept_explanation(content, topic_title)
        
        # 4. Examples
        sections['examples'] = self._generate_examples(content, topic_title)
        
        # 5. Case Studies
        sections['case_studies'] = self._generate_case_studies(content, topic_title)
        
        # 6. Key Takeaways
        sections['key_takeaways'] = self._generate_key_takeaways(content, topic_title)
        
        # 7. Practice Exercises
        sections['practice_exercises'] = self._generate_practice_exercises(content, topic_title)
        
        # 8. Quiz Questions
        sections['quiz_questions'] = self._generate_quiz_questions(content, topic_title)
        
        return sections
    
    def generate_study_material_with_progress(self, content: str, topic_title: str = "Educational Topic", progress_callback=None) -> dict:
        """
        Generate comprehensive study material with progress tracking
        
        Args:
            content: The source content (from transcript)
            topic_title: Title for the study material
            progress_callback: Function to call with progress updates
            
        Returns:
            Dict containing all sections of the study material
        """
        
        sections = {}
        section_names = [
            ('overview', 'Overview'),
            ('learning_outcomes', 'Learning Outcomes'),
            ('concept_explanation', 'Concept Explanation'),
            ('examples', 'Examples'),
            ('key_takeaways', 'Key Takeaways'),
            ('practice_exercises', 'Practice Exercises')
        ]
        
        total_sections = len(section_names)
        
        for i, (section_key, section_name) in enumerate(section_names):
            if progress_callback:
                progress_callback(section_key, (i / total_sections) * 100)
            
            if section_key == 'overview':
                sections[section_key] = self._generate_overview(content, topic_title)
            elif section_key == 'learning_outcomes':
                sections[section_key] = self._generate_learning_outcomes(content, topic_title)
            elif section_key == 'concept_explanation':
                sections[section_key] = self._generate_concept_explanation(content, topic_title)
            elif section_key == 'examples':
                sections[section_key] = self._generate_examples(content, topic_title)
            elif section_key == 'key_takeaways':
                sections[section_key] = self._generate_key_takeaways(content, topic_title)
            elif section_key == 'practice_exercises':
                sections[section_key] = self._generate_practice_exercises(content, topic_title)
        
        # Add a simplified quiz section
        if progress_callback:
            progress_callback('quiz_questions', 90)
        sections['quiz_questions'] = self._generate_simple_quiz(content, topic_title)
        
        if progress_callback:
            progress_callback('completed', 100)
        
        return sections
    
    def _generate_simple_quiz(self, content: str, topic_title: str) -> str:
        """Generate a simplified quiz section"""
        prompt = f"""Based on the following content about "{topic_title}", create a simple quiz for self-assessment.

Content: {content[:2000]}...

Create:
- 3 Multiple Choice Questions (with 4 options each and correct answers)
- 2 Short answer questions

Format clearly with correct answers provided at the end."""

        return self._call_ollama(prompt)
    
    def _generate_overview(self, content: str, topic_title: str) -> str:
        """Generate overview section"""
        prompt = f"""Based on the following content about "{topic_title}", create a comprehensive overview section for study material.

Content: {content[:2000]}...

Create an overview that includes:
- Brief description of what the topic covers
- Why this topic is important for students
- What students will gain from studying this

Make it engaging and informative (2-3 paragraphs):"""

        return self._call_ollama(prompt, max_tokens=600)
    
    def _generate_learning_outcomes(self, content: str, topic_title: str) -> str:
        """Generate learning outcomes section"""
        prompt = f"""Based on the following content about "{topic_title}", create specific learning outcomes.

Content: {content[:1500]}...

Create 4-6 learning outcomes that students should achieve after studying this topic. 
Format as:
"After completing this topic, students will be able to:"
- [Outcome 1]
- [Outcome 2]
- etc.

Make them specific and action-oriented."""

        return self._call_ollama(prompt, max_tokens=400)
    
    def _generate_concept_explanation(self, content: str, topic_title: str) -> str:
        """Generate detailed concept explanation"""
        prompt = f"""Based on the following content about "{topic_title}", create a detailed concept explanation for students.

Content: {content[:4000]}...

Create a comprehensive explanation that includes:
- Core concepts and definitions
- How different concepts relate to each other
- Step-by-step explanations where applicable
- Important principles and theories
- Common misconceptions to avoid

Make it detailed and educational (5-7 paragraphs). Use clear, student-friendly language."""

        return self._call_ollama(prompt)
    
    def _generate_examples(self, content: str, topic_title: str) -> str:
        """Generate real-world examples"""
        prompt = f"""Based on the following content about "{topic_title}", create 3-4 real-world examples that illustrate the concepts.

Content: {content[:3000]}...

For each example, provide:
- A clear scenario or situation
- How the concept applies in this context
- What students can learn from this example
- Connection to everyday life or professional applications

Make examples diverse and engaging."""

        return self._call_ollama(prompt)
    
    def _generate_case_studies(self, content: str, topic_title: str) -> str:
        """Generate case studies for application-based understanding"""
        prompt = f"""Based on the following content about "{topic_title}", create 2 detailed case studies for application-based learning.

Content: {content[:3000]}...

For each case study, include:
- Background/Context
- The situation or problem
- How the concepts from this topic apply
- Analysis and solution approach
- Lessons learned
- Discussion questions for students

Make them realistic and thought-provoking."""

        return self._call_ollama(prompt)
    
    def _generate_key_takeaways(self, content: str, topic_title: str) -> str:
        """Generate key takeaways section"""
        prompt = f"""Based on the following content about "{topic_title}", create key takeaways that students should remember.

Content: {content[:3000]}...

Create 6-8 key takeaways in bullet point format:
- [Key point 1]
- [Key point 2]
- etc.

Focus on the most important concepts, principles, and insights that students must retain for exams and practical application."""

        return self._call_ollama(prompt)
    
    def _generate_practice_exercises(self, content: str, topic_title: str) -> str:
        """Generate practice exercises and activities"""
        prompt = f"""Based on the following content about "{topic_title}", create 4-5 practice exercises for students.

Content: {content[:3000]}...

Create diverse exercises including:
- Analytical exercises
- Problem-solving tasks
- Reflective questions
- Application-based activities
- Critical thinking challenges

For each exercise, provide:
- Clear instructions
- What students should focus on
- Expected outcomes

Make them engaging and educational."""

        return self._call_ollama(prompt)
    
    def _generate_quiz_questions(self, content: str, topic_title: str) -> str:
        """Generate quiz questions for self-assessment"""
        prompt = f"""Based on the following content about "{topic_title}", create a comprehensive quiz for self-assessment.

Content: {content[:3000]}...

Create:
- 5 Multiple Choice Questions (with 4 options each and correct answers)
- 3 Fill-in-the-blank questions
- 2 Short answer questions
- 1 Essay question

Format clearly with correct answers provided at the end. Make questions test different levels of understanding: recall, comprehension, application, and analysis."""

        return self._call_ollama(prompt)
    
    def _call_ollama(self, prompt: str, max_tokens: int = 800) -> str:
        """Make API call to Ollama with timeout and retry logic"""
        try:
            response = ollama.generate(
                model=self.model_name,
                prompt=prompt,
                options={
                    'temperature': 0.7,
                    'top_p': 0.9,
                    'max_tokens': max_tokens
                }
            )
            
            result = response['response'].strip()
            return result if result else "Unable to generate content for this section."
            
        except Exception as e:
            error_msg = str(e)
            logging.error(f"Error calling Ollama: {error_msg}")
            
            # Handle specific GPU memory errors
            if "status code: 500" in error_msg or "system memory" in error_msg:
                # Try to free up memory and retry once
                try:
                    import gc
                    gc.collect()
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                    
                    # Retry with smaller max_tokens
                    response = ollama.generate(
                        model=self.model_name,
                        prompt=prompt[:1000],  # Truncate prompt
                        options={
                            'temperature': 0.7,
                            'top_p': 0.9,
                            'max_tokens': min(max_tokens, 400)  # Reduce max tokens
                        }
                    )
                    
                    result = response['response'].strip()
                    return result if result else "Content generated with reduced parameters due to memory constraints."
                    
                except Exception as retry_e:
                    logging.error(f"Retry failed: {retry_e}")
                    return "Unable to generate content due to insufficient GPU memory. Consider using a smaller model or restarting the application."
            
            return f"Error generating content: {error_msg}"
    
    def format_study_material(self, sections: dict, topic_title: str) -> str:
        """Format all sections into a complete study material document"""
        
        formatted_content = f"""# {topic_title}

## Overview
{sections.get('overview', 'Content not available')}

## Learning Outcomes
{sections.get('learning_outcomes', 'Content not available')}

## Main Contents

### Concept Explanation
{sections.get('concept_explanation', 'Content not available')}

### Examples
{sections.get('examples', 'Content not available')}

### Case Studies / Scenarios
{sections.get('case_studies', 'Content not available')}

## Key Takeaways
{sections.get('key_takeaways', 'Content not available')}

## Learning Activities

### Practice Exercises / Activities
{sections.get('practice_exercises', 'Content not available')}

### Quizzes / Self-Assessment
{sections.get('quiz_questions', 'Content not available')}

---
*Generated using AI-powered Educational Content Generator*
"""
        
        return formatted_content
    
    def generate_summary(self, content: str, topic_title: str = "Video Content") -> str:
        """Generate a focused summary with clear key points"""
        prompt = f"""Summarize this content about "{topic_title}". Use ONLY this format, no explanations:

{content[:4000]}

**Main Topic:** [What this content is about]

**Key Points:**
• [Point 1]
• [Point 2]
• [Point 3]
• [Point 4]
• [Point 5]

**Key Takeaways:**
[Main conclusions]"""

        return self._call_ollama(prompt, max_tokens=400)
    
    def _generate_title(self, content: str) -> str:
        """Generate a title from content"""
        prompt = f"""Based on this content, suggest a clear, educational title for study material:

Content: {content[:1000]}...

Provide just the title (no explanation):"""
        
        title = self._call_ollama(prompt)
        return title.strip('"').strip() if title else "Educational Topic"

class SimpleSummarizer:
    """Simple text summarizer using Ollama"""
    
    def __init__(self, model_name: str = "llama3.2:3b"):
        self.model_name = model_name
    
    def summarize_text(self, text: str) -> str:
        """Summarize text with clear key points format"""
        prompt = f"""Summarize this text. Use ONLY this format, no explanations:

{text[:4000]}

**Main Topic:** [What this is about]

**Key Points:**
• [Point 1]
• [Point 2]
• [Point 3]
• [Point 4]
• [Point 5]

**Key Takeaways:**
[Main conclusions]"""

        try:
            response = ollama.generate(
                model=self.model_name,
                prompt=prompt,
                options={
                    'temperature': 0.5,  # Even lower temperature for strict format
                    'top_p': 0.7,
                    'max_tokens': 350
                }
            )
            
            result = response['response'].strip()
            return result if result else "Unable to generate summary."
            
        except Exception as e:
            logging.error(f"Error generating summary: {e}")
            return f"Error generating summary: {str(e)}"

class ContentGenerator:
    """Enhanced AI-powered content generator for educational materials"""
    
    def __init__(self, model_name: str = "llama3.2:3b"):
        self.model_name = model_name
        
    def generate_summary(self, content: str, topic_title: str = "Video Content") -> str:
        """Generate a summary with clear key points"""
        prompt = f"""Summarize this content about "{topic_title}". Use ONLY this format, no explanations:

{content[:4000]}

**Main Topic:** [What this content is about]

**Key Points:**
• [Point 1]
• [Point 2]
• [Point 3]
• [Point 4]
• [Point 5]

**Key Takeaways:**
[Main conclusions]"""

        return self._call_ollama(prompt, max_tokens=350)
    
    def generate_study_material(self, content: str, topic_title: str, selected_sections: List[str]) -> dict:
        """Generate comprehensive study material"""
        sections = {}
        
        if 'overview' in selected_sections:
            sections['overview'] = self._generate_overview(content, topic_title)
            sections['learning_outcomes'] = self._generate_learning_outcomes(content, topic_title)
        
        if 'concept_explanation' in selected_sections:
            sections['concept_explanation'] = self._generate_concept_explanation(content, topic_title)
        
        if 'examples' in selected_sections:
            sections['examples'] = self._generate_examples(content, topic_title)
        
        if 'case_studies' in selected_sections:
            sections['case_studies'] = self._generate_case_studies(content, topic_title)
        
        if 'key_takeaways' in selected_sections:
            sections['key_takeaways'] = self._generate_key_takeaways(content, topic_title)
        
        if 'practice_exercises' in selected_sections:
            sections['practice_exercises'] = self._generate_practice_exercises(content, topic_title)
        
        if 'quiz_questions' in selected_sections:
            sections['quiz_questions'] = self._generate_quiz_questions(content, topic_title)
        
        return sections
    
    def generate_study_material_with_progress(self, content: str, topic_title: str, selected_sections: List[str], progress_callback=None) -> dict:
        """Generate comprehensive study material with progress tracking"""
        
        sections = {}
        section_names = [
            ('overview', 'Overview'),
            ('learning_outcomes', 'Learning Outcomes'),
            ('concept_explanation', 'Concept Explanation'),
            ('examples', 'Examples'),
            ('case_studies', 'Case Studies'),
            ('key_takeaways', 'Key Takeaways'),
            ('practice_exercises', 'Practice Exercises'),
            ('quiz_questions', 'Quiz Questions')
        ]
        
        # Filter to only selected sections
        selected_section_names = [(key, name) for key, name in section_names if key in selected_sections]
        total_sections = len(selected_section_names)
        
        for i, (section_key, section_name) in enumerate(selected_section_names):
            if progress_callback:
                progress_callback(section_key, (i / total_sections) * 100)
            
            if section_key == 'overview':
                sections['overview'] = self._generate_overview(content, topic_title)
            elif section_key == 'learning_outcomes':
                sections['learning_outcomes'] = self._generate_learning_outcomes(content, topic_title)
            elif section_key == 'concept_explanation':
                sections['concept_explanation'] = self._generate_concept_explanation(content, topic_title)
            elif section_key == 'examples':
                sections['examples'] = self._generate_examples(content, topic_title)
            elif section_key == 'case_studies':
                sections['case_studies'] = self._generate_case_studies(content, topic_title)
            elif section_key == 'key_takeaways':
                sections['key_takeaways'] = self._generate_key_takeaways(content, topic_title)
            elif section_key == 'practice_exercises':
                sections['practice_exercises'] = self._generate_practice_exercises(content, topic_title)
            elif section_key == 'quiz_questions':
                sections['quiz_questions'] = self._generate_quiz_questions(content, topic_title)
        
        if progress_callback:
            progress_callback('completed', 100)
        
        return sections
    
    def _generate_overview(self, content: str, topic_title: str) -> str:
        prompt = f"""Create an overview for "{topic_title}" based on this content:

{content[:2000]}...

Include:
- Brief description of the topic
- Why it's important
- What students will learn

Make it engaging (2-3 paragraphs):"""
        return self._call_ollama(prompt)
    
    def _generate_learning_outcomes(self, content: str, topic_title: str) -> str:
        prompt = f"""Create learning outcomes for "{topic_title}":

{content[:1500]}...

Format as:
"After studying this topic, students will be able to:"
- [Outcome 1]
- [Outcome 2]
- etc.

Create 4-6 specific, actionable outcomes:"""
        return self._call_ollama(prompt)
    
    def _generate_concept_explanation(self, content: str, topic_title: str) -> str:
        prompt = f"""Create detailed concept explanations for "{topic_title}":

{content[:4000]}...

Include:
- Core concepts and definitions
- How concepts relate to each other
- Step-by-step explanations
- Important principles

Make it comprehensive and educational (5-7 paragraphs):"""
        return self._call_ollama(prompt)
    
    def _generate_examples(self, content: str, topic_title: str) -> str:
        prompt = f"""Create real-world examples for "{topic_title}":

{content[:3000]}...

Provide 3-4 examples that:
- Illustrate key concepts
- Show practical applications
- Connect to everyday life
- Help students understand better

Make examples diverse and engaging:"""
        return self._call_ollama(prompt)
    
    def _generate_case_studies(self, content: str, topic_title: str) -> str:
        """Generate case studies for application-based understanding"""
        prompt = f"""Based on the following content about "{topic_title}", create 2 detailed case studies for application-based learning.

{content[:3000]}...

For each case study, include:
- Background/Context
- The situation or problem
- How the concepts from this topic apply
- Analysis and solution approach
- Lessons learned
- Discussion questions for students

Make them realistic and thought-provoking:"""
        return self._call_ollama(prompt)
    
    def _generate_key_takeaways(self, content: str, topic_title: str) -> str:
        prompt = f"""Create key takeaways for "{topic_title}":

{content[:3000]}...

List 6-8 essential points students must remember:
- [Key point 1]
- [Key point 2]
- etc.

Focus on the most important concepts:"""
        return self._call_ollama(prompt)
    
    def _generate_practice_exercises(self, content: str, topic_title: str) -> str:
        prompt = f"""Create practice exercises for "{topic_title}":

{content[:3000]}...

Design 4-5 exercises including:
- Analytical tasks
- Problem-solving activities
- Reflective questions
- Application challenges

Make them educational and engaging:"""
        return self._call_ollama(prompt)
    
    def _generate_quiz_questions(self, content: str, topic_title: str) -> str:
        prompt = f"""Create quiz questions for "{topic_title}":

{content[:3000]}...

Include:
- 5 Multiple choice questions (with answers)
- 3 Short answer questions
- 2 Essay questions

Format clearly with correct answers:"""
        return self._call_ollama(prompt)
    
    def _generate_title(self, content: str) -> str:
        """Generate a title from content"""
        prompt = f"""Based on this content, suggest a clear, educational title for study material:

{content[:1000]}...

Provide just the title (no explanation):"""
        
        title = self._call_ollama(prompt)
        return title.strip('"').strip() if title else "Educational Topic"
    
    def _call_ollama(self, prompt: str, max_tokens: int = 800) -> str:
        """Make API call to Ollama with timeout and retry logic"""
        try:
            response = ollama.generate(
                model=self.model_name,
                prompt=prompt,
                options={
                    'temperature': 0.7,
                    'top_p': 0.9,
                    'max_tokens': max_tokens
                }
            )
            
            result = response['response'].strip()
            return result if result else "Unable to generate content for this section."
            
        except Exception as e:
            error_msg = str(e)
            logging.error(f"Error calling Ollama: {error_msg}")
            
            # Handle specific GPU memory errors
            if "status code: 500" in error_msg or "system memory" in error_msg:
                # Try to free up memory and retry once
                try:
                    import gc
                    gc.collect()
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                    
                    # Retry with smaller max_tokens
                    response = ollama.generate(
                        model=self.model_name,
                        prompt=prompt[:1000],  # Truncate prompt
                        options={
                            'temperature': 0.7,
                            'top_p': 0.9,
                            'max_tokens': min(max_tokens, 400)  # Reduce max tokens
                        }
                    )
                    
                    result = response['response'].strip()
                    return result if result else "Content generated with reduced parameters due to memory constraints."
                    
                except Exception as retry_e:
                    logging.error(f"Retry failed: {retry_e}")
                    return "Unable to generate content due to insufficient GPU memory. Consider using a smaller model or restarting the application."
            
            return f"Error generating content: {error_msg}"

def load_whisper_model(model_size="turbo"):
    """Load Whisper model with GPU acceleration"""
    global whisper_model
    if whisper_model is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"Loading Whisper model: {model_size} on {device}")
        whisper_model = whisper.load_model(model_size, device=device)
        print("Model loaded successfully!")
    return whisper_model

def check_gpu_memory():
    """Check available GPU memory"""
    if torch.cuda.is_available():
        total_memory = torch.cuda.get_device_properties(0).total_memory / 1024**3
        allocated_memory = torch.cuda.memory_allocated(0) / 1024**3
        free_memory = total_memory - allocated_memory
        
        return {
            'total': total_memory,
            'allocated': allocated_memory,
            'free': free_memory,
            'available': True
        }
    else:
        return {'available': False}

def ensure_gpu_memory_for_ollama():
    """Ensure sufficient GPU memory is available for Ollama"""
    global whisper_model
    
    if torch.cuda.is_available():
        memory_info = check_gpu_memory()
        
        # If less than 2GB free, clear whisper model
        if memory_info['free'] < 2.0:
            logging.info(f"Low GPU memory ({memory_info['free']:.1f}GB free). Clearing Whisper model.")
            
            if whisper_model is not None:
                del whisper_model
                whisper_model = None
            
            torch.cuda.empty_cache()
            import gc
            gc.collect()
            
            # Check again
            memory_info = check_gpu_memory()
            logging.info(f"After cleanup: {memory_info['free']:.1f}GB free")
            
            return memory_info['free'] >= 1.5  # Need at least 1.5GB for Ollama
        
        return True
    
    return True  # CPU mode, no memory constraints

def get_gpu_status():
    """Get GPU status information"""
    if torch.cuda.is_available():
        gpu_name = torch.cuda.get_device_name(0)
        total_memory = torch.cuda.get_device_properties(0).total_memory / 1024**3
        allocated_memory = torch.cuda.memory_allocated(0) / 1024**3
        
        return {
            'available': True,
            'name': gpu_name,
            'total_memory': f"{total_memory:.1f} GB",
            'allocated_memory': f"{allocated_memory:.1f} GB",
            'free_memory': f"{total_memory - allocated_memory:.1f} GB"
        }
    else:
        return {
            'available': False,
            'name': 'CPU Only',
            'message': 'CUDA not available'
        }

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
        logging.error(f"Error downloading audio: {e}")
        return None

def get_video_info(url):
    """Get video information"""
    ydl_opts = {'quiet': True, 'no_warnings': True}
    
    try:
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

def format_srt_time(seconds):
    """Convert seconds to SRT timestamp format"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millisecs = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millisecs:03d}"

def integrate_images_into_sections(sections: Dict[str, str], images: List[Dict]) -> Dict[str, str]:
    """Integrate images into appropriate sections based on their suggested placement"""
    
    # Group images by suggested placement
    images_by_placement = {}
    for img in images:
        placement = img['suggested_placement']
        if placement not in images_by_placement:
            images_by_placement[placement] = []
        images_by_placement[placement].append(img)
    
    # Integrate images into sections
    for placement, img_list in images_by_placement.items():
        if placement in sections:
            # Add images to the section
            image_html = generate_image_html(img_list)
            sections[placement] += f"\n\n### Visual Illustrations\n{image_html}"
    
    return sections

def generate_image_html(images: List[Dict]) -> str:
    """Generate HTML for displaying images in the content"""
    from urllib.parse import quote
    
    html_parts = []
    for img in images:
        # Use web_path if available, otherwise construct the path with proper URL encoding
        if 'web_path' in img:
            image_src = img['web_path']
        else:
            # URL encode the filename to handle spaces and special characters
            encoded_filename = quote(img['filename'])
            image_src = f"/static/images/{encoded_filename}"
        
        html = f"""
<div class="educational-image" style="margin: 20px 0; text-align: center;">
    <img src="{image_src}" 
         alt="{img.get('alt_text', 'Educational illustration')}" 
         style="max-width: 100%; height: auto; border: 1px solid #ddd; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);"
         onerror="this.style.display='none'; this.nextElementSibling.innerHTML='<em>Image could not be loaded</em>';">
    <p style="margin-top: 10px; font-style: italic; color: #666; font-size: 14px;">
        <strong>Figure:</strong> {img.get('description', 'Educational illustration')}
    </p>
</div>"""
        html_parts.append(html)
    
    return '\n'.join(html_parts)

def save_results(transcript_result, summary, study_material, video_info, job_id, selected_images=None):
    """Save all results to files including PDF with images"""
    output_dir = Path(OUTPUT_FOLDER)
    output_dir.mkdir(exist_ok=True)
    
    # Clean title for filename
    title = video_info['title']
    safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).strip()
    safe_title = safe_title[:30]
    
    base_name = f"{safe_title}_{job_id}"
    files = {}
    
    # 1. Transcript file
    txt_filename = f"{base_name}_transcript.txt"
    txt_file = output_dir / txt_filename
    with open(txt_file, 'w', encoding='utf-8') as f:
        f.write(f"Title: {video_info['title']}\n")
        f.write(f"Duration: {video_info['duration']//60}:{video_info['duration']%60:02d}\n")
        f.write(f"Language: {transcript_result['language']}\n")
        f.write("-" * 50 + "\n\n")
        f.write("TRANSCRIPT:\n")
        f.write(transcript_result['text'].strip())
    files['transcript'] = txt_filename
    
    # 2. Summary file (if available)
    if summary:
        summary_filename = f"{base_name}_summary.txt"
        summary_file = output_dir / summary_filename
        with open(summary_file, 'w', encoding='utf-8') as f:
            f.write(f"Title: {video_info['title']}\n")
            f.write(f"Duration: {video_info['duration']//60}:{video_info['duration']%60:02d}\n")
            f.write("-" * 50 + "\n\n")
            f.write("SUMMARY:\n")
            f.write(summary)
        files['summary'] = summary_filename
    
    # 3. Study material files (if available)
    if study_material:
        # Markdown file
        study_filename = f"{base_name}_study_material.md"
        study_file = output_dir / study_filename
        with open(study_file, 'w', encoding='utf-8') as f:
            f.write(study_material)
        files['study_material'] = study_filename
        
        # PDF file with embedded images
        pdf_generator = PDFGenerator()
        pdf_filename = f"{base_name}_study_material.pdf"
        pdf_file = output_dir / pdf_filename
        
        if pdf_generator.generate_pdf(study_material, video_info['title'], str(pdf_file), selected_images):
            files['study_material_pdf'] = pdf_filename
            logging.info(f"Generated PDF: {pdf_filename}")
        else:
            logging.error(f"Failed to generate PDF: {pdf_filename}")
    
    # 4. SRT file
    srt_filename = f"{base_name}.srt"
    srt_file = output_dir / srt_filename
    with open(srt_file, 'w', encoding='utf-8') as f:
        for i, segment in enumerate(transcript_result['segments'], 1):
            start = format_srt_time(segment['start'])
            end = format_srt_time(segment['end'])
            text = segment['text'].strip()
            f.write(f"{i}\n{start} --> {end}\n{text}\n\n")
    files['srt'] = srt_filename
    
    # 5. JSON file
    json_filename = f"{base_name}_complete.json"
    json_file = output_dir / json_filename
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump({
            'video_info': video_info,
            'transcript': transcript_result,
            'summary': summary,
            'study_material': study_material,
            'job_id': job_id,
            'timestamp': datetime.now().isoformat(),
            'images_count': len(selected_images) if selected_images else 0
        }, f, indent=2, ensure_ascii=False)
    files['json'] = json_filename
    
    return files

def generate_selective_study_material(content_generator, content: str, topic_title: str, selected_sections: List[str], progress_callback=None):
    """Generate study material with only selected sections"""
    
    # Default sections if none selected
    if not selected_sections:
        selected_sections = ['overview', 'concept_explanation', 'examples', 'key_takeaways', 'practice_exercises', 'quiz_questions']
    
    sections = {}
    section_mapping = {
        'overview': ('overview', 'Overview'),
        'concept_explanation': ('concept_explanation', 'Concept Explanation'),
        'examples': ('examples', 'Examples'),
        'case_studies': ('case_studies', 'Case Studies'),
        'key_takeaways': ('key_takeaways', 'Key Takeaways'),
        'practice_exercises': ('practice_exercises', 'Practice Exercises'),
        'quiz_questions': ('quiz_questions', 'Quiz Questions')
    }
    
    total_sections = len(selected_sections)
    
    for i, section_key in enumerate(selected_sections):
        if progress_callback:
            progress_callback(section_key, (i / total_sections) * 100)
        
        if section_key == 'overview':
            # Generate both overview and learning outcomes together
            sections['overview'] = content_generator._generate_overview(content, topic_title)
            sections['learning_outcomes'] = content_generator._generate_learning_outcomes(content, topic_title)
        elif section_key == 'concept_explanation':
            sections['concept_explanation'] = content_generator._generate_concept_explanation(content, topic_title)
        elif section_key == 'examples':
            sections['examples'] = content_generator._generate_examples(content, topic_title)
        elif section_key == 'case_studies':
            sections['case_studies'] = content_generator._generate_case_studies(content, topic_title)
        elif section_key == 'key_takeaways':
            sections['key_takeaways'] = content_generator._generate_key_takeaways(content, topic_title)
        elif section_key == 'practice_exercises':
            sections['practice_exercises'] = content_generator._generate_practice_exercises(content, topic_title)
        elif section_key == 'quiz_questions':
            sections['quiz_questions'] = content_generator._generate_quiz_questions(content, topic_title)
    
    if progress_callback:
        progress_callback('completed', 100)
    
    return sections

def format_selective_study_material(sections: Dict[str, str], topic_title: str) -> str:
    """Format selected sections into a complete study material document"""
    
    formatted_content = f"# {topic_title}\n\n"
    
    # Add sections in a logical order
    section_order = [
        ('overview', '## Overview'),
        ('learning_outcomes', '## Learning Outcomes'),
        ('concept_explanation', '### Concept Explanation'),
        ('examples', '### Examples'),
        ('case_studies', '### Case Studies / Scenarios'),
        ('key_takeaways', '## Key Takeaways'),
        ('practice_exercises', '### Practice Exercises / Activities'),
        ('quiz_questions', '### Quizzes / Self-Assessment')
    ]
    
    main_content_added = False
    learning_activities_added = False
    
    for section_key, section_header in section_order:
        if section_key in sections and sections[section_key]:
            # Add main content header if we're adding concept explanations, examples, or case studies
            if section_key in ['concept_explanation', 'examples', 'case_studies'] and not main_content_added:
                formatted_content += "## Main Contents\n\n"
                main_content_added = True
            
            # Add learning activities header if we're adding exercises or quizzes
            if section_key in ['practice_exercises', 'quiz_questions'] and not learning_activities_added:
                formatted_content += "## Learning Activities\n\n"
                learning_activities_added = True
            
            formatted_content += f"{section_header}\n{sections[section_key]}\n\n"
    
    formatted_content += "---\n*Generated using AI-powered Educational Content Generator*\n"
    
    return formatted_content

def format_study_material(sections: dict, topic_title: str) -> str:
    """Format study material sections into markdown"""
    content = f"# {topic_title}\n\n"
    
    if 'overview' in sections:
        content += f"## Overview\n{sections['overview']}\n\n"
    
    if 'learning_outcomes' in sections:
        content += f"## Learning Outcomes\n{sections['learning_outcomes']}\n\n"
    
    if any(key in sections for key in ['concept_explanation', 'examples']):
        content += "## Main Content\n\n"
        
        if 'concept_explanation' in sections:
            content += f"### Concept Explanation\n{sections['concept_explanation']}\n\n"
        
        if 'examples' in sections:
            content += f"### Examples\n{sections['examples']}\n\n"
    
    if 'key_takeaways' in sections:
        content += f"## Key Takeaways\n{sections['key_takeaways']}\n\n"
    
    if any(key in sections for key in ['practice_exercises', 'quiz_questions']):
        content += "## Learning Activities\n\n"
        
        if 'practice_exercises' in sections:
            content += f"### Practice Exercises\n{sections['practice_exercises']}\n\n"
        
        if 'quiz_questions' in sections:
            content += f"### Quiz Questions\n{sections['quiz_questions']}\n\n"
    
    content += "---\n*Generated using AI-powered YouTube Summarizer*\n"
    return content

def process_video_worker(job_id):
    """Background worker for video processing"""
    job = processing_jobs[job_id]
    content_generator = EContentGenerator()
    image_analyzer = ImageAnalyzer()
    pdf_extractor = PDFExtractor()
    
    try:
        # Extract images from PDF if provided
        if job.pdf_file:
            job.status = "extracting_images"
            job.progress = 5
            
            # Create temp directory for extracted images
            temp_images_dir = os.path.join(UPLOAD_FOLDER, f"images_{job_id}")
            os.makedirs(temp_images_dir, exist_ok=True)
            
            # Extract images from PDF
            job.extracted_images = pdf_extractor.extract_images_from_pdf(
                job.pdf_file, temp_images_dir
            )
            
            logging.info(f"Extracted {len(job.extracted_images)} images from PDF")
        
        # Get video info
        job.status = "getting_info"
        job.progress = 10
        
        job.video_info = get_video_info(job.url)
        if not job.video_info:
            raise Exception("Could not get video information")
        
        # Download audio
        job.status = "downloading"
        job.progress = 20
        
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp_file:
            temp_path = tmp_file.name.replace('.mp3', '')
        
        audio_file = download_audio(job.url, temp_path)
        if not audio_file:
            raise Exception("Could not download audio")
        
        # Transcribe
        job.status = "transcribing"
        job.progress = 40
        
        # Clear any cached models and load fresh
        global whisper_model
        
        # Properly clear GPU memory
        if whisper_model is not None:
            del whisper_model
            whisper_model = None
        
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        
        # Load model fresh and store in global variable
        device = "cuda" if torch.cuda.is_available() else "cpu"
        whisper_model = whisper.load_model(job.model_size, device=device)
        model = whisper_model
        
        # Use the most optimized settings for speed
        transcript_result = model.transcribe(
            audio_file, 
            word_timestamps=True, 
            verbose=False,
            fp16=torch.cuda.is_available(),
            beam_size=1,  # Faster decoding
            best_of=1     # Faster decoding
        )
        
        job.transcript = transcript_result['text']
        topic_title = job.video_info['title']
        
        # Select relevant images if available
        selected_images = []
        if job.extracted_images:
            job.status = "analyzing_images"
            job.progress = 55
            
            temp_images_dir = os.path.join(UPLOAD_FOLDER, f"images_{job_id}")
            topic_context = f"{topic_title} {transcript_result['text'][:500]}"
            selected_images = image_analyzer.select_relevant_images(
                temp_images_dir, topic_context, max_images=6
            )
            
            # Copy selected images to static folder
            for img_info in selected_images[:]:  # Use slice copy to avoid modification during iteration
                try:
                    from urllib.parse import quote
                    dest_path = os.path.join(STATIC_IMAGES_FOLDER, img_info['filename'])
                    shutil.copy2(img_info['path'], dest_path)
                    # URL encode the filename for web path
                    encoded_filename = quote(img_info['filename'])
                    img_info['web_path'] = f"/static/images/{encoded_filename}"
                    logging.info(f"Copied image {img_info['filename']} to {dest_path}")
                except Exception as e:
                    logging.error(f"Error copying image {img_info['filename']}: {e}")
                    # Remove from selected_images if copy failed
                    selected_images.remove(img_info)
        
        # Ensure sufficient GPU memory for Ollama
        memory_available = ensure_gpu_memory_for_ollama()
        
        if not memory_available:
            logging.warning("Insufficient GPU memory for Ollama. Content generation may fail.")
        
        # Additional cleanup
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            import gc
            gc.collect()
        
        # Generate content based on type
        if job.content_type == "study_material":
            job.status = "generating_study_material"
            job.progress = 60
            
            # Generate comprehensive study material with progress tracking
            def progress_callback(section_name, progress):
                job.progress = 60 + (progress * 25 / 100)  # 60% to 85%
                job.status = f"generating_{section_name}"
            
            sections = generate_selective_study_material(
                content_generator, transcript_result['text'], topic_title, job.selected_sections, progress_callback
            )
            
            # Integrate images into sections
            if selected_images:
                sections = integrate_images_into_sections(sections, selected_images)
            
            study_material = format_study_material(sections, topic_title)
            job.study_material = study_material
            
        else:
            job.status = "summarizing"
            job.progress = 70
            
            summary = content_generator.generate_summary(transcript_result['text'], topic_title)
            job.summary = summary
        
        # Save results
        job.status = "saving"
        job.progress = 90
        
        job.files = save_results(transcript_result, job.summary, job.study_material, job.video_info, job_id, selected_images)
        job.result = {
            'transcript': transcript_result['text'],
            'summary': job.summary,
            'study_material': job.study_material,
            'language': transcript_result['language'],
            'segments_count': len(transcript_result['segments']),
            'content_type': job.content_type,
            'images_count': len(selected_images) if selected_images else 0
        }
        
        # Clean up
        try:
            os.unlink(audio_file)
            if job.pdf_file:
                os.unlink(job.pdf_file)
        except:
            pass
        
        job.status = "completed"
        job.progress = 100
        
        # Clear GPU memory after processing
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        
        # Clear the whisper model to free GPU memory for Ollama
        if whisper_model is not None:
            del whisper_model
            whisper_model = None
        
    except Exception as e:
        job.status = "error"
        error_msg = str(e)
        
        # Handle CUDA errors specifically
        if "CUDA error" in error_msg or "status code: 500" in error_msg:
            job.error = "GPU memory error. Try restarting the application or using a smaller model."
        else:
            job.error = error_msg
            
        job.progress = 0
        
        # Clear GPU memory on error
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        
        # Clear whisper model on error
        if whisper_model is not None:
            del whisper_model
            whisper_model = None

# Flask Routes
@app.route('/')
def index():
    """Main page"""
    gpu_info = get_gpu_status()
    return render_template('index.html', gpu_info=gpu_info)

@app.route('/process', methods=['POST'])
def start_processing():
    """Start video processing"""
    # Handle both JSON and form data
    if request.is_json:
        data = request.json
        url = data.get('url', '').strip()
        model_size = data.get('model', 'turbo')
        content_type = data.get('content_type', 'summary')
        selected_sections = data.get('study_sections', [])
        pdf_file_path = None
    else:
        # Handle form data with file upload
        url = request.form.get('url', '').strip()
        model_size = request.form.get('model', 'turbo')
        content_type = request.form.get('content_type', 'summary')
        
        # Get selected study material sections
        selected_sections = request.form.getlist('study_sections') if content_type == 'study_material' else []
        
        # Handle PDF file upload
        pdf_file_path = None
        if 'pdf_file' in request.files:
            file = request.files['pdf_file']
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                unique_filename = f"{timestamp}_{filename}"
                pdf_file_path = os.path.join(UPLOAD_FOLDER, unique_filename)
                file.save(pdf_file_path)
    
    if not url:
        return jsonify({'error': 'URL is required'}), 400
    
    # Check if it's a supported video URL (YouTube is primary, but allow others)
    supported_domains = ['youtube.com', 'youtu.be', 'vimeo.com', 'dailymotion.com', 'twitch.tv']
    if not any(domain in url for domain in supported_domains):
        return jsonify({'error': 'Please provide a valid video URL (YouTube, Vimeo, etc.)'}), 400
    
    # Create job
    job_id = str(uuid.uuid4())[:8]
    job = ProcessingJob(job_id, url, model_size, content_type, pdf_file_path, selected_sections)
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
        # Include the actual content in the response
        enhanced_result = job.result.copy()
        enhanced_result['summary'] = job.summary
        enhanced_result['study_material'] = job.study_material
        enhanced_result['transcript'] = job.transcript
        
        response['result'] = enhanced_result
        response['files'] = job.files
    elif job.status == 'error':
        response['error'] = job.error
    
    return jsonify(response)

@app.route('/download/<filename>')
def download_file(filename):
    """Download result file"""
    safe_filename = os.path.basename(filename)
    file_path = Path(OUTPUT_FOLDER) / safe_filename
    
    if file_path.exists() and file_path.is_file():
        return send_file(file_path, as_attachment=True, download_name=safe_filename)
    else:
        return f"File not found: {safe_filename}", 404

@app.route('/files')
def list_files():
    """List all files"""
    output_dir = Path(OUTPUT_FOLDER)
    files = []
    
    if output_dir.exists():
        for file_path in output_dir.glob("*"):
            if file_path.is_file():
                files.append({
                    'name': file_path.name,
                    'size': file_path.stat().st_size,
                    'modified': file_path.stat().st_mtime
                })
    
    return render_template('files.html', files=files)

@app.route('/gpu-status')
def gpu_status():
    """Get GPU status"""
    return jsonify(get_gpu_status())

@app.route('/process-transcript', methods=['POST'])
def start_transcript_processing():
    """Start transcript processing job"""
    transcript_text = request.form.get('transcript_text', '').strip()
    transcript_title = request.form.get('transcript_title', '').strip()
    content_type = request.form.get('transcript_content_type', 'summary')
    
    # Get selected study material sections
    selected_sections = request.form.getlist('transcript_study_sections') if content_type == 'study_material' else []
    
    if not transcript_text:
        return jsonify({'error': 'Transcript text is required'}), 400
    
    # Handle PDF file upload for images
    pdf_file_path = None
    if 'transcript_pdf_file' in request.files:
        file = request.files['transcript_pdf_file']
        if file and file.filename and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            unique_filename = f"{timestamp}_{filename}"
            pdf_file_path = os.path.join(UPLOAD_FOLDER, unique_filename)
            file.save(pdf_file_path)
    
    # Create job for transcript processing
    job_id = str(uuid.uuid4())[:8]
    job = ProcessingJob(job_id, None, None, content_type, pdf_file_path, selected_sections)
    job.transcript = transcript_text
    job.video_info = {
        'title': transcript_title or 'Direct Transcript',
        'duration': 0,
        'uploader': 'Direct Input',
        'thumbnail': '',
        'view_count': 0,
    }
    processing_jobs[job_id] = job
    
    # Start background worker for transcript processing
    thread = threading.Thread(target=process_transcript_worker, args=(job_id,))
    thread.daemon = True
    thread.start()
    
    return jsonify({'job_id': job_id})

def process_transcript_worker(job_id):
    """Background worker for transcript processing"""
    job = processing_jobs[job_id]
    content_generator = EContentGenerator()
    image_analyzer = ImageAnalyzer()
    pdf_extractor = PDFExtractor()
    
    try:
        # Extract images from PDF if provided
        if job.pdf_file:
            job.status = "extracting_images"
            job.progress = 5
            
            # Create temp directory for extracted images
            temp_images_dir = os.path.join(UPLOAD_FOLDER, f"images_{job_id}")
            os.makedirs(temp_images_dir, exist_ok=True)
            
            # Extract images from PDF
            job.extracted_images = pdf_extractor.extract_images_from_pdf(
                job.pdf_file, temp_images_dir
            )
            
            logging.info(f"Extracted {len(job.extracted_images)} images from PDF")
        
        # Update status
        job.status = "processing_transcript"
        job.progress = 20
        
        # Generate title from transcript if not provided
        if not job.video_info['title'] or job.video_info['title'] == 'Direct Transcript':
            topic_title = content_generator._generate_title(job.transcript)
            job.video_info['title'] = topic_title
        else:
            topic_title = job.video_info['title']
        
        # Select relevant images if available
        selected_images = []
        if job.extracted_images:
            job.status = "analyzing_images"
            job.progress = 35
            
            temp_images_dir = os.path.join(UPLOAD_FOLDER, f"images_{job_id}")
            topic_context = f"{topic_title} {job.transcript[:500]}"
            selected_images = image_analyzer.select_relevant_images(
                temp_images_dir, topic_context, max_images=6
            )
            
            # Copy selected images to static folder
            for img_info in selected_images[:]:  # Use slice copy to avoid modification during iteration
                try:
                    from urllib.parse import quote
                    dest_path = os.path.join(STATIC_IMAGES_FOLDER, img_info['filename'])
                    shutil.copy2(img_info['path'], dest_path)
                    # URL encode the filename for web path
                    encoded_filename = quote(img_info['filename'])
                    img_info['web_path'] = f"/static/images/{encoded_filename}"
                    logging.info(f"Copied image {img_info['filename']} to {dest_path}")
                except Exception as e:
                    logging.error(f"Error copying image {img_info['filename']}: {e}")
                    # Remove from selected_images if copy failed
                    selected_images.remove(img_info)
        
        # Update status based on content type
        if job.content_type == "study_material":
            job.status = "generating_study_material"
            job.progress = 50
            
            # Generate comprehensive study material with progress tracking
            def progress_callback(section_name, progress):
                job.progress = 50 + (progress * 35 / 100)  # 50% to 85%
                job.status = f"generating_{section_name}"
            
            sections = generate_selective_study_material(
                content_generator, job.transcript, topic_title, job.selected_sections, progress_callback
            )
            
            # Integrate images into sections
            if selected_images:
                sections = integrate_images_into_sections(sections, selected_images)
            
            study_material = format_study_material(sections, topic_title)
            job.study_material = study_material
            
            job.progress = 85
        else:
            job.status = "summarizing"
            job.progress = 70
            
            # Generate simple summary
            summary = content_generator.generate_summary(job.transcript, topic_title)
            job.summary = summary
        
        # Update status
        job.status = "saving"
        job.progress = 90
        
        # Create a mock transcript result for saving
        transcript_result = {
            'text': job.transcript,
            'language': 'auto-detected',
            'segments': []  # No segments for direct transcript
        }
        
        # Save files
        job.files = save_results(transcript_result, job.summary, job.study_material, job.video_info, job_id, selected_images)
        job.result = {
            'transcript': job.transcript,
            'summary': job.summary,
            'study_material': job.study_material,
            'language': 'auto-detected',
            'segments_count': 0,
            'content_type': job.content_type,
            'images_count': len(selected_images) if selected_images else 0
        }
        
        # Clean up
        try:
            if job.pdf_file:
                os.unlink(job.pdf_file)
        except:
            pass
        
        # Complete
        job.status = "completed"
        job.progress = 100
        
    except Exception as e:
        job.status = "error"
        job.error = str(e)
        job.progress = 0

@app.route('/static/images/<path:filename>')
def serve_image(filename):
    """Serve extracted images"""
    from urllib.parse import unquote
    
    # URL decode the filename to handle spaces and special characters
    decoded_filename = unquote(filename)
    
    # Validate the filename for security (but keep spaces and special chars)
    if '..' in decoded_filename or '/' in decoded_filename or '\\' in decoded_filename:
        return "Invalid filename", 400
    
    image_path = Path(STATIC_IMAGES_FOLDER) / decoded_filename
    
    # Log for debugging
    logging.info(f"Serving image: {decoded_filename} from {image_path}")
    
    if image_path.exists() and image_path.is_file():
        # Determine MIME type based on file extension
        ext = image_path.suffix.lower()
        mime_types = {
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.gif': 'image/gif',
            '.bmp': 'image/bmp',
            '.webp': 'image/webp'
        }
        mimetype = mime_types.get(ext, 'image/png')
        
        return send_file(image_path, mimetype=mimetype)
    else:
        logging.error(f"Image not found: {decoded_filename} at {image_path}")
        return f"Image not found: {decoded_filename}", 404

@app.route('/health')
def health():
    """Health check"""
    return jsonify({'status': 'healthy'})

if __name__ == '__main__':
    # Create directories
    Path("templates").mkdir(exist_ok=True)
    Path(OUTPUT_FOLDER).mkdir(exist_ok=True)
    
    print("🚀 Starting Video Summarizer...")
    print("🎤 Features: Video Transcription + AI Summarization")
    
    # Show GPU status
    gpu_info = get_gpu_status()
    if gpu_info['available']:
        print(f"🚀 GPU: {gpu_info['name']}")
        print(f"💾 VRAM: {gpu_info['total_memory']} total")
        print("🎯 GPU acceleration ENABLED!")
    else:
        print("⚠️  GPU not available - using CPU mode")
    
    # Get port from environment variable (for Render deployment)
    port = int(os.environ.get('PORT', 5000))
    print(f"📱 Starting server on port {port}")
    
    app.run(debug=False, host='0.0.0.0', port=port, use_reloader=False)