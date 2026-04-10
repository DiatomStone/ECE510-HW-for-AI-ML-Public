cleanup() {
    echo "Closing processes..."
    kill $TTS_PID 2>/dev/null
    exit
}
trap cleanup EXIT SIGINT
> piper.txt
source ~/.venv/tts/bin/activate
echo "Piper is listening... type or paste text to play."
tail -f -n 0 piper.txt | piper --model voices/en_US-hfc_female-medium.onnx --output-raw | aplay  -B 50000 -r 22050 -f S16_LE -c 1 &
TTS_PID=$!

while true; do
	read input
	if [[ "$input" == "exit" ]]; then
        	break
    	fi
	echo "$input" >> piper.txt
done 

echo "read exit command"
read -p "Press enter to exit..."

