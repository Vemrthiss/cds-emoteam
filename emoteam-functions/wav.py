from pydub import AudioSegment

def mp3_to_wav(mp3_path: str, wav_path: str):
  audio = AudioSegment.from_mp3(mp3_path)
  audio.export(wav_path, format="wav")