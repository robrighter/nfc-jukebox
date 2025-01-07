import os
import glob
import sys
import subprocess
import signal
import time
from pathlib import Path
import termios
import tty
import select

import RPi.GPIO as GPIO
from mfrc522 import SimpleMFRC522


LED_PIN = 24

gpio_wait = True
print("Waiting for GPIO ...")
while gpio_wait:
    try:
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        GPIO.setup(LED_PIN, GPIO.OUT)
        gpio_wait = False
    except Exception:
        time.sleep(100)
        pass

print("GPIO setup.")
print("setting up RFID Reader...")
reader = SimpleMFRC522()
print("RFID reader setup.")

def set_play_led(is_on):
    if is_on:
        GPIO.output(LED_PIN, GPIO.HIGH)
    else:
        GPIO.output(LED_PIN, GPIO.LOW)

set_play_led(False)

class KeyPoller:
    def __enter__(self):
        # Save the terminal settings
        self.fd = sys.stdin.fileno()
        self.old_settings = termios.tcgetattr(self.fd)
        try:
            # Set the terminal to raw mode
            tty.setraw(self.fd)
        except termios.error:
            pass
        return self

    def __exit__(self, type, value, traceback):
        # Restore the terminal settings
        termios.tcsetattr(self.fd, termios.TCSADRAIN, self.old_settings)

    def poll(self, timeout=0.1):
        # Check if there's any input waiting
        dr, dw, de = select.select([sys.stdin], [], [], timeout)
        if not dr == []:
            return sys.stdin.read(1)
        return None

