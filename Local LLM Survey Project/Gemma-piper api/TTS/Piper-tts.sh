source ~/.venv/tts/bin/activate
echo "Enter filename (without .txt):"
read file_name
cat "$file_name.txt" | piper --model voices/en_US-hfc_female-medium.onnx --output_file "output/$file_name.wav"
ffmpeg -i output/$file_name.wav -codec:a libmp3lame -b:a 64k output/$file_name.mp3
rm output/$file_name.wav
echo "piper tts finished!"
read -p "Press enter to exit..."
