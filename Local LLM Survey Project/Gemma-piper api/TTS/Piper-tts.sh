piper="voices/en_US-hfc_female-medium.onnx"
alba="voices/en_GB-alba-medium.onnx"
alan="voices/en_GB-alan-medium.onnx"
lessac="voices/en_US-lessac-medium.onnx"
default="voices/en_US-libritts_r-medium.onnx"

reformat_txt(){
sed ':a;N;$!ba; s/-\n//g' "$1".txt | tee "$1".tmp
}

source ~/.venv/tts/bin/activate
read -p "Enter filename (without .txt): " file_name
read -p "Enter voice actor: " voice

reformat_txt input/$file_name

case "$voice" in
    	"alan")
        voice=$alan
        ;;
	"alba")
        voice=$alba
        ;;
        "lessac")
        voice=$lessac
        ;;
        "piper")
        voice=$piper
        ;;
        *)
        voice=$default
        ;;
esac
cat input/"$file_name.tmp" | piper --model "$voice" --sentence-silence 0.4 --output_file "output/$file_name.wav"
ffmpeg -i "output/$file_name.wav" -codec:a libmp3lame -b:a 64k "output/$file_name.mp3"
rm "output/$file_name.wav" "input/$file_name.tmp"
echo "piper tts finished!"
read -p "Press enter to exit..."
