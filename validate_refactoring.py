"""
Syntax and structure validation test for refactored code
This test checks that all files compile correctly without importing dependencies
"""

import py_compile
import os

print("="*60)
print("REFACTORING VALIDATION TEST")
print("="*60)

files_to_test = [
    ("app.py", "Main application file"),
    ("src/ui/supervisor.py", "Supervisor UI module"),
    ("src/email_service.py", "Email service module"),
    ("src/ai.py", "AI functions module"),
    ("src/roompact.py", "Roompact API module"),
]

all_passed = True

for filepath, description in files_to_test:
    try:
        print(f"\n✓ Testing {description}...")
        print(f"  File: {filepath}")
        py_compile.compile(filepath, doraise=True)
        print(f"  ✅ Syntax check passed")
        
        # Check file size
        size = os.path.getsize(filepath)
        print(f"  Size: {size:,} bytes")
        
    except py_compile.PyCompileError as e:
        print(f"  ✗ Syntax error: {e}")
        all_passed = False
    except FileNotFoundError:
        print(f"  ✗ File not found")
        all_passed = False

print("\n" + "="*60)

# Check that functions were removed from app.py
print("\nVerifying functions were removed from app.py...")
with open('app.py', 'r', encoding='utf-8') as f:
    app_content = f.read()
    
removed_functions = [
    'def extract_und_leads_section',
    'def supervisor_summaries_page',
    'def supervisors_section_page',
    'def duty_analysis_section',
    'def engagement_analysis_section',
    'def general_form_analysis_section',
]

for func in removed_functions:
    if func in app_content:
        print(f"  ✗ WARNING: '{func}' still found in app.py (should be removed)")
        all_passed = False
    else:
        print(f"  ✓ '{func}' correctly removed from app.py")

# Check that imports were added to app.py
print("\nVerifying imports were added to app.py...")
required_imports = [
    'from src.ui.supervisor import',
    'from src.email_service import',
    'from src.roompact import discover_form_types',
]

for imp in required_imports:
    if imp in app_content:
        print(f"  ✓ Import found: '{imp}'")
    else:
        print(f"  ✗ WARNING: Import missing: '{imp}'")
        all_passed = False

# Check that functions exist in new modules
print("\nVerifying functions exist in new modules...")

with open('src/email_service.py', 'r', encoding='utf-8') as f:
    email_content = f.read()
    if 'def extract_und_leads_section' in email_content:
        print("  ✓ extract_und_leads_section found in src/email_service.py")
    else:
        print("  ✗ extract_und_leads_section NOT found in src/email_service.py")
        all_passed = False

with open('src/ui/supervisor.py', 'r', encoding='utf-8') as f:
    supervisor_content = f.read()
    supervisor_functions = [
        'def supervisor_summaries_page',
        'def supervisors_section_page',
        'def duty_analysis_section',
        'def engagement_analysis_section',
        'def general_form_analysis_section',
    ]
    for func in supervisor_functions:
        if func in supervisor_content:
            print(f"  ✓ {func.replace('def ', '')} found in src/ui/supervisor.py")
        else:
            print(f"  ✗ {func.replace('def ', '')} NOT found in src/ui/supervisor.py")
            all_passed = False

print("\n" + "="*60)
if all_passed:
    print("✅ ALL TESTS PASSED - Refactoring successful!")
    print("\nNext steps:")
    print("1. Install Streamlit: pip install streamlit")
    print("2. Run the app: streamlit run app.py")
    print("3. Test the Supervisors Section in the UI")
else:
    print("❌ SOME TESTS FAILED - Please review the warnings above")
print("="*60)
