import os
import json
import pickle
import sys

sys.path.append('/Users/sebastiaanscholten/Documents/speech2image-master/preprocessing')
sys.path.append('/Users/sebastiaanscholten/Documents/speech2image-master/preprocessing/dictionaries')

from visual_features import vis_feats
from audio_features import audio_features
from text_features import text_features_flickr
from aud_feat_functions import get_fbanks, get_freqspectrum, get_mfcc, delta, raw_frames
from scipy.io.wavfile import read
import numpy
import tables
import os
import wave

from pathlib import Path
import tables

audio_path = os.path.join('/Users/sebastiaanscholten/Documents/speech2image-master/vgsexperiments/experiments/Generating_TTS_Flickrwords/Flickr8kWordsWAV')
data_loc = os.path.join('mfcc/words_mfcc_features.h5')
speech = ['mfcc']

audio = os.listdir(audio_path)

audio_base = [x.split('.')[0] for x in audio]

append_name = 'flickr_'

if not Path(data_loc).is_file():
    # create h5 output file for preprocessed images and audio
    output_file = tables.open_file(data_loc, mode='a')
    # create the h5 file to hold all image and audio features. This will fail if they already excist such
    # as when you run this file to append new features to an excisting feature file
    for x in audio_base:
        try:
            # one group for each image file which will contain its vgg16 features and audio captions
            output_file.create_group("/", append_name + x.split('.')[0])
        except:
            continue

node_list = output_file.root._f_list_nodes()

feat = 'mfcc'
params = []
# set alpha for the preemphasis
alpha = 0.97
# set the number of desired filterbanks
nfilters = 40
# windowsize and shift in seconds
t_window = .025
t_shift = .010
# option to include delta and double delta features
use_deltas = True
# option to include frame energy
use_energy = True
# put paramaters in a list
params.append(alpha)
params.append(nfilters)
params.append(t_window)
params.append(t_shift)
params.append(feat)
params.append(output_file)
params.append(use_deltas)
params.append(use_energy)
#############################################################################

# create the audio features for all captions
def fix_wav(path_to_file):
    #fix wav file. In the flickr dataset there is one wav file with an incorrect
    #number of frames indicated in the header, causing it to be unreadable by pythons
    #wav read function. This opens the file with the wave package, extracts the correct
    #number of frames and saves the file with a correct header

    file = wave.open(path_to_file, 'r')
    # derive the correct number of frames from the file
    frames = file.readframes(file.getnframes())
    # get all other header parameters
    params = file.getparams()
    file.close()
    # now save the file with a new header containing the correct number of frames
    out_file = wave.open(path_to_file, 'w')
    out_file.setparams(out_file.getparams())
    out_file.writeframes(frames)
    out_file.close()

def audio_features(params, img_audio, audio_path, append_name, node_list):
    output_file = params[5]
    # create pytable atom for the features
    f_atom = tables.Float32Atom()
    count = 1
    # keep track of the nodes for which no features could be made, places database contains some
    # empty audio files
    invalid = []
    for node in node_list:
        print('processing file audio:' + str(count))
        count += 1
        # create a group for the desired feature type (e.g. a group called 'fbanks')
        audio_node = output_file.create_group(node, params[4])
        # get the base name of the node this feature will be appended to
        base_name = node._v_name.split(append_name)[1]
        # get the caption file names corresponding to the image of this node
        caption_files = [base_name + '.wav']

        for cap in caption_files:
            # basename for the caption file, i.e. cut of the file extension as dots arent
            # allowed in pytables group names.
            base_capt = cap.split('.')[0]
            # as the places database splits the audio files over multiple subfolders these paths from
            # the top folder are included the captions in the dictionary but can be removed from the base_name
            # of the node in the h5 file.
            if '/' in base_capt:
                base_capt = base_capt.split('/')[-1]
            # read audio samples
            try:
                input_data = read(os.path.join(audio_path, cap))
                # in the places database some of the audiofiles are empty. To keep this script
                # compatible with database that might have more captions to one image, we check
                # if the audio node is empty at the end of the loop and delete the entire node
                # if no caption features could be made.
                if len(input_data[1]) == 0:
                    # break as we can do nothing with an empty audio file.
                    break
            except:
                # try to repair the file, however I found some files in places, so broken that
                # such that they could not be read at all. Just remove such nodes
                try:
                    fix_wav(os.path.join(audio_path, cap))
                    input_data = read(os.path.join(audio_path, cap))
                except:
                    break
            # sampling frequency
            fs = input_data[0]
            # get window and frameshift size in samples
            window_size = int(fs * params[2])
            frame_shift = int(fs * params[3])

            # create features (implemented are raw audio, the frequency spectrum, fbanks and
            # mfcc's)
            if params[4] == 'raw':
                [features, energy] = raw_frames(input_data, frame_shift, window_size)

            elif params[4] == 'freq_spectrum':
                [frames, energy] = raw_frames(input_data, frame_shift, window_size)
                features = get_freqspectrum(frames, params[0], fs, window_size)

            elif params[4] == 'fbanks':
                [frames, energy] = raw_frames(input_data, frame_shift, window_size)
                freq_spectrum = get_freqspectrum(frames, params[0], fs, window_size)
                features = get_fbanks(freq_spectrum, params[1], fs)

            elif params[4] == 'mfcc':
                [frames, energy] = raw_frames(input_data, frame_shift, window_size)
                freq_spectrum = get_freqspectrum(frames, params[0], fs, window_size)
                fbanks = get_fbanks(freq_spectrum, params[1], fs)
                features = get_mfcc(fbanks)

            # optionally add the frame energy
            if params[7]:
                features = numpy.concatenate([energy[:, None], features], 1)
            # optionally add the deltas and double deltas
            if params[6]:
                single_delta = delta(features, 2)
                double_delta = delta(single_delta, 2)
                features = numpy.concatenate([features, single_delta, double_delta], 1)

            # create new leaf node in the feature node for the current audio file
            feature_shape = numpy.shape(features)[1]
            f_table = output_file.create_earray(audio_node, append_name + base_capt, f_atom, (0, feature_shape),
                                                expectedrows=5000)

            # append new data to the tables
            f_table.append(features)
        if audio_node._f_list_nodes() == []:
            # keep track of all the invalid nodes for which no features could be made
            invalid.append(node._v_name)
            # remove the top node including all other features if no captions features could be created
            output_file.remove_node(node, recursive=True)
    print(invalid)
    return

for ftype in speech:
    params[4] = feat
    audio_features(params, audio_base, audio_path, append_name, node_list)

output_file.close()