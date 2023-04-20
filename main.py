import os
import socket
import sys
import json

import ffmpeg
import numpy
from vosk import Model, KaldiRecognizer, SetLogLevel
from gtts import gTTS

SAMPLE_RATE = 16000
SILENCE_THRESHOLD = 100000
SILENCE_CONSECUTIVE = 10
SILENCE_CAPTURE_WIDTH = 10
packet_size = 4096
buffer = []
abs_sum_silence_counter = 0
silence = True
sound = []
final_outputs = []
partial_outputs = []
last_partial_output = ""
numpy.set_printoptions(threshold=sys.maxsize, linewidth=sys.maxsize)
voice_commands_enabled = False
waiting_for_song = False
song_is_playing = False
greetings = ["hello", "hi", "hey", "hola", "whatsup", "sup"]
song_commands = {"play_command": "play", "pause_command": "pause", "next_command": "next", "rewind_command": "rewind", "search_command": "search"}
ai_name = "buddy"
disable_command = ["disable", "goodbye"]
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.connect(('8.8.8.8', 1))  # connect() for UDP doesn't send packets
local_ip_address = s.getsockname()[0]

language = 'en'
rtp_address = 'rtp://' + local_ip_address + ':5555'

model = Model(lang="en-us")
rec = KaldiRecognizer(model, SAMPLE_RATE)
process1 = ffmpeg.input(rtp_address).output('-', format='s16le', ac=1, ar='16k').run_async(pipe_stdout=True)

def speak(text):
    textobj = gTTS(text=text, lang=language, slow=False, tld='co.jp')
    textobj.save("temp.mp3")
    os.system("mpg321 temp.mp3")

def enable_voice_commands(final_output):
    words = final_output.split(" ")
    if bool(set(greetings) & set(words)):
        if ai_name in words:
            speak("Greetings Rohan, Voice Commands Enabled")
            global voice_commands_enabled
            voice_commands_enabled = True
def parse_command(final_output):
    words = final_output.split(" ")
    if bool(set(disable_command) & set(words)):
        speak("Disabling Voice Commands, Goodbye")
        global voice_commands_enabled
        voice_commands_enabled = False
    elif "song" in words:
        if song_commands["play_command"] in words:
            speak("playing song")
        elif song_commands["pause_command"] in words:
            speak("pausing song")
        elif song_commands["next_command"] in words:
            speak("playing next song")
        elif song_commands["rewind_command"] in words:
            speak("rewinding song")
        else:
            speak("What song would you like to play?")
            global waiting_for_song
            waiting_for_song = True
    else:
        speak("I did not recognize that command, please try again")


def search_and_play_song(final_output):
    speak("playing song " + final_output)
    global waiting_for_song
    waiting_for_song = False


while process1.poll() is None:
    packet = process1.stdout.read(packet_size)
    try:
        arr = numpy.fromstring(packet, dtype="int16")
        abs_sum = numpy.sum(numpy.absolute(arr))
        if abs_sum > SILENCE_THRESHOLD:
            abs_sum_silence_counter = 0
            if silence:
                oarr = numpy.arange(1, dtype='int16')
                silence = False
        else:
            if not silence:
                abs_sum_silence_counter += 1
                if abs_sum_silence_counter > SILENCE_CONSECUTIVE:
                    for s in sound:
                        if rec.AcceptWaveform(s):
                            final_outputs += [json.loads(rec.Result())['text']]
                        else:
                            partial_outputs += [json.loads(rec.PartialResult())['partial']]
                        final_outputs = list(filter(None, final_outputs))
                        partial_outputs = list(filter(None, partial_outputs))
                    final_output = ""
                    if len(final_outputs) > 0:
                        max_len = 0
                        for output in final_outputs:
                            if len(output) > max_len:
                                final_output = output
                                max_len = len(output)
                    elif len(partial_outputs) > 0:
                        max_len = 0
                        for output in partial_outputs:
                            if len(output) > max_len:
                                final_output = output
                                max_len = len(output)
                        if final_output == last_partial_output:
                            final_output = ""
                        else:
                            last_partial_output = final_output
                    if final_output != "":
                        if not voice_commands_enabled:
                            enable_voice_commands(final_output)
                        elif not waiting_for_song:
                            parse_command(final_output)
                        else:
                            search_and_play_song(final_output)
                    final_outputs = []
                    partial_outputs = []
                    sound = []
                    silence = True
        if not silence:
            sound += [packet]
        else:
            if len(sound) < SILENCE_CAPTURE_WIDTH:
                sound += [packet]
            else:
                sound.pop(0)
                sound += [packet]
    except socket.error:
        process1.stdout.close()
        process1.wait()
        break
