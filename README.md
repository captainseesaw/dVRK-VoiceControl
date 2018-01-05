# dVRK-VoiceControl
Voice Control for dVRK based on Google Cloud Speech API (https://cloud.google.com/speech/) and dVRK (https://github.com/jhu-dvrk/sawIntuitiveResearchKit/)

# Google Cloud API
The voice control uses the Streaming API. To enable continuous streaming and bypass the 60s limit set by Google, the GPRC connection is cutoff before the limit and re-established.
To setup Google Cloud API:
1. Make sure python is installed on the computer
2. If using pip, install google cloud by "pip install google.cloud"
3. If using pip, install pyaudio by "pip install pyaudio"
4. Setup the crendentials via Application Default Crendentials by "export GOOGLE_APPLICATION_CREDENTIALS=PATH_TO_KEY_FILE", Replace PATH_TO_KEY_FILE with the path to your JSON service account file. GOOGLE_APPLICATION_CREDENTIALS should be written out as-is (it's not a placeholder in the example above).
 

# dVRK
The control of dVRK is based on ROS. To control dVRK using voice:
1. "Power On" - power on the arms
2. "Power Off" - power off the arms
3. "Home" - home the arms
