from PIL import Image
import os

# Get the current directory
base_dir = os.getcwd()

# Compress images in fulls and thumbs directories
for folder in [r'images\gallery\fulls', r'images\gallery\thumbs']:
    folder_path = os.path.join(base_dir, folder)
    if not os.path.exists(folder_path):
        print(f"Folder not found: {folder_path}")
        continue
    
    for filename in os.listdir(folder_path):
        if filename.endswith('.jpg'):
            filepath = os.path.join(folder_path, filename)
            img = Image.open(filepath)
            
            # Convert RGBA to RGB if needed
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')
            
            # Compress with quality reduction
            img.save(filepath, 'JPEG', quality=75, optimize=True)
            
            new_size = os.path.getsize(filepath)
            print(f"Compressed {filename}: {new_size} bytes")

print("All images compressed successfully!")
