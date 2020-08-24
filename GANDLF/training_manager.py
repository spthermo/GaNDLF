
from torch.optim.lr_scheduler import ReduceLROnPlateau
import torch
from torch.utils.data.dataset import Dataset
import torch.optim as optim
import numpy as np
import pandas as pd
from torch.utils.data import DataLoader
import os
import random
import torchio
from torchio.transforms import *
from torchio import Image, Subject
from sklearn.model_selection import KFold
from shutil import copyfile
import time
import sys
import ast 
import pickle
from pathlib import Path
import subprocess


# from GANDLF.data.ImagesFromDataFrame import ImagesFromDataFrame
from GANDLF.training_loop import trainingLoop

# This function takes in a dataframe, with some other parameters and returns the dataloader
def TrainingManager(dataframe, augmentations, kfolds, psize, channelHeaders, labelHeader, model_parameters_file, outputDir,
    num_epochs, batch_size, learning_rate, which_loss, opt, 
    class_list, base_filters, n_channels, which_model, parallel_compute_command, device):

    # kfolds = int(parameters['kcross_validation'])
    # check for single fold training
    singleFoldTraining = False
    if kfolds < 0: # if the user wants a single fold training
      kfolds = abs(kfolds)
      singleFoldTraining = True

    kf = KFold(n_splits=kfolds) # initialize the kfold structure

    currentFold = 0

    # get the indeces for kfold splitting
    trainingData_full = dataframe
    training_indeces_full = list(trainingData_full.index.values)

    # start the kFold train
    for train_index, test_index in kf.split(training_indeces_full):

      # the output of the current fold is only needed if multi-fold training is happening
      if singleFoldTraining:
        currentOutputFolder = outputDir
      else:
        currentOutputFolder = os.path.join(outputDir, str(currentFold))
        Path(currentOutputFolder).mkdir(parents=True, exist_ok=True)

      trainingData = trainingData_full.iloc[train_index]
      validationData = trainingData_full.iloc[test_index]

      # save the current model configuration as a sanity check
      # parametersFilePickle = os.path.join(currentOutputFolder,'model.cfg')
      copyfile(model_parameters_file, os.path.join(currentOutputFolder,'model.cfg'))

      if (not parallel_compute_command) or (singleFoldTraining): # parallel_compute_command is an empty string, thus no parallel computing requested
        trainingLoop(trainingDataFromPickle = trainingData, validataionDataFromPickle = validationData, 
        num_epochs = num_epochs, batch_size = batch_size, learning_rate = learning_rate, 
        which_loss = which_loss, opt = opt, class_list = class_list,
        base_filters = base_filters, n_channels = n_channels, which_model = which_model, psize = psize, 
        channelHeaders = channelHeaders, labelHeader = labelHeader, augmentations = augmentations, outputDir = currentOutputFolder, device = device)

      else:
        # # write parameters to pickle - this should not change for the different folds, so keeping is independent
        ## pickle/unpickle data
        # pickle the data
        currentTrainingDataPickle = os.path.join(currentOutputFolder, 'train.pkl')
        currentValidataionDataPickle = os.path.join(currentOutputFolder, 'validation.pkl')
        trainingData.to_pickle(currentTrainingDataPickle)
        validationData.to_pickle(currentValidataionDataPickle)

        channelHeaderPickle = os.path.join(currentOutputFolder,'channelHeader.pkl')
        with open(channelHeaderPickle, 'wb') as handle:
            pickle.dump(channelHeaders, handle, protocol=pickle.HIGHEST_PROTOCOL)
        labelHeaderPickle = os.path.join(currentOutputFolder,'labelHeader.pkl')
        with open(labelHeaderPickle, 'wb') as handle:
            pickle.dump(labelHeader, handle, protocol=pickle.HIGHEST_PROTOCOL)
        augmentationsPickle = os.path.join(currentOutputFolder,'augmentations.pkl')
        with open(augmentationsPickle, 'wb') as handle:
            pickle.dump(augmentations, handle, protocol=pickle.HIGHEST_PROTOCOL)
        psizePickle = os.path.join(currentOutputFolder,'psize.pkl')
        with open(psizePickle, 'wb') as handle:
            pickle.dump(psize, handle, protocol=pickle.HIGHEST_PROTOCOL)

        # call qsub here
        parallel_compute_command_actual = parallel_compute_command.replace('${outputDir}', currentOutputFolder)
        
        if not('python' in parallel_compute_command_actual):
          sys.exit('The \'parallel_compute_command_actual\' needs to have the python from the virtual environment, which is usually \'${GANDLF_dir}/venv/bin/python\'')

        command = parallel_compute_command_actual + \
            ' -m GANDLF.training_loop -train_loader_pickle ' + currentTrainingDataPickle + \
            ' -val_loader_pickle ' + currentValidataionDataPickle + \
            ' -num_epochs ' + str(num_epochs) + ' -batch_size ' + str(batch_size) + \
            ' -learning_rate ' + str(learning_rate) + ' -which_loss ' + which_loss + \
            ' -n_classes ' + str(n_classes) + ' -base_filters ' + str(base_filters) + \
            ' -n_channels ' + str(n_channels) + ' -which_model ' + which_model + \
            ' -channel_header_pickle ' + channelHeaderPickle + ' -label_header_pickle ' + labelHeaderPickle + \
            ' -augmentations_pickle ' + augmentationsPickle + ' -psize_pickle ' + psizePickle + ' -device ' + str(device) + ' -outputDir ' + currentOutputFolder
        
        subprocess.Popen(command, shell=True).wait()

      if singleFoldTraining:
        break
      currentFold = currentFold + 1 # increment the fold