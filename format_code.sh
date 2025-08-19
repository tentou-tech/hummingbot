#!/bin/bash
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
