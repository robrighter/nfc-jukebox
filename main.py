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

class KeyPoller:
    def __enter__(self):
        # Save the terminal settings
        self.fd = sys.stdin.fileno()
        self.old_settings = termios.tcgetattr(self.fd)
        try:
            # Set the terminal to raw mode
            tty.setraw(self.fd)
        except termios.error:
            # If we can't set raw mode (e.g., when running in IDE), fall back to normal mode
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
    def __init__(self, directory):
        # Get all MP3 files from directory
        self.directory = directory
        self.playlist = sorted(glob.glob(os.path.join(directory, "*.mp3")))
        
        if not self.playlist:
            print("No MP3 files found in directory")
            sys.exit(1)
            
        self.current_track = 0
        self.process = None
        self.playing = False
        self.paused = False
        self.current_position = 0  # Track the position in seconds
        
    def start_playback(self, position=0):
        # Start playback from the specified position
        if position > 0:
            seek_arg = f"--seek {position}"
        else:
            seek_arg = ""
            
        command = f"mpg123 -q --control {seek_arg} {self.playlist[self.current_track]}"
        self.process = subprocess.Popen(
            command.split(),
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        self.playing = True
        self.paused = False
        
    def play_current_track(self):
        # Stop any currently playing track
        if self.process:
            self.process.terminate()
            self.process.wait()
            
        # Reset position when starting a new track
        self.current_position = 0
        self.start_playback()
        self.show_now_playing()
        
    def show_now_playing(self):
        # Clear the current line and display track information
        sys.stdout.write('\r' + ' ' * 80 + '\r')  # Clear line
        current_file = Path(self.playlist[self.current_track]).name
        print(f"Now playing: {current_file}")
        print(f"Track {self.current_track + 1} of {len(self.playlist)}")
        sys.stdout.flush()
        
    def toggle_play_pause(self):
        if not self.paused and self.process:
            # Pause by terminating the process
            try:
                self.current_position = int(time.time() - self.start_time)
                self.process.terminate()
                self.process.wait()
                self.process = None
                self.paused = True
                print("\rPaused playback")
            except Exception as e:
                print(f"\rError pausing: {e}")
        elif self.paused:
            # Resume by starting process from last position
            try:
                self.start_playback(self.current_position)
                self.paused = False
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
        # Check if the current process has ended
        if self.process and self.process.poll() is not None and not self.paused:
            self.next_track()
        
    def run(self):
        print("\nMP3 Player Controls:")
        print("p - Play/Pause")
        print("n - Next track")
        print("b - Previous track")
        print("q - Quit")
        print("\nPress any key to begin...")
        
        with KeyPoller() as poller:
            # Wait for initial keypress
            while poller.poll() is None:
                pass
            
            # Start playing first track
            self.start_time = time.time()
            self.play_current_track()
            
            # Main control loop
            while True:
                try:
                    # Check if we need to move to next track
                    self.check_if_track_ended()
                    
                    # Check for keypresses
                    char = poller.poll()
                    if char:
                        if char == 'p':
                            self.toggle_play_pause()
                        elif char == 'n':
                            self.next_track()
                        elif char == 'b':
                            self.previous_track()
                        elif char == 'q':
                            if self.process:
                                self.process.terminate()
                                self.process.wait()
                            print("\rGoodbye!")
                            return
                            
                except KeyboardInterrupt:
                    if self.process:
                        self.process.terminate()
                        self.process.wait()
                    print("\rGoodbye!")
                    return

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python mp3_player.py <directory>")
        sys.exit(1)
        
    directory = sys.argv[1]
    if not os.path.isdir(directory):
        print(f"Error: {directory} is not a valid directory")
        sys.exit(1)
        
    # Check if mpg123 is installed
    try:
        subprocess.run(["which", "mpg123"], check=True, capture_output=True)
    except subprocess.CalledProcessError:
        print("Error: mpg123 is not installed. Please install it using:")
        print("sudo apt-get install mpg123")
        sys.exit(1)
        
    player = MP3Player(directory)
    player.run()