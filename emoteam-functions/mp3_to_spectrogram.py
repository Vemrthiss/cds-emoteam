import librosa
import librosa.display
import numpy as np
import matplotlib.pyplot as plt
import io

def generate_spectrogram(mp3_buffer, output_spectrogram_path):
    # Load the audio data from the buffer
    y, sr = librosa.load(mp3_buffer)

    # Convert to Mel-spectrogram
    mel_spectrogram = librosa.feature.melspectrogram(y=y, sr=sr)

    # Convert to log-scaled Mel-spectrogram
    log_mel_spectrogram = librosa.power_to_db(mel_spectrogram, ref=np.max)

    # Save the Mel-spectrogram as an image
    librosa.display.specshow(log_mel_spectrogram, sr=sr, x_axis='time', y_axis='mel')
    plt.axis('off')
    plt.savefig(output_spectrogram_path, bbox_inches='tight', pad_inches=0)
    plt.close()

if __name__ == "__main__":
    # Get input and output file paths from command-line arguments
    # For demonstration, assume mp3_data is the audio data
    mp3_data = b"..."  # Placeholder for the audio data
    track_id = "example_track_id"  # Placeholder for the track ID

    # Generate spectrogram
    with io.BytesIO(mp3_data) as mp3_buffer:
        generate_spectrogram(mp3_buffer, f"/img/{track_id}.png")
