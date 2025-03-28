#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Wed Dec 29 2021

@author: Sudhir Vissa
"""

#%%
# Libraries


import warnings
warnings.filterwarnings('ignore')

from tensorflow.keras.applications.vgg16 import VGG16
from tensorflow.keras.preprocessing import image
from tensorflow.keras.models import Sequential, Model
from tensorflow.keras.layers import Dense, Dropout, Flatten, Input

import numpy as np
import json

from tensorflow.keras import metrics, optimizers

from tensorflow.keras.callbacks import ModelCheckpoint

import itertools
import matplotlib.pyplot as plt

import os
from sklearn.metrics import confusion_matrix, classification_report
import tensorflow as tf


#%%

def plot_confusion_matrix(cm, classes,
                          normalize=False,
                          title='Confusion matrix',
                          cmap=plt.cm.Blues):

    if normalize:
        cm = cm.astype('float') / cm.sum(axis=1)[:, np.newaxis]
        print("Normalized confusion matrix")
    else:
        print('Confusion matrix, without normalization')

#     print(cm)
    plt.figure(figsize=(6,5))
    plt.imshow(cm, interpolation='nearest', cmap=cmap)
    # plt.title(title)
    plt.colorbar()
    tick_marks = np.arange(len(classes))
    plt.xticks(tick_marks, classes)
    plt.yticks(tick_marks, classes)

    fmt = '.2f' if normalize else 'd'
    thresh = cm.max() / 2.
    for i, j in itertools.product(range(cm.shape[0]), range(cm.shape[1])):
        plt.text(j, i, format(cm[i, j], fmt),
                 horizontalalignment="center",
                 fontsize=20,
                 color="white" if cm[i, j] > thresh else "black")

    plt.tight_layout()
    plt.ylabel('True label')
    plt.xlabel('Predicted label')
    figname = title + '.png'
    
    plt.savefig(figname, dpi = 600)
    
#%%

def top_5_accuracy(y_true, y_pred):
    return metrics.top_k_categorical_accuracy(y_true, y_pred, k=5)



def get_top_k_predictions(preds, label_map, k=5, print_flag=False):
    sorted_array = np.argsort(preds)[::-1]
    top_k = sorted_array[:k]
    label_map_flip = dict((v,k) for k,v in label_map.items())
    
    y_pred = []
    for label_index in top_k:
        if print_flag:
            print("{} ({})".format(label_map_flip[label_index], preds[label_index]))
        y_pred.append(label_map_flip[label_index])
        
    return y_pred

#%%


def save2saved2tflite(model, output_model_path):
    saved_model_dir = '' #means current directory
    tf.saved_model.save(model, saved_model_dir) #saves to the current directory
    converter = tf.lite.TFLiteConverter.from_saved_model(saved_model_dir) 
    tflite_model = converter.convert() #converts our model into a .tflite model which flutter uses for ondevice machine learning
    with open(output_model_path, 'wb') as f: #to write the converted model into a file, written as binary so add 'wb' instead of 'w'
       f.write(tflite_model)

def save4mkeras2tflite(model, output_model_path):
    converter = tf.lite.TFLiteConverter.from_keras_model(q_aware_model)
    converter.optimizations = [tf.lite.Optimize.DEFAULT]
    quantized_tflite_model = converter.convert()
    converter = tf.lite.TFLiteConverter.from_keras_model(model)
    baseline_tflite_model = converter.convert()

#%%
# steps_per_epoch = len(X_train)//batch_size
# validation_steps = len(X_test)//batch_size # if you have validation data 
batch_size = 20 #40
epochs = 25   # 200

# dimensions of our images.
img_width, img_height = 224, 224

input_tensor = Input(shape=(224,224,3))

nb_training_samples =  128  # 1600 #32* 4
nb_validation_samples =  32 # 400 # Set parameter values 4(labels)*8(testing samples per label)

n_targets = 4

#%%

training_data_dir = 'wavelets/wavelet_selected/training'

training_datagen = image.ImageDataGenerator(
    rescale=1./255)

training_generator = training_datagen.flow_from_directory(
    training_data_dir,
    target_size=(img_height, img_width),
    batch_size=batch_size)

# validation generator configuration
validation_data_dir = 'wavelets/wavelet_selected/testing/'

validation_datagen = image.ImageDataGenerator(
    rescale=1./255)

validation_generator = validation_datagen.flow_from_directory(
    validation_data_dir,
    target_size=(img_height, img_width),
    batch_size=batch_size)

#%%

base_model = VGG16(weights='imagenet', include_top=False, input_tensor=input_tensor)
print('Model loaded.')
base_model.summary()

#%%

top_model = Sequential()
top_model.add(Flatten(input_shape=base_model.output_shape[1:]))
top_model.add(Dense(256, activation='relu'))
top_model.add(Dropout(0.5))
top_model.add(Dense(n_targets, activation='softmax'))

top_model.summary()


#%%

model = Model(inputs=base_model.input, outputs=top_model(base_model.output))
model.summary()


#%%

num_layers_to_freeze = 15


#%%

for layer in model.layers[:num_layers_to_freeze]:
    layer.trainable = False


model.compile(optimizer=optimizers.SGD(lr=1e-4, momentum=0.9), 
                      loss='categorical_crossentropy', 
                      metrics=['accuracy', top_5_accuracy])


# serialize model to JSON
model_json = model.to_json()
model_filename = "cough_model_artifacts/vgg16_model_{}_frozen_layers.json".format(num_layers_to_freeze)

with open(model_filename, "w") as json_file:
    json_file.write(model_json)
    
    
#%%

filepath = "cough_model_artifacts/esc50_vgg16_stft_weights_train_last_2_base_layers_best.hdf5"
metric = 'val_accuracy'

best_model_checkpoint = ModelCheckpoint(filepath, monitor=metric, verbose=5, save_best_only=True, mode='max')
callbacks_list = [best_model_checkpoint]


model.fit_generator(
    training_generator,
    steps_per_epoch=nb_training_samples/batch_size,
    epochs=epochs,
    validation_data=validation_generator,
    validation_steps=nb_validation_samples/batch_size,
    callbacks=callbacks_list)


#%%
label_map = (training_generator.class_indices)

#%% 
json = json.dumps(label_map)
f = open("cough_model_artifacts/cough_label_map.json","w")
f.write(json)
f.close()

#%%
top_model.save("cough_model_artifacts/cough_model", save_format="tf")


#%%


testing_dir = './wavelets/wavelet_selected/testing/'

y_true = []
y_pred = []


for label in label_map.keys():
    
    file_list = os.listdir(testing_dir + label)
    
    for file_name in file_list:
        img_path = testing_dir + label + '/' + file_name
        
        img = image.load_img(img_path, target_size=(224, 224))
        
        x = image.img_to_array(img)
        x = np.expand_dims(x, axis=0)* 1./255
        
        preds = model.predict(x)[0]
        
        y_true.append(label)
        y_pred.append(get_top_k_predictions(preds, label_map, k=1)[0])



#%%
        
cm = confusion_matrix(y_true, y_pred)

plot_confusion_matrix(cm, sorted(label_map.keys()), normalize=False, title = 'cough_model_artifacts/wavelet_cough_vgg16')

plot_confusion_matrix(cm, sorted(label_map.keys()), normalize=True, title = 'cough_model_artifacts/wavelet_cough_normalized')

#%%

print(classification_report(y_true, y_pred, target_names = sorted(label_map.keys()) ))


print('xxxxxxx Done Testing xxxxxxxx')

#%%

#saving tflite model
#save2saved2tflite(model, 'cough.tflite')



testing_dir = './wavelets/wavelet_live/'

y_true = []
y_pred = []
    
file_list = os.listdir(testing_dir)

for file_name in file_list:
    img_path = testing_dir + '/' + file_name

    img = image.load_img(img_path, target_size=(224, 224))
    
    x = image.img_to_array(img)
    x = np.expand_dims(x, axis=0)* 1./255
    
    preds = model.predict(x)[0]
    print("file: " + file_name)
    print("class: " + label)
    
    y_true.append(file_name)
    y_pred.append(get_top_k_predictions(preds, label_map, k=1)[0])
    cm = confusion_matrix(y_true, y_pred)
    plot_confusion_matrix(cm, sorted(label_map.keys()), normalize=False, title = 'cough_model_artifacts/cough_vgg16'+file_name)



#%%
        
# cm = confusion_matrix(y_true, y_pred)

# plot_confusion_matrix(cm, sorted(label_map.keys()), normalize=False, title = 'cough_model_artifacts/live_wavelet_cough_vgg16')

# plot_confusion_matrix(cm, sorted(label_map.keys()), normalize=True, title = 'cough_model_artifacts/live_wavelet_cough_normalized')

# #%%

# print(classification_report(y_true, y_pred, target_names = sorted(label_map.keys()) ))


print('xxxxxxx Done xxxxxxxx')
















