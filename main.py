import os
import glob
import sys
import subprocess
import signal
import time
from pathlib import Path

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
        
    def play_current_track(self):
        # Stop any currently playing track
        if self.process:
            self.process.terminate()
            self.process.wait()
            
        # Start new track
        self.process = subprocess.Popen(
            ["mpg123", "-q", "--control", self.playlist[self.current_track]],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        self.playing = True
        self.paused = False
        self.show_now_playing()
        
    def show_now_playing(self):
        # Display current track information
        current_file = Path(self.playlist[self.current_track]).name
        print(f"\nNow playing: {current_file}")
        print(f"Track {self.current_track + 1} of {len(self.playlist)}")
        
    def toggle_play_pause(self):
        if self.process:
            if self.paused:
                self.process.stdin.write(b's')
                self.process.stdin.flush()
                self.paused = False
                print("\nResumed playback")
            else:
                self.process.stdin.write(b's')
                self.process.stdin.flush()
                self.paused = True
                print("\nPaused playback")
                
    def next_track(self):
        self.current_track = (self.current_track + 1) % len(self.playlist)
        self.play_current_track()
        
    def previous_track(self):
        self.current_track = (self.current_track - 1) % len(self.playlist)
        self.play_current_track()
        
    def check_if_track_ended(self):
        # Check if the current process has ended
        if self.process and self.process.poll() is not None:
            self.next_track()
        
    def run(self):
        print("\nMP3 Player Controls:")
        print("'p' - Play/Pause")
        print("'n' - Next track")
        print("'b' - Previous track")
        print("'q' - Quit")
        
        # Start playing first track
        self.play_current_track()
        
        # Main control loop
        while True:
            try:
                # Check if we need to move to next track
                self.check_if_track_ended()
                
                # Non-blocking input check
                import select
                if select.select([sys.stdin], [], [], 0.1)[0]:
                    key = sys.stdin.readline().strip().lower()
                    if key == 'p':
                        self.toggle_play_pause()
                    elif key == 'n':
                        self.next_track()
                    elif key == 'b':
                        self.previous_track()
                    elif key == 'q':
                        if self.process:
                            self.process.terminate()
                            self.process.wait()
                        print("\nGoodbye!")
                        sys.exit(0)
                        
            except KeyboardInterrupt:
                if self.process:
                    self.process.terminate()
                    self.process.wait()
                print("\nGoodbye!")
                sys.exit(0)

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