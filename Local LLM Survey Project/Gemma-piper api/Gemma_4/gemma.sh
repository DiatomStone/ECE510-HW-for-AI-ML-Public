gemma() {
    # Combine your global rules file + the specific prompt
    echo -e "\nUser: $*" >> context.md
    (cat AGENT.md; tail -n 100 context.md)| \
    ollama run gemma4:e4b --think=false| \
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
    echo "test..."
    tail -f -n 0 ../TTS/piper.txt | \
    piper --model ../TTS/voices/en_US-hfc_female-medium.onnx --output-raw | \
    aplay -B 50000 -r 22050 -f S16_LE -c 1 > /dev/null 2>&1 &
    PIPER_PID=$!
    echo "Piper engine started (PID: $PIPER_PID). Append text to piper.txt to speak."
}

cleanup() {
	echo "Closing PIPER TTS..."
	[[ -n "$PIPER_PID" ]] && kill $PIPER_PID 2>/dev/null
}


trap cleanup EXIT SIGINT
echo "starting system..."
start_piper_tts
echo "Greetings gemma!" | ollama run gemma4:e4b --think=false 

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
