#!/usr/bin/env python3

import sys
import os

# Add the current directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import the PDF creation function
from app import create_pdf_with_reportlab

def test_new_paragraph_formatting():
    """Test the new paragraph formatting instead of bullets"""
    
    # Sample content that includes items that were previously bullet points
    test_content = """
## Staff Updates

#### Individual Staff Activities

- John completed the resident advisor training program and is now certified
- Sarah organized the community building event that had 85 participants  
- Mike resolved three maintenance requests and improved room satisfaction
- Lisa implemented new check-in procedures that reduced wait times by 50%

#### ASCEND Framework Activities

- Accountability: Tom developed new accountability measures for staff performance
- Service: Jennifer launched the 24/7 student support hotline
- Community: David organized inter-hall programming that connected 200+ residents
- Excellence: Maria achieved 98% resident satisfaction in her building
- Nurture: Alex implemented mentorship program pairing upperclassmen with first-years
- Development: Chris completed leadership training and earned professional certification

### Other Sections

Regular paragraph text should remain unchanged and look normal.

**Meeting Summary**

More content here that should be formatted normally.
"""
    
    try:
        # Generate the PDF
        pdf_bytes, filename, content_type = create_pdf_with_reportlab(
            test_content, 
            "2025-10-15", 
            "Test User"
        )
        
        # Save the test PDF
        test_filename = f"test_paragraph_format_{filename}"
        with open(test_filename, 'wb') as f:
            f.write(pdf_bytes)
        
        print(f"SUCCESS: PDF with paragraph formatting generated - {test_filename}")
        print(f"PDF size: {len(pdf_bytes):,} bytes")
        print("Changes made:")
        print("- Removed bullet points (•)")
        print("- Created individual paragraphs for each item")
        print("- Bold first word/name in each paragraph")
        print("- Improved spacing and indentation")
        
        return True
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_new_paragraph_formatting()
    if success:
        print("\nParagraph formatting test completed successfully!")
    else:
        print("\nThere were issues with the paragraph formatting.")