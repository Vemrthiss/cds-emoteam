import librosa.display
import numpy as np
import imageio
import matplotlib.pyplot as plt

def make_spectrogram(mp3_path: str, output_path: str):
  y, sr = librosa.load(mp3_path)

  # Convert to Mel-spectrogram
  mel_spectrogram = librosa.feature.melspectrogram(y=y, sr=sr)

  # Convert to log-scaled Mel-spectrogram
  log_mel_spectrogram = librosa.power_to_db(mel_spectrogram, ref=np.max)

  # img = (log_mel_spectrogram - np.mean(log_mel_spectrogram)) / np.std(log_mel_spectrogram)
  # img = (img * 255).astype(np.uint8)
  # imageio.imwrite(output_path, img)
  librosa.display.specshow(log_mel_spectrogram, sr=sr, x_axis='time', y_axis='mel')
  plt.axis('off')
  plt.savefig(output_path, bbox_inches='tight', pad_inches=0)
  plt.close()