source ~/.venv/tts/bin/activate
echo "Enter filename (without .txt):"
read file_name
edge-tts --file "$file_name.txt" --write-media "output/$file_name.mp3"
read -p "Press Enter to exit..."
