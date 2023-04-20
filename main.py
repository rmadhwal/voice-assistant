import os
import socket
import subprocess
import sys
import json
import time

import ffmpeg
import numpy
from vosk import Model, KaldiRecognizer, SetLogLevel
from gtts import gTTS
import _thread

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
command_failed = False
greetings = ["hello", "hi", "hey", "hola", "whatsup", "sup"]
song_commands = {"play_command": "play", "pause_command": "pause", "cancel_command": "cancel", "next_command": "next",
                 "rewind_command": "rewind", "back_command": "back", "search_command": "search"}
speaker_commands = {"off_command": "off"}
ai_name = "buddy"
disable_command = ["disable", "goodbye"]
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.connect(('8.8.8.8', 1))  # connect() for UDP doesn't send packets
local_ip_address = s.getsockname()[0]
host = '192.168.0.100'
port = 50001
previous_outputs = []
accepted_output = ""
empty_outputs = 0
last_output_time = time.time()
last_accepted_output = ""

language = 'en'
rtp_address = 'rtp://' + local_ip_address + ':5555'

model = Model(lang="en-us")
rec = KaldiRecognizer(model, SAMPLE_RATE)
process1 = ffmpeg.input(rtp_address).output('-', format='s16le', ac=1, ar='16k').run_async(pipe_stdout=True)


def speak(text):
    textobj = gTTS(text=text, lang=language, slow=False, tld='co.jp')
    textobj.save("temp.mp3")
    os.system("mpg321 temp.mp3")


def turn_on_speakers():
    command = "kefctl -H 192.168.0.100 -i aux"
    os.system(command)


def are_speakers_off():
    command = "kefctl -H 192.168.0.100 -s"
    output = subprocess.check_output(command, shell=True)
    return b'Power:   Off' in output


def enable_voice_commands(final_output):
    try:
        if are_speakers_off():
            turn_on_speakers()
    except:
        print("couldnt check speaker for status")
    global command_failed
    words = final_output.split(" ")
    if bool(set(greetings) & set(words)):
        speak("Greetings Rohan, Voice Commands Enabled")
        global voice_commands_enabled
        voice_commands_enabled = True
        return
    command_failed = True


def turn_off_speakers():
    command = "kefctl -H 192.168.0.100 -o"
    os.system(command)


def turn_bt_mode_on_speakers():
    command = "kefctl -H 192.168.0.100 -i bluetooth"
    os.system(command)


def parse_command(final_output):
    global command_failed
    words = final_output.split(" ")
    if bool(set(disable_command) & set(words)):
        speak("Disabling Voice Commands, Goodbye")
        global voice_commands_enabled
        voice_commands_enabled = False
    if song_commands["play_command"] in words:
        speak("playing song")
        os.system("cmus-remote -p")
    elif song_commands["pause_command"] in words or song_commands["cancel_command"] in words:
        speak("pausing song")
        os.system("cmus-remote -u")
    elif song_commands["next_command"] in words:
        speak("playing next song")
        os.system("cmus-remote -n")
    elif song_commands["rewind_command"] in words:
        os.system("cmus-remote -R")
        speak("rewinding song")
    elif song_commands["back_command"] in words:
        os.system("cmus-remote -r")
        speak("rewinding song")
    elif song_commands["search_command"] in words:
        speak("What song would you like to play?")
        global waiting_for_song
        waiting_for_song = True
    elif "speakers" in words:
        if speaker_commands["off_command"] in words:
            speak("turning off speakers")
            turn_off_speakers()
        elif speaker_commands["bluetooth_command"] in words:
            speak("enabling bluetooth")
            turn_bt_mode_on_speakers()
    else:
        command_failed = True
        speak("I did not recognize that command, please try again")


def search_and_play_song(final_output):
    words = final_output.split(" ")
    global waiting_for_song
    if "nevermind" in words or "cancel" in words:
        waiting_for_song = False
        return
    speak("playing song " + final_output)
    command = "cmus-remote -C /\"" + final_output + "\" win-activate"
    os.system(command)
    waiting_for_song = False


def see_if_command_exists():
    global accepted_output
    global process1
    global waiting_for_song
    global last_accepted_output
    global last_output_time

    while process1.poll() is None:
        if accepted_output != "":
            print(accepted_output)
            if not voice_commands_enabled:
                enable_voice_commands(accepted_output)
            elif not waiting_for_song:
                parse_command(accepted_output)
            else:
                search_and_play_song(accepted_output)
            accepted_output = ""
            if command_failed:
                last_accepted_output = []
                last_output_time = time.time()


def listen_for_commands():
    global final_outputs
    global partial_outputs
    global last_partial_output
    global previous_outputs
    global empty_outputs
    global last_accepted_output
    global last_output_time
    global voice_commands_enabled
    global accepted_output
    global process1
    global command_failed

    while process1.poll() is None:
        packet = process1.stdout.read(packet_size)
        try:
            if rec.AcceptWaveform(packet):
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
                previous_outputs += [final_output]
            elif len(previous_outputs) > 1:
                empty_outputs += 1
                new_previous_outputs = []
                for i in range(len(previous_outputs)):
                    words = previous_outputs[i].split(" ")
                    if not (bool(set(last_accepted_output) & set(words))) or time.time() - last_output_time > 20:
                        new_previous_outputs.append(previous_outputs[i])
                previous_outputs = new_previous_outputs
                if empty_outputs > 20 and len(previous_outputs) > 1:
                    accepted_output = previous_outputs[-1]
                    last_accepted_output = list(
                        filter(lambda x: x != 'song' and x != 'speakers', previous_outputs[-1].split(" ")))
                    last_output_time = time.time()
                    previous_outputs = []
            final_outputs = []
            partial_outputs = []
        except socket.error:
            process1.stdout.close()
            process1.wait()
            break


try:
    _thread.start_new_thread(listen_for_commands, ())
    _thread.start_new_thread(see_if_command_exists, ())
except:
    print("Error: unable to start thread")

while 1:
   pass