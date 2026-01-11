
import sys

def patch():
    path = 'app/templates/projects/form.html'
    try:
        with open(path, 'r') as f:
            lines = f.readlines()
        
        new_lines = []
        skip_next = False
        
        for i, line in enumerate(lines):
            if skip_next:
                skip_next = False
                continue
                
            if 'const isEdit = {{ "true" if project else "false" }' in line:
                # Found the broken line
                # Check if it lacks the closing };
                if '};' not in line:
                    print(f"Fixing broken line {i+1}")
                    # Construct fixed line keeping indentation
                    indent = line[:line.find('const')]
                    fixed_line = indent + 'const isEdit = {{ "true" if project else "false" }};\n'
                    new_lines.append(fixed_line)
                    
                    # Check if next line is the stray };
                    if i + 1 < len(lines):
                        next_line = lines[i+1].strip()
                        if next_line == '};':
                            print(f"Removing stray closing brace at line {i+2}")
                            skip_next = True
                    continue
            
            new_lines.append(line)
            
        with open(path, 'w') as f:
            f.writelines(new_lines)
            print("File patched successfully.")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    patch()
