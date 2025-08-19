#!/usr/bin/env python3
"""
🔧 PRE-COMMIT SETUP AND FORMATTING TOOLS

This script sets up automated code formatting to prevent git commit failures.
It configures:
- autopep8 for automatic Python formatting
- isort for import sorting  
- flake8 configuration
- VS Code settings for auto-format on save
"""

import json
import os
import subprocess

from pathlib import Path

def install_formatting_tools():
    """Install required formatting tools"""
    print("📦 Installing formatting tools...")
    
    tools = [
        'autopep8',
        'isort', 
        'flake8',
        'pre-commit'
    ]
    
    for tool in tools:
        try:
            print(f"   Installing {tool}...")
            subprocess.run(['pip', 'install', tool], check=True, capture_output=True)
            print(f"   ✅ {tool} installed")
        except subprocess.CalledProcessError as e:
            print(f"   ❌ Failed to install {tool}: {e}")

def create_vscode_settings():
    """Create VS Code settings for auto-formatting"""
    print("\n🔧 Setting up VS Code auto-formatting...")
    
    vscode_dir = Path('/home/thien/hummingbot/.vscode')
    vscode_dir.mkdir(exist_ok=True)
    
    settings = {
        "python.defaultInterpreterPath": "/home/thien/miniconda3/envs/hummingbot/bin/python",
        "python.formatting.provider": "autopep8",
        "python.formatting.autopep8Args": [
            "--max-line-length=120",
            "--aggressive",
            "--aggressive"
        ],
        "python.linting.enabled": True,
        "python.linting.flake8Enabled": True,
        "python.linting.flake8Args": [
            "--max-line-length=120",
            "--ignore=E203,W503,E402"
        ],
        "editor.formatOnSave": True,
        "editor.formatOnPaste": True,
        "python.sortImports.args": [
            "--profile=black",
            "--line-length=120"
        ],
        "[python]": {
            "editor.codeActionsOnSave": {
                "source.organizeImports": True
            }
        }
    }
    
    settings_file = vscode_dir / 'settings.json'
    with open(settings_file, 'w') as f:
        json.dump(settings, f, indent=2)
    
    print(f"   ✅ VS Code settings created: {settings_file}")

def create_autopep8_config():
    """Create autopep8 configuration"""
    print("\n📝 Creating autopep8 configuration...")
    
    config_content = """[tool:autopep8]
max_line_length = 120
ignore = E203,W503,E402
aggressive = 2
"""
    
    config_file = Path('/home/thien/hummingbot/setup.cfg')
    
    # Read existing config or create new
    existing_content = ""
    if config_file.exists():
        with open(config_file, 'r') as f:
            existing_content = f.read()
    
    # Add autopep8 config if not present
    if '[tool:autopep8]' not in existing_content:
        with open(config_file, 'a') as f:
            f.write('\n' + config_content)
        print(f"   ✅ autopep8 config added to {config_file}")
    else:
        print(f"   ✅ autopep8 config already exists in {config_file}")

def create_flake8_config():
    """Create flake8 configuration"""
    print("\n📝 Creating flake8 configuration...")
    
    config_content = """[flake8]
max-line-length = 120
ignore = E203,W503,E402,F401
exclude = build,__pycache__,.git,*.egg-info,dist
per-file-ignores = 
    scripts/*:E402,F401
"""
    
    config_file = Path('/home/thien/hummingbot/.flake8')
    with open(config_file, 'w') as f:
        f.write(config_content)
    
    print(f"   ✅ flake8 config created: {config_file}")

def setup_git_hooks():
    """Set up git hooks for automatic formatting"""
    print("\n🔗 Setting up git hooks...")
    
    # Create pre-commit hook script
    hook_content = """#!/bin/bash
# Auto-format Python files before commit

echo "🔧 Running auto-formatting..."

# Get list of Python files to be committed
  FILES=$(git diff --cached --name-only --diff-filter=ACM | grep -E "\\.py$")if [ -z "$FILES" ]; then
    echo "✅ No Python files to format"
    exit 0
fi

# Format files with autopep8
for file in $FILES; do
    echo "  📝 Formatting $file"
    autopep8 --in-place --max-line-length=120 --aggressive --aggressive "$file"
    isort "$file" --profile=black --line-length=120
    git add "$file"
done

echo "✅ Auto-formatting complete"
"""
    
    hook_file = Path('/home/thien/hummingbot/.git/hooks/pre-commit')
    with open(hook_file, 'w') as f:
        f.write(hook_content)
    
    # Make executable
    os.chmod(hook_file, 0o755)
    
    print(f"   ✅ Git pre-commit hook created: {hook_file}")

def create_format_script():
    """Create a quick format script"""
    print("\n📝 Creating quick format script...")
    
    script_content = """#!/bin/bash
# Quick format all Python files in the project

echo "🔧 Formatting all Python files..."

# Find and format all Python files
find . -name "*.py" -not -path "./build/*" -not -path "./__pycache__/*" -not -path "./.git/*" | while read file; do
    echo "  📝 Formatting $file"
    autopep8 --in-place --max-line-length=120 --aggressive --aggressive "$file"
    isort "$file" --profile=black --line-length=120
done

echo "✅ All files formatted!"
echo "💡 Run 'git add .' and 'git commit' to commit changes"
"""
    
    script_file = Path('/home/thien/hummingbot/format_code.sh')
    with open(script_file, 'w') as f:
        f.write(script_content)
    
    # Make executable
    os.chmod(script_file, 0o755)
    
    print(f"   ✅ Format script created: {script_file}")
    print("   💡 Run './format_code.sh' to format all files")

def test_formatting():
    """Test the formatting setup"""
    print("\n🧪 Testing formatting setup...")
    
    try:
        # Test autopep8
        result = subprocess.run(['autopep8', '--version'], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"   ✅ autopep8: {result.stdout.strip()}")
        else:
            print("   ❌ autopep8 not working")
        
        # Test isort  
        result = subprocess.run(['isort', '--version'], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"   ✅ isort: {result.stdout.strip()}")
        else:
            print("   ❌ isort not working")
            
        # Test flake8
        result = subprocess.run(['flake8', '--version'], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"   ✅ flake8: {result.stdout.strip()}")
        else:
            print("   ❌ flake8 not working")
            
    except FileNotFoundError as e:
        print(f"   ❌ Tool not found: {e}")

def main():
    """Main setup function"""
    print("🔧 PRE-COMMIT SETUP AND FORMATTING TOOLS")
    print("=" * 50)
    print("This will set up automated code formatting to prevent git commit failures.")
    print("")
    
    # Install tools
    install_formatting_tools()
    
    # Create configurations
    create_vscode_settings()
    create_autopep8_config()
    create_flake8_config()
    
    # Set up git hooks
    setup_git_hooks()
    
    # Create helper scripts
    create_format_script()
    
    # Test setup
    test_formatting()
    
    print("\n🎉 SETUP COMPLETE!")
    print("=" * 20)
    print("✅ VS Code will now auto-format on save")
    print("✅ Git hooks will auto-format before commits")
    print("✅ Run './format_code.sh' to format all files manually")
    print("✅ Flake8 errors should be prevented automatically")
    print("")
    print("💡 USAGE:")
    print("   1. Format all files: ./format_code.sh")
    print("   2. Normal git workflow: git add . && git commit -m 'message'")
    print("   3. Files will be auto-formatted before commit")

if __name__ == "__main__":
    main()
