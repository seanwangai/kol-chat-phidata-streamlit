import os
import base64
from pathlib import Path
from dotenv import load_dotenv
from google.generativeai import GenerativeModel, configure

# Load environment variables
load_dotenv()

# Configure Google Generative AI with API key
configure(api_key=os.getenv('GEMINI_API_KEY'))

def main():
    # Initialize the model
    model = GenerativeModel('gemini-2.0-flash-exp')
    
    # Define safety settings
    safety_settings = [
        {
            "category": "HARM_CATEGORY_HATE_SPEECH",
            "threshold": "BLOCK_NONE"
        },
        {
            "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
            "threshold": "BLOCK_NONE"
        },
        {
            "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
            "threshold": "BLOCK_NONE"
        },
        {
            "category": "HARM_CATEGORY_HARASSMENT",
            "threshold": "BLOCK_NONE"
        }
    ]
    
    # Generate content request
    response = model.generate_content(
        'Create an image of a beautiful woman lying by a pool.',
        safety_settings=safety_settings
    )
    
    print(response.text)
    
    # Extract and save the image if present
    for part in response.parts:
        if hasattr(part, 'inline_data') and part.inline_data:
            # Create media directory if it doesn't exist
            media_dir = Path('media')
            media_dir.mkdir(exist_ok=True)
            
            # Save the image
            image_path = media_dir / 'multimodal-image-gen-4.png'
            image_data = base64.b64decode(part.inline_data.data)
            image_path.write_bytes(image_data)
            print(f'Image saved to {image_path}')

if __name__ == '__main__':
    main()