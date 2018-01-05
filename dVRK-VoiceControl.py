#!/usr/bin/env python

""" Voice control of dVRK based on Google Cloud Speech API sample application using the streaming API.

NOTE: 
This module requires the additional dependency of ROS and dVRK. 
To insall:
	https://github.com/jhu-dvrk/sawIntuitiveResearchKit/wiki/CatkinBuild
This module requires the additional dependency `pyaudio`. 
To install using pip:
	pip install pyaudio
"""

# Cloud Speech API License:
# Copyright 2017 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#	   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# [START import_libraries]
from __future__ import division

import re
import sys

from google.cloud import speech
from google.cloud.speech import enums
from google.cloud.speech import types
from google.gax import BackoffSettings
import pyaudio
from six.moves import queue
from PyQt4.QtCore import *
from PyQt4.QtGui import *

import grpc
import logging
import time

import rospy
from std_msgs.msg import Bool, Empty, Float32
# [END import_libraries]

# Audio recording parameters
RATE = 16000
CHUNK = int(RATE / 10)	# 100ms
DEADLINE_SECS = 60
WRAP_IT_UP_SECS = 15
SECS_OVERLAP = 1

SPEECH_CONTEXT = types.SpeechContext(phrases=["home","teleop","scale","enable","set"])	# list of commands for dVRK


class VoiceRecognizer(QObject):
	def __init__(self, parent = None):
		super(VoiceRecognizer, self).__init__(parent)
		language_code = 'en-US'  # a BCP-47 language tag
		self.confirm_signal = pyqtSignal()
		self.client = speech.SpeechClient()
		self.config = types.RecognitionConfig(
			encoding=enums.RecognitionConfig.AudioEncoding.LINEAR16,
			sample_rate_hertz=RATE,
			language_code=language_code,
			speech_contexts=[SPEECH_CONTEXT])
		self.streaming_config = types.StreamingRecognitionConfig(
			config=self.config,
			interim_results=True)

		self.home_pub = rospy.Publisher('/dvrk/console/home', Empty, latch = True, queue_size = 1)	# HOME command publisher
		self.poff_pub = rospy.Publisher('/dvrk/console/power_off', Empty, latch = True, queue_size = 1)	# POWER OFF command publisher
		self.pon_pub = rospy.Publisher('/dvrk/console/power_on', Empty, latch = True, queue_size = 1)	# POWER ON command publisher
		self.tenable_pub = rospy.Publisher('/dvrk/console/teleop/enable', Bool, latch = True, queue_size = 1)	# TELEOP ENABLE command publisher
		self.tscale = rospy.Publisher('/dvrk/console/teleop/scale', Float32, latch = True, queue_size = 1)	# TELEOP SCALE command publisher
		self.tset_scale = rospy.Publisher('/dvrk/console/teleop/set_scale', Float32, latch = True, queue_size = 1)	# TELEOP SET SCALE command publisher

		self.exit = False

	def start_recognize(self):
		with MicrophoneStream(RATE, CHUNK) as stream:
			self.audio_generator = stream.generator()
			requests = (types.StreamingRecognizeRequest(audio_content=content)
						for content in self.audio_generator)

			self.responses = self.client.streaming_recognize(self.streaming_config, requests)

			# Now, put the transcription responses to use.
			try:
				while not self.exit:
					self.listen_print_loop(self.responses)

					# Discard this stream and create a new one.
					# Note: calling .cancel() doesn't immediately raise an RpcError
					# - it only raises when the iterator's next() is requested
					self.responses.cancel()
					self.audio_generator = stream.generator()
					logging.debug('Starting new stream')
					requests = (types.StreamingRecognizeRequest(audio_content=content)
								for content in self.audio_generator)

					self.responses = self.client.streaming_recognize(self.streaming_config, requests)

					if self.exit:
						break

			except grpc.RpcError:
				# This happens because of the interrupt handler
				print "error in GPRC"
				pass

	def listen_print_loop(self, responses):
		"""Iterates through server responses and prints them.

		The responses passed is a generator that will block until a response
		is provided by the server.

		Each response may contain multiple results, and each result may contain
		multiple alternatives; for details, see https://goo.gl/tjCPAU.	Here we
		print only the transcription for the top alternative of the top result.

		In this case, responses are provided for interim results as well. If the
		response is an interim one, print a line feed at the end of it, to allow
		the next result to overwrite it, until the response is a final one. For the
		final one, print a newline to preserve the finalized transcription.
		"""
		print "listen_print_loop started"
		time_to_switch = time.time() + DEADLINE_SECS - WRAP_IT_UP_SECS

		num_chars_printed = 0
		for response in responses:
			if time.time() > time_to_switch:
				print "time to cut off connection and make a new one"
				break
			if not response.results:
				continue

			# The `results` list is consecutive. For streaming, we only care about
			# the first result being considered, since once it's `is_final`, it
			# moves on to considering the next utterance.
			result = response.results[0]
			if not result.alternatives:
				continue

			# Display the transcription of the top alternative.
			transcript = result.alternatives[0].transcript

			# Display interim results, but with a carriage return at the end of the
			# line, so subsequent lines will overwrite them.
			#
			# If the previous result was longer than this one, we need to print
			# some extra spaces to overwrite the previous result
			overwrite_chars = ' ' * (num_chars_printed - len(transcript))

			if not result.is_final:
				sys.stdout.write(transcript + overwrite_chars + '\r')
				sys.stdout.flush()

				num_chars_printed = len(transcript)
			else:
				print(transcript + overwrite_chars)

				# analyze word and publish according msg
				self.analyze_word(transcript)

				# Exit recognition if any of the transcribed phrases could be
				# one of our keywords.
				if re.search(r'\b(exit|quit)\b', transcript, re.I):
					print('Exiting..')
					# cancel streaming responses, set exit = True to break the loop
					self.responses.cancel()
					self.exit = True
					break

				num_chars_printed = 0

				# clear commands, start new loop
				for i in range(0, len(self.command)):
					self.command[i] = 0

		print "listen and print loop broke"

	def analyze_word(self, transcript):
		if re.search(r'\b(home)\b', transcript, re.I):
            		self.home_pub.publish()
			print ("Home arms")
		if re.search(r'\b(power off)\b', transcript, re.I):
            		self.poff_pub.publish()
			print ("Power off arms")
		if re.search(r'\b(power on)\b', transcript, re.I):
            		self.pon_pub.publish()
			print ("Power on arms")
		# TODO: setup teleoperation
