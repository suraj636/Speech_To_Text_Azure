from fastapi import FastAPI, File, UploadFile, HTTPException, Response
import soundfile as sf
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from pymongo import MongoClient
import requests
import io
import os
import logging
import scipy.signal as signal
import tempfile
from pymongo.server_api import ServerApi


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Replace this with the origin of your frontend
    allow_credentials=True,
    allow_methods=["GET","POST"],
    allow_headers=["*"],
)

uri=os.getenv("Mongodb_Cs")

# Connect to MongoDB Atlas
client = MongoClient(uri, server_api=ServerApi('1'))
db = client["SpeechToText"]
collection = db["Audio_Transcription"]


azure_subscription_key = os.getenv("Azure_subscription_key")
azure_access_token = os.getenv("Azure_access_token")
azure_base_url = os.getenv("Azure_base_url")

class ProcessedAudio(BaseModel):
    file_name: str

# Function to check if the audio is in WAV format
def is_wav(data):
    # Check if the data starts with the WAV header
    return data.startswith(b'RIFF') and data[8:12] == b'WAVE'


@app.get("/")
async def read_root():
    return {"message": "Welcome to Speech to Text API"}

@app.post("/process_audio_/")
async def process_audio_endpoint(input_file: UploadFile = File(...), target_sr: int = 8000, language_code: str = "en-US"):
    #logging.info("Process_Audio is called")
    print(str("API is called"))
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_audio_file:
            content = await input_file.read()

            # Check if the audio is in WAV format
            if not is_wav(content):
                # Convert audio to WAV format
                audio, sr = sf.read(io.BytesIO(content))
                with io.BytesIO() as wav_buffer:
                    sf.write(wav_buffer, audio, sr, format='WAV', subtype='PCM_16')
                    content = wav_buffer.getvalue()

            temp_audio_file.write(content)

            print(str(("We can say that the audio has been converted into wav")))

            audio, sr = sf.read(temp_audio_file.name)

            #logging.info("File has been stored and now ready to be processed")

            if audio.ndim > 1:
                audio = audio[:, 0]
            #logging.info("Audio file channel is converted to Single Channel")

            if sr != target_sr:
                # Resample audio using scipy
                audio = signal.resample(audio, int(len(audio) * target_sr / sr))
                sr = target_sr
                logging.info("Audio file's sampling rate has been set to 8000Hz")
            logging.info("Audio file's sampling rate has been set to 8000kHz")

            output_file = io.BytesIO()

            sf.write(output_file, audio, target_sr, format='WAV', subtype='PCM_16')

            output_file.seek(0)
            audio_data = output_file.read()

        print(str("Header is initialized for sending the request to azure"))
        headers = {
            "Content-Type": "audio/wav",
            "Authorization": f"Bearer {azure_access_token}",
            "Ocp-Apim-Subscription-Key": azure_subscription_key
        }
        params = {
            "language": language_code,
        }
        
        #language_code="hi-EN"
        print(str(language_code))
        azure_speech_api_url = f"{azure_base_url}?language={language_code}"
        print(str(azure_speech_api_url))

        response = requests.post(azure_base_url, headers=headers, params=params, data=audio_data)
        #logging.info("Response is received")
        response.raise_for_status()

        # Extracting transcription from the response
        transcription = response.json().get("DisplayText", "Transcription not available")
        #logging.info("Translated Text :",transcription)

        # Store data in MongoDB
        #audio_doc = {
         #   "audio": io.BytesIO(content).read(),  # Store the original audio content
          #  "transcription": transcription
        #}

        # Store the audio file in MongoDB using GridFS
        #audio_id = fs.put(io.BytesIO(content), filename=input_file.filename)

        # Extracting transcription from the response
        #transcription = "Transcription not available"
        logging.info("Converting the audio to base64 so that it can be stored in the database")

        # Convert the audio data to base64 format
        #audio_base64 = base64.b64encode(audio_data)
        #audio_data_base64 = base64.b64encode(audio_data).decode('utf-8')

        # Store data in MongoDB
        audio_doc = {
                "audio":audio_data,#audio_data_base64,#Binary.createFromBase64(audio_base64),#io.BytesIO(content).read(),
                "transcription": transcription
            }
        collection.insert_one(audio_doc)

        return transcription
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error calling Azure Speech API: {str(e)}")
