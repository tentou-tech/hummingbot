#!/usr/bin/env python3
"""
Fix Flake8 errors specifically in our project files (not external dependencies)
"""

import subprocess
import re
import os



def run_flake8_on_project():
    """Run flake8 only on project files, excluding .venv and other external directories"""
    
    # Directories to check (our project code)
    project_dirs = [
        "hummingbot/",
        "scripts/",
        "test/",
        "controllers/",
        "bin/"
    ]
    
    # Files in root directory to check
    root_files = [
        "setup.py",
        "*.py"  # Any Python files in root
    ]
    
    cmd = ["flake8"] + project_dirs + root_files + [
        "--exclude=.venv,build,__pycache__,.git,.tox,dist,*.egg-info",
        "--max-line-length=120",
        "--ignore=E203,W503,E722",  # Ignore some common issues
        "--format=%(path)s:%(row)d:%(col)d: %(code)s %(text)s"
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd="/home/thien/hummingbot")
        return result.stdout, result.stderr, result.returncode
    except Exception as e:
        return "", str(e), 1


def fix_common_errors(file_path, errors):
    """Fix common Flake8 errors in a file"""
    
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return False
    
    try:
        with open(file_path, 'r') as f:
            content = f.read()
        
        original_content = content
        changes_made = False
        
        for error in errors:
            line_num = error.get('line', 0)
            error_code = error.get('code', '')
            
            if error_code == 'F401':  # Unused import
                # Remove the unused import line
                lines = content.split('\n')
                if 0 < line_num <= len(lines):
                    import_line = lines[line_num - 1]
                    # Only remove if it's clearly an import line
                    if import_line.strip().startswith(('import ', 'from ')):
                        lines[line_num - 1] = ''  # Remove the line
                        content = '\n'.join(lines)
                        changes_made = True
            
            elif error_code == 'F541':  # f-string missing placeholders
                # Convert f-strings without placeholders to regular strings
                lines = content.split('\n')
                if 0 < line_num <= len(lines):
                    line = lines[line_num - 1]
                    # Find f-strings and convert to regular strings if no placeholders
                    if 'f"' in line and '{' not in line:
                        lines[line_num - 1] = line.replace('f"', '"')
                        content = '\n'.join(lines)
                        changes_made = True
                    elif "f'" in line and '{' not in line:
                        lines[line_num - 1] = line.replace("f'", "'")
                        content = '\n'.join(lines)
                        changes_made = True
        
        if changes_made:
            with open(file_path, 'w') as f:
                f.write(content)
            print(f"✓ Fixed errors in {file_path}")
            return True
        else:
            print(f"- No automatic fixes applied to {file_path}")
            return False
            
    except Exception as e:
        print(f"✗ Error processing {file_path}: {e}")
        return False


def parse_flake8_output(output):
    """Parse flake8 output into structured format"""
    
    errors_by_file = {}
    
    for line in output.strip().split('\n'):
        if not line:
            continue
            
        # Parse: filepath:line:col: code message
        match = re.match(r'^([^:]+):(\d+):(\d+):\s+([A-Z]\d+)\s+(.+)$', line)
        if match:
            filepath, line_num, col_num, code, message = match.groups()
            
            if filepath not in errors_by_file:
                errors_by_file[filepath] = []
            
            errors_by_file[filepath].append({
                'line': int(line_num),
                'col': int(col_num),
                'code': code,
                'message': message
            })
    
    return errors_by_file


def main():
    """Main function to check and fix project Flake8 errors"""
    
    print("🔍 Checking Flake8 errors in project files...")
    
    # Run flake8 on project files only
    stdout, stderr, returncode = run_flake8_on_project()
    
    if returncode == 0:
        print("✅ No Flake8 errors found in project files!")
        return
    
    if stderr:
        print(f"⚠️  Flake8 stderr: {stderr}")
    
    if not stdout:
        print("⚠️  No Flake8 output to process")
        return
    
    # Parse the errors
    errors_by_file = parse_flake8_output(stdout)
    
    print(f"\n📊 Found errors in {len(errors_by_file)} files:")
    
    total_errors = 0
    fixed_files = 0
    
    for filepath, errors in errors_by_file.items():
        total_errors += len(errors)
        print(f"\n📁 {filepath} ({len(errors)} errors):")
        
        for error in errors[:5]:  # Show first 5 errors
            print(f"   Line {error['line']}: {error['code']} {error['message']}")
        
        if len(errors) > 5:
            print(f"   ... and {len(errors) - 5} more errors")
        
        # Try to fix common errors
        if fix_common_errors(filepath, errors):
            fixed_files += 1
    
    print("\n📈 Summary:")
    print(f"   Total files with errors: {len(errors_by_file)}")
    print(f"   Total errors: {total_errors}")
    print(f"   Files with automatic fixes applied: {fixed_files}")
    
    # Re-run flake8 to see remaining issues
    print("\n🔄 Re-checking after fixes...")
    stdout, stderr, returncode = run_flake8_on_project()
    
    if returncode == 0:
        print("✅ All project Flake8 errors fixed!")
    else:
        remaining_errors = parse_flake8_output(stdout)
        print(f"⚠️  {len(remaining_errors)} files still have errors that need manual fixing")
        
        # Show the specific files that still need work
        for filepath in remaining_errors:
            print(f"   - {filepath}")


if __name__ == "__main__":
    main()