#		if re.search(r'\b(teleop enable)\b', transcript, re.I):
#            		self.tenable_pub.publish()
#			print ("Enable teleoperation")
#		if re.search(r'\b(teleop scale)\b', transcript, re.I):
#            		self.tscale_pub.publish()
#		if re.search(r'\b(teleop set scale)\b', transcript, re.I):
#            		self.tset_scale_pub.publish()

class MicrophoneStream(object):
	"""Opens a recording stream as a generator yielding the audio chunks."""

	def __init__(self, rate, chunk):
		self._rate = rate
		self._chunk = chunk

		# Create a thread-safe buffer of audio data
		self._buff = queue.Queue()
		self.closed = True

	def __enter__(self):
		self._audio_interface = pyaudio.PyAudio()
		self._audio_stream = self._audio_interface.open(
			format=pyaudio.paInt16,
			# The API currently only supports 1-channel (mono) audio
			# https://goo.gl/z757pE
			channels=1, rate=self._rate,
			input=True, frames_per_buffer=self._chunk,
			# Run the audio stream asynchronously to fill the buffer object.
			# This is necessary so that the input device's buffer doesn't
			# overflow while the calling thread makes network requests, etc.
			stream_callback=self._fill_buffer,
		)

		self.closed = False

		return self

	def __exit__(self, type, value, traceback):
		self._audio_stream.stop_stream()
		self._audio_stream.close()
		self.closed = True
		# Signal the generator to terminate so that the client's
		# streaming_recognize method will not block the process termination.
		self._buff.put(None)
		self._audio_interface.terminate()

	def _fill_buffer(self, in_data, frame_count, time_info, status_flags):
		"""Continuously collect data from the audio stream, into the buffer."""
		self._buff.put(in_data)
		return None, pyaudio.paContinue

	def generator(self):
		while not self.closed:
			# Use a blocking get() to ensure there's at least one chunk of
			# data, and stop iteration if the chunk is None, indicating the
			# end of the audio stream.
			chunk = self._buff.get()
			if chunk is None:
				return
			data = [chunk]

			# Now consume whatever other data's still buffered.
			while True:
				try:
					chunk = self._buff.get(block=False)
					if chunk is None:
						return
					data.append(chunk)
				except queue.Empty:
					break

			yield b''.join(data)


# [END audio_stream]

if __name__ == '__main__':
	rospy.init_node('dvrk_voice_control')
    	vr = VoiceRecognizer()
    	vr.start_recognize()
#	vr.analyze_word("teleop enable")
#	time.sleep(10)
