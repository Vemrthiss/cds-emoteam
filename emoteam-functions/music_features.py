import arff
import pandas as pd
import numpy as np
import os
import subprocess

def get_music_features(wav_path, dist_file, opensmile_dir):
  # extract static features of all wavs and load into 1 file
  SMILExtract = os.path.join(opensmile_dir, "build", "progsrc", "smilextract", "SMILExtract")
  config_file = os.path.join(opensmile_dir, "config", "is09-13", "IS13_ComParE.conf")

  subprocess.check_call([SMILExtract, "-C", config_file, "-I", wav_path, "-O", dist_file, "-instname", wav_path])

def wav_to_features(wav_path, output_path, track_id):
  static_features_file = f"static_features_{track_id}.arff"
  get_music_features(wav_path, static_features_file, "/usr/local/bin/opensmile")

  res = arff.load(open(static_features_file, "r"))
  data = res['data']
  cols = list(map(lambda t: t[0], res['attributes']))
  df = pd.DataFrame(data, columns=cols)
  # exclude last col "class", not relevant from opensmile
  df = df.drop(columns=['class', 'name'])
  df.reset_index(drop=True, inplace=True)
  mean = pd.read_csv('features_mean.csv', header=None, index_col=0).T
  std = pd.read_csv('features_std.csv', header=None, index_col=0).T
  mean.reset_index(drop=True, inplace=True)
  std.reset_index(drop=True, inplace=True)
  df = (df - mean) / std # do z-score normalization
  # select relevant cols
  selected_cols = pd.read_csv('./selected_music_features.csv', header=None)
  selected_cols = np.array(selected_cols).flatten()
  df = df[selected_cols]

  # save to csv
  df.to_csv(output_path, index=False)

  # remove arff file
  if os.path.exists(static_features_file):
    os.remove(static_features_file)