voice="en_US-libritts_r-medium.onnx"
mode=(gemma4:e4b gemma4:26b-a4b-it-q4_K_M ministral-3:8b)
speaker=(en_US-libritts-high.onnx en_US-ljspeech-high.onnx en_GB-cori-high.onnx)
model=${mode[0]}
gemma() {
    # Combine your global rules file + the specific prompt
    echo -e "\nUser: $*" >> context.md
    (cat AGENT.md; tail -n 100 context.md)| \
    ollama run "$model" --think=false| \
    sed -E 's/[a-zA-Z0-9]*(\x1b\[[0-9;]*[a-zA-Z])+//g' | \
    tee -a ../TTS/piper.txt
}

write_code() {
	echo "Writing generated code..."
    	case $1 in 
    "cli")
    	cp ../TTS/piper.txt code/CLI.sh
    	;;
    "c")
    	cp ../TTS/piper.txt code/program.c
    	;;
    "python")
    	cp ../TTS/piper.txt code/application.py
    	;;
    *)
    	echo "not supported format"
    	;;
    esac 
}

read_code(){
	echo "Reading generated code..."
    	case $1 in 
    "cli")
    	cat code/CLI.sh
    	;;
    "c")
    	cat code/program.c
    	;;
    "python")
    	cat code/application.py
    	;;
    *)
    	echo "not supported format"
    	;;
    esac 
}

run_code(){
	read -p "Are you sure? [y/n] " check0
	if [[ "$check0" != "y" ]]; then 
		echo "smart."
		return
	fi
	read -p "Absolutely sure? [y/n] " check1
	if [[ "$check1" != "y" ]]; then 
		echo "smart."
		return
	fi
	
	
	read -p "Here goes... sorry if it breaks anything. [Enter]"
	case $1 in 
    "cli")
    	./code/CLI.sh
    	;;
    "c")
	cd code
    	make
	cd ..
	./code/program
    	;;
    "python")
    	python3 code/application.py
    	;;
    *)
    	echo "not supported format"
    	;;
    esac 
}

start_piper_tts() {
    source ~/.venv/tts/bin/activate

    # Clear the file
    > ../TTS/piper.txt
    
    # Start the listener in the background
    tail -f -n 0 ../TTS/piper.txt | \
    piper --model ../TTS/voices/$voice --sentence-silence 0.4 --output-raw | \
    aplay -B 50000 -r 22050 -f S16_LE -c 1 2> /dev/null  &
    PIPER_PID=$!
    echo "Piper engine started (PID: $PIPER_PID). Append text to piper.txt to speak."
}

cleanup() {
	>context.md
	echo "Closing PIPER TTS..."
	[[ -n "$PIPER_PID" ]] && kill $PIPER_PID 2>/dev/null
}


trap cleanup EXIT SIGINT

echo -e "[enter]\tgemma4_e4b\n[1]\tgemma_26b_Q4\n[2]\tministral_3_8b"
read -p "Select model:  " choice

case "$choice" in
	"1")
	 model=${mode[1]}
	 voice=${speaker[1]}
	 ;;
	"2")
	 model=${mode[2]}
	 voice=${speaker[2]}
	 ;;
	*)
	 model=${mode[0]}
	 voice=${speaker[0]}
	 ;;
esac
start_piper_tts
echo -e "Model : $model\nVoice : $voice"
#warm up
echo "warm up greetings, do not reply wait for next prompt" | ollama run "$model" --think=false 

echo "type 'bye' to stop" 
while true; do 
	echo; read -p ">> Prompt: " message; echo 
	[[ -z "$message" ]] && continue  # Skip empty enters

    # Extract the first word as the command
    cmd=$(echo "$message" | cut -d' ' -f1)
    # Extract everything AFTER the first word as the arguments/prompt
    args=$(echo "$message" | cut -d' ' -f2-)
    args=${args,,}

	case "$cmd" in
    "STATUS")
        ollama ps
        ;;
    "FORGET")
        >context.md
        ;;
    "bye")
    	break;
    	;;
    "CODE")
    	>../TTS/piper.txt
    	gemma "$message"
    	write_code $args
    	;;
    "READ")
    	read_code $args
    	;;
    "RUN")
        run_code $args
    	;;
    "IMAGE")
    	image="$message. describe this image: /home/systemuser/Documents/Tools/Gemma_4/inputs/Pasted image.png"
    	gemma "$image"
    	;;
    *)
        # Default case (wildcard) 
	gemma "$message"
        ;;
esac

done
cleanup
