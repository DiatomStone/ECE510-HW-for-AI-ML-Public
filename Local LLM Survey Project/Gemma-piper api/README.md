# README
## No-responsibility Disclaimer
No responsibility taken if any files damage your system or hardware 
inspect and use at your own disgression. 

## Prerequisites
ollama  
gemma4 e4b  
piper-tts  
piper voices (both .onnx and .json) put in TTS/voices. 
aplay, realtime audio output for linux

## Install Prerequisites

### Piper Voices
~[piper-samples](https://rhasspy.github.io/piper-samples/#en_US-hfc_female-medium)
put in... 
TTS/voices/en_US-hfc_female-medium.onnx.json
TTS/voices/en_US-hfc_female-medium.onnx
### piper-tts
```
python3 -m venv ~/.venv/tts
source ~/.venv/tts/bin/activate
pip install piper-tts
echo 'Hello world' | piper --model en_US-hfc_female-medium.onx --output_file test.wav
```
### local llm
```
curl -fsSL https://ollama.com/install.sh | sh
ollama pull gemma4:e4b
ollama list
```
### aplay
```
sudo apt install alsa-utils
```

## Run
gemma interface wrapper in Gemma_4 folder
```
./gemma.sh
```

Realtime piper read aloud in TTS folder
```
./Piper_rttts.sh
```

## gemma.sh  

|Comand | example, prompt w/o quotation ""| function| 
|:----|:----|:----|
|bye         ||exit |
|FORGET      ||delete context|
|STATUS      ||ollama ps (see status)|
|CODE        |"CODE c make a 4 -bit adder"| suports c python cli, ask gemma to output code then copies to file in Gemma_4/code|
|READ        |"READ cli"|Read the program in Gemma_4/code|
|RUN         |"RUN c", "RUN python" |runs the program in Gemma_4/code|
|IMAGE      |"IMAGE who painted this picture"| tells gema to read the image in Gemma_4/input|

