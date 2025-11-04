import os
from pathlib import Path
import pygame

# Initialize pygame mixer
pygame.mixer.init()

# Get the absolute path to the sounds directory
SOUNDS_DIR = Path(__file__).parent.parent / 'assets' / 'sounds'

# Create the sounds directory if it doesn't exist
SOUNDS_DIR.mkdir(parents=True, exist_ok=True)

# Sound file paths
SOUNDS = {
    'success': SOUNDS_DIR / 'success.wav',  # On-time attendance
    'notification': SOUNDS_DIR / 'notification.wav'  # Late attendance
}

def play_sound(sound_type: str):
    """
    Play a sound effect
    Args:
        sound_type: Type of sound to play ('success', 'error', 'notification')
    """
    try:                                                                                    
        if sound_type in SOUNDS and SOUNDS[sound_type].exists():
            sound = pygame.mixer.Sound(str(SOUNDS[sound_type]))
            sound.play()
        else:
            print(f"Sound file not found: {sound_type}")
    except Exception as e:
        print(f"Error playing sound: {str(e)}")

def initialize_default_sounds():
    """
    Initialize default system sounds if they don't exist
    You can replace these with your own sound files by placing .wav files
    in the assets/sounds directory
    """
    # Here you would either:
    # 1. Copy default sound files from your package
    # 2. Download them from a known location
    # 3. Generate them programmatically
    
    # For now, we'll just print instructions
    if not any(sound.exists() for sound in SOUNDS.values()):
        print("""
        Sound files not found! Please add .wav files to the assets/sounds directory:
        - success.wav: For successful attendance
        - error.wav: For errors
        - notification.wav: For general notifications
        
        You can download free sound effects from:
        - https://freesound.org
        - https://mixkit.co/free-sound-effects
        - https://soundbible.com
        
        Convert them to .wav format if needed.
        """)