class MP3Player:
    def __init__(self):
        self.base_dir = os.path.join('.', 'music')
        self.process = None
        self.playing = False
        self.paused = False
        self.current_position = 0
        
        # Ensure base music directory exists
        if not os.path.exists(self.base_dir):
            os.makedirs(self.base_dir)
        
    def get_available_playlists(self):
        # Get all subdirectories in the music folder
        try:
            subdirs = [d for d in os.listdir(self.base_dir) 
                      if os.path.isdir(os.path.join(self.base_dir, d))]
            return sorted(subdirs)
        except Exception:
            return []
        
    def load_directory(self, subdir):
        # Convert subdir to full path
        full_path = os.path.join(self.base_dir, subdir)
        
        # Validate and load the new directory
        if not os.path.isdir(full_path):
            raise ValueError(f"Error: {subdir} is not a valid subdirectory in ./music")
            
        self.current_subdir = subdir
        self.playlist = sorted(glob.glob(os.path.join(full_path, "*.mp3")))
        print(str(self.playlist))
        if not self.playlist:
            raise ValueError(f"No MP3 files found in ./music/{subdir}")
            
        self.current_track = 0
        
    def prompt_for_directory(self):
        while True:
            # Get available playlists
            playlists = self.get_available_playlists()
            
            if not playlists:
                print("\rNo subdirectories found in ./music")
                print("Please create a subdirectory with MP3 files and try again")
                sys.exit(1)
                
            print("\rAvailable playlists:")
            for playlist in playlists:
                print(f"  - {playlist}")
            
            print("\rEnter playlist name:")
            try:
                subdir = input().strip()
                self.load_directory(subdir)
                print(f"Found {len(self.playlist)} MP3 files in ./music/{subdir}")
                return
            except ValueError as e:
                print(f"Error: {str(e)}")
                print("Please try again.")
            except Exception as e:
                print(f"Error: {str(e)}")
                print("Please try again.")
        
    def change_directory(self, new_subdir=None):
        # Switch to normal terminal mode temporarily
        termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, self.old_settings)
        
        try:
            # Show available playlists
            playlists = self.get_available_playlists()
            print("\rAvailable playlists:")
            for playlist in playlists:
                print(f"  - {playlist}")
            
            if new_subdir == None:
                print("\rEnter playlist name:")
                new_subdir = input().strip()
            
            # Stop current playback
            if self.process:
                self.process.terminate()
                self.process.wait()
                self.process = None
            set_play_led(False)

            # Try to load the new directory
            self.load_directory(new_subdir)
            print(f"\rChanged to playlist: {new_subdir}")
            print(f"Found {len(self.playlist)} MP3 files")
            
            # Start playing first track in new directory
            self.play_current_track()
            
        except ValueError as e:
            print(f"\r{str(e)}")
        except Exception as e:
            print(f"\rError changing directory: {e}")
        finally:
            # Switch back to raw mode
            try:
                tty.setraw(sys.stdin.fileno())
            except termios.error:
                pass
        
    def start_playback(self, position=0):
        if position > 0:
            seek_arg = f"--seek {position}"
        else:
            seek_arg = ""
        
        current_file = self.playlist[self.current_track]
        command = ['mpg123', current_file]
        self.process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        self.playing = True
        self.paused = False
        set_play_led(True)
        
    def play_current_track(self):
        if self.process:
            self.process.terminate()
            self.process.wait()
            
        self.current_position = 0
        self.start_playback()
        self.show_now_playing()
        
    def show_now_playing(self):
        sys.stdout.write('\r' + ' ' * 80 + '\r')  # Clear line
        current_file = Path(self.playlist[self.current_track]).name
        print(f"Now playing: [{self.current_subdir}] {current_file}")
        print(f"Track {self.current_track + 1} of {len(self.playlist)}")
        sys.stdout.flush()
        
    def toggle_play_pause(self):
        if not self.paused and self.process:
            try:
                self.current_position = 0 # int(time.time() - self.start_time)
                self.process.terminate()
                self.process.wait()
                self.process = None
                self.paused = True
                set_play_led(False)
                print("\rPaused playback")
            except Exception as e:
                print(f"\rError pausing: {e}")
        elif self.paused:
            try:
                self.start_playback(self.current_position)
                self.paused = False
                set_play_led(True)
                print("\rResumed playback")
            except Exception as e:
                print(f"\rError resuming: {e}")
                
    def next_track(self):
        self.current_track = (self.current_track + 1) % len(self.playlist)
        self.play_current_track()
        
    def previous_track(self):
        self.current_track = (self.current_track - 1) % len(self.playlist)
        self.play_current_track()
        
    def check_if_track_ended(self):
        if self.process and self.process.poll() is not None and not self.paused:
            self.next_track()
        
    def run(self):
        # Check if mpg123 is installed
        current_dir = None

        try:
            subprocess.run(["which", "mpg123"], check=True, capture_output=True)
        except subprocess.CalledProcessError:
            print("Error: mpg123 is not installed. Please install it using:")
            print("sudo apt-get install mpg123")
            sys.exit(1)

        # Get initial directory
        # self.prompt_for_directory()
        
        print("\nMP3 Player Controls:")
        print("p - Play/Pause")
        print("n - Next track")
        print("b - Previous track")
        print("c - Change playlist")
        print("q - Quit")
        
        # Store the initial terminal settings for directory change
        self.old_settings = termios.tcgetattr(sys.stdin.fileno())
        
        # Start playback immediately
        self.start_time = time.time()
        # self.play_current_track()
        
        with KeyPoller() as poller:
            while True:
                try:
                    self.check_if_track_ended()

                    id, new_dir = reader.read_no_block()
                    if new_dir != None:
                        new_dir = new_dir.strip()
                    
                    
                    # print("Read from RFID: "+ str(new_dir))
                    char = poller.poll()
                    if char:
                        if char == 'p':
                            self.toggle_play_pause()
                        elif char == 'n':
                            self.next_track()
                        elif char == 'b':
                            self.previous_track()
                        elif char == 'c':
                            self.change_directory()
                        elif char == 'q':
                            set_play_led(False)
                            if self.process:
                                self.process.terminate()
                                self.process.wait()
                            print("\rGoodbye!")
                            return
                    # print("new_dir="+str(new_dir)+ " current_dir="+str(current_dir)) 
                    if new_dir != current_dir:
                        if new_dir != None:
                            current_dir = new_dir
                            self.change_directory(current_dir)
                           
                except KeyboardInterrupt:
                    if self.process:
                        self.process.terminate()
                        self.process.wait()
                    print("\rGoodbye!")
                    return

if __name__ == "__main__":
    player = MP3Player()
    player.run()
