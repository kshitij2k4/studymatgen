#!/usr/bin/env python3
"""
Simple Summarizer Module
Provides text summarization functionality using Ollama
"""

import ollama
import logging
from typing import Optional

class SimpleSummarizer:
    """Simple text summarizer using Ollama for quick summaries"""
    
    def __init__(self, model_name: str = "llama3.2:3b"):
        """
        Initialize the summarizer with a specified model.
        
        Args:
            model_name: The Ollama model to use for summarization
        """
        self.model_name = model_name
        
    def summarize_text(self, text: str, max_length: Optional[int] = None) -> str:
        """
        Summarize the given text using Ollama.
        
        Args:
            text: The text to summarize
            max_length: Maximum length of the summary (optional)
            
        Returns:
            The summarized text
        """
        # Determine summary length instruction
        length_instruction = ""
        if max_length:
            if max_length <= 100:
                length_instruction = "Keep it very brief (1-2 sentences)."
            elif max_length <= 300:
                length_instruction = "Keep it concise (2-3 sentences)."
            elif max_length <= 500:
                length_instruction = "Provide a moderate summary (1-2 paragraphs)."
            else:
                length_instruction = "Provide a comprehensive summary (2-3 paragraphs)."
        else:
            length_instruction = "Provide a clear, informative summary."
        
        prompt = f"""Please provide a concise summary of the following text. {length_instruction}

Text to summarize:
{text[:4000]}...

Summary:"""

        try:
            response = ollama.generate(
                model=self.model_name,
                prompt=prompt,
                options={
                    'temperature': 0.7,
                    'top_p': 0.9,
                    'max_tokens': max_length or 500
                }
            )
            
            result = response['response'].strip()
            return result if result else "Unable to generate summary."
            
        except Exception as e:
            logging.error(f"Error generating summary: {e}")
            return f"Error generating summary: {str(e)}"
    
    def summarize_with_key_points(self, text: str) -> dict:
        """
        Generate both a summary and key points.
        
        Args:
            text: The text to summarize
            
        Returns:
            Dict containing 'summary' and 'key_points'
        """
        # Generate summary
        summary = self.summarize_text(text, max_length=400)
        
        # Generate key points
        key_points_prompt = f"""Based on the following text, extract 5-7 key points in bullet format:

{text[:3000]}...

Key Points:
-"""

        try:
            response = ollama.generate(
                model=self.model_name,
                prompt=key_points_prompt,
                options={
                    'temperature': 0.7,
                    'top_p': 0.9,
                    'max_tokens': 300
                }
            )
            
            key_points = response['response'].strip()
            if not key_points.startswith('-'):
                key_points = "- " + key_points
            
        except Exception as e:
            logging.error(f"Error generating key points: {e}")
            key_points = "Unable to generate key points."
        
        return {
            'summary': summary,
            'key_points': key_points
        }
    
    def quick_summary(self, text: str) -> str:
        """
        Generate a very brief summary (1-2 sentences).
        
        Args:
            text: The text to summarize
            
        Returns:
            Brief summary
        """
        return self.summarize_text(text, max_length=100)
    
    def detailed_summary(self, text: str) -> str:
        """
        Generate a detailed summary (2-3 paragraphs).
        
        Args:
            text: The text to summarize
            
        Returns:
            Detailed summary
        """
        return self.summarize_text(text, max_length=800)

def main():
    """Test the SimpleSummarizer"""
    summarizer = SimpleSummarizer()
    
    test_text = """
    Artificial Intelligence (AI) is a branch of computer science that aims to create 
    intelligent machines that work and react like humans. Some of the activities 
    computers with artificial intelligence are designed for include speech recognition, 
    learning, planning, and problem solving. AI is being used in various industries 
    including healthcare, finance, transportation, and entertainment. Machine learning, 
    a subset of AI, enables computers to learn automatically and improve from experience 
    without being explicitly programmed. Deep learning, which is part of machine learning, 
    uses neural networks with multiple layers to analyze various factors of data.
    """
    
    print("🤖 SimpleSummarizer Test")
    print("=" * 50)
    print("Original text:")
    print(test_text)
    print("\n" + "=" * 50)
    
    # Test different summary types
    print("Quick Summary:")
    print(summarizer.quick_summary(test_text))
    
    print("\nDetailed Summary:")
    print(summarizer.detailed_summary(test_text))
    
    print("\nSummary with Key Points:")
    result = summarizer.summarize_with_key_points(test_text)
    print("Summary:", result['summary'])
    print("Key Points:", result['key_points'])

if __name__ == '__main__':
    main()