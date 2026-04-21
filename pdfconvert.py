# Pdf to rtf converter
"""
PDF TO RTF CONVERTER
--------------------
A utility to convert PDF documents into RTF (Rich Text Format) files
compatible with Wordpad. It preserves layout, formatting, and images.

Note: This script requires 'aspose-words' installed.
Installation: pip install aspose-words
"""

import os
import sys

# Check for aspose-words installation
try:
    import aspose.words as aw
except ImportError:
    print("\033[91mError: The 'aspose-words' library is not installed.\033[0m")
    print("Please install it using: pip install aspose-words")
    sys.exit(1)

# ANSI Color Codes
class Colors:
    PURPLE = '\033[38;2;170;0;255m'
    GREEN = '\033[38;2;0;255;0m'
    YELLOW = '\033[38;2;255;255;0m'
    RED = '\033[38;2;255;0;0m'
    BOLD = '\033[1m'
    END = '\033[0m'

def convert_pdf_to_rtf(input_path):
    # Initialize Windows console
    if os.name == 'nt':
        os.system('')

    print(f"\n{Colors.PURPLE}{Colors.BOLD}--- PDF TO RTF CONVERSION ---{Colors.END}")
    
    if not os.path.exists(input_path):
        print(f"{Colors.RED}Error: File '{input_path}' not found.{Colors.END}")
        return

    if not input_path.lower().endswith('.pdf'):
        print(f"{Colors.RED}Error: Input file must be a .pdf{Colors.END}")
        return

    output_path = os.path.splitext(input_path)[0] + ".rtf"

    try:
        print(f"{Colors.YELLOW}Loading PDF...{Colors.END}")
        # Load the PDF document
        doc = aw.Document(input_path)
        
        print(f"{Colors.YELLOW}Converting to RTF...{Colors.END}")
        # Save as RTF
        doc.save(output_path)
        
        print(f"\n{Colors.GREEN}{Colors.BOLD}Success!{Colors.END}")
        print(f"{Colors.PURPLE}Saved to:{Colors.END} {output_path}\n")

    except Exception as e:
        print(f"\033[91mConversion failed: {e}{Colors.END}")

if __name__ == "__main__":
    # Check if file was dragged onto script or passed as argument
    if len(sys.argv) > 1:
        convert_pdf_to_rtf(sys.argv[1])
    else:
        print(f"{Colors.PURPLE}{Colors.BOLD}=== CATRO PDF CONVERTER ==={Colors.END}")
        path = input(f"\n{Colors.YELLOW}Enter full path to PDF file: {Colors.END}").strip('"')
        convert_pdf_to_rtf(path)