import os
import pygame
import glob
import sys
from pathlib import Path
import threading
import time

class MP3Player:
    def __init__(self, directory):
        # Initialize pygame mixer
        pygame.mixer.init()
        pygame.init()
        
        # Get all MP3 files from directory
        self.directory = directory
        self.playlist = sorted(glob.glob(os.path.join(directory, "*.mp3")))
        
        if not self.playlist:
            print("No MP3 files found in directory")
            sys.exit(1)
            
        self.current_track = 0
        self.playing = False
        self.paused = False
        
    def play_current_track(self):
        # Load and play the current track
        pygame.mixer.music.load(self.playlist[self.current_track])
        pygame.mixer.music.play()
        self.playing = True
        self.paused = False
        self.show_now_playing()
        
    def show_now_playing(self):
        # Display current track information
        current_file = Path(self.playlist[self.current_track]).name
        print(f"\nNow playing: {current_file}")
        print(f"Track {self.current_track + 1} of {len(self.playlist)}")
        
    def toggle_play_pause(self):
        if self.paused:
            pygame.mixer.music.unpause()
            self.paused = False
            print("\nResumed playback")
        else:
            pygame.mixer.music.pause()
            self.paused = True
            print("\nPaused playback")
            
    def next_track(self):
        self.current_track = (self.current_track + 1) % len(self.playlist)
        self.play_current_track()
        
    def previous_track(self):
        self.current_track = (self.current_track - 1) % len(self.playlist)
        self.play_current_track()
        
    def check_music_ended(self):
        # Check if the current song has ended and play next track
        while True:
            if self.playing and not pygame.mixer.music.get_busy() and not self.paused:
                self.next_track()
            time.sleep(0.1)
            
    def run(self):
        print("\nMP3 Player Controls:")
        print("'p' - Play/Pause")
        print("'n' - Next track")
        print("'b' - Previous track")
        print("'q' - Quit")
        
        # Start playing first track
        self.play_current_track()
        
        # Start thread to check for end of track
        threading.Thread(target=self.check_music_ended, daemon=True).start()
        
        # Main control loop
        while True:
            try:
                key = input().lower()
                if key == 'p':
                    self.toggle_play_pause()
                elif key == 'n':
                    self.next_track()
                elif key == 'b':
                    self.previous_track()
                elif key == 'q':
                    pygame.mixer.music.stop()
                    pygame.quit()
                    print("\nGoodbye!")
                    sys.exit(0)
                    
            except KeyboardInterrupt:
                pygame.mixer.music.stop()
                pygame.quit()
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
        
    player = MP3Player(directory)
    player.run()