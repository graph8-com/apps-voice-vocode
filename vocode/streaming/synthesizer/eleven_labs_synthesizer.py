import os
import io
import asyncio
import logging
import time
import hashlib
import json
from pathlib import Path
import aiofiles
import aiofiles.os
from typing import Any, AsyncGenerator, Optional, Tuple, Union
import wave
import aiohttp
from opentelemetry.trace import Span

from vocode import getenv
from vocode.streaming.synthesizer.base_synthesizer import (
    BaseSynthesizer,
    SynthesisResult,
    encode_as_wav,
    tracer,
)
from vocode.streaming.models.synthesizer import (
    ElevenLabsSynthesizerConfig,
    SynthesizerType,
)
from vocode.streaming.agent.bot_sentiment_analyser import BotSentiment
from vocode.streaming.models.message import BaseMessage
from vocode.streaming.utils.mp3_helper import decode_mp3
from vocode.streaming.synthesizer.miniaudio_worker import MiniaudioWorker


ADAM_VOICE_ID = "pNInz6obpgDQGcFmaJgB"
ELEVEN_LABS_BASE_URL = "https://api.elevenlabs.io/v1/"


class ElevenLabsSynthesizer(BaseSynthesizer[ElevenLabsSynthesizerConfig]):
    def __init__(
        self,
        synthesizer_config: ElevenLabsSynthesizerConfig,
        logger: Optional[logging.Logger] = None,
        aiohttp_session: Optional[aiohttp.ClientSession] = None,
    ):
        super().__init__(synthesizer_config, aiohttp_session)

        import elevenlabs

        self.elevenlabs = elevenlabs

        self.api_key = synthesizer_config.api_key or getenv("ELEVEN_LABS_API_KEY")
        self.voice_id = synthesizer_config.voice_id or ADAM_VOICE_ID
        self.stability = synthesizer_config.stability
        self.similarity_boost = synthesizer_config.similarity_boost
        self.model_id = synthesizer_config.model_id
        self.optimize_streaming_latency = synthesizer_config.optimize_streaming_latency
        self.words_per_minute = 150
        self.experimental_streaming = synthesizer_config.experimental_streaming
        # self.use_caching = synthesizer_config.use_caching
        self.logger = logger
        # if self.use_caching:
        # Folder where cached files will be stored
        self.CACHE_FOLDER = Path("TTS_cache_11labs")

        # Ensure the cache folder exists
        os.makedirs(self.CACHE_FOLDER, exist_ok=True)

    
    async def update_metafile(metadata_filename):
        async with aiofiles.open(metadata_filename, "r+") as jsonFile:
            data = json.load(jsonFile)
            
            usage_count = data.get("usage_count", 1)
            data["usage_count"] = usage_count + 1

            jsonFile.seek(0)  # rewind
            json.dump(data, jsonFile)
            jsonFile.truncate()
        

    async def create_speech(
        self,
        message: BaseMessage,
        chunk_size: int,
        bot_sentiment: Optional[BotSentiment] = None,
    ) -> SynthesisResult:
        
        # Generate a unique hash key based on the text and voice settings
        text_hash = hashlib.sha256(
            message.text.lower().strip().encode('utf-8')
            ).hexdigest()
        filename = f"{text_hash}.mp3"
        filepath = self.CACHE_FOLDER / filename
        metadata_filename = f"{text_hash}.json"
        metadata_filepath = self.CACHE_FOLDER / metadata_filename

        if filepath.is_file():
            self.logger.debug('TTS: Cache-hit!')
            try:
                # Attempt to read the audio from the cache
                async with aiofiles.open(filepath, 'rb') as f:
                    audio_data = await f.read()
                
                output_bytes_io = decode_mp3(audio_data)

                # If successful, create the synthesis result from the cached audio
                return self.create_synthesis_result_from_wav(
                    synthesizer_config=self.synthesizer_config,
                    file=output_bytes_io,
                    message=message,
                    chunk_size=chunk_size,
                )
            except wave.Error as e:
                # If an error occurs, log it, delete the corrupted file, and proceed to synthesize
                self.logger.error(f"Corrupted cache file detected: {e}. Deleting and re-synthesizing.")
                await aiofiles.os.remove(filepath)

        voice = self.elevenlabs.Voice(voice_id=self.voice_id)
        if self.stability is not None and self.similarity_boost is not None:
            voice.settings = self.elevenlabs.VoiceSettings(
                stability=self.stability, similarity_boost=self.similarity_boost
            )
        url = ELEVEN_LABS_BASE_URL + f"text-to-speech/{self.voice_id}"

        if self.experimental_streaming:
            url += "/stream"

        if self.optimize_streaming_latency:
            url += f"?optimize_streaming_latency={self.optimize_streaming_latency}"
        headers = {"xi-api-key": self.api_key}
        body = {
            "text": message.text,
            "voice_settings": voice.settings.dict() if voice.settings else None,
        }
        if self.model_id:
            body["model_id"] = self.model_id

        create_speech_span = tracer.start_span(
            f"synthesizer.{SynthesizerType.ELEVEN_LABS.value.split('_', 1)[-1]}.create_total",
        )

        session = self.aiohttp_session
        response = await session.request(
            "POST",
            url,
            json=body,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=15),
        )
        if not response.ok:
            raise Exception(f"ElevenLabs API returned {response.status} status code")
        if self.experimental_streaming:
            return SynthesisResult(
                self.experimental_mp3_streaming_output_generator(
                    response, chunk_size, create_speech_span
                ),  # should be wav
                lambda seconds: self.get_message_cutoff_from_voice_speed(
                    message, seconds, self.words_per_minute
                ),
            )
        else:
            # cache-miss
            self.logger.debug('TTS: Cache-miss!')
            audio_data = await response.read()
            create_speech_span.end()
            convert_span = tracer.start_span(
                f"synthesizer.{SynthesizerType.ELEVEN_LABS.value.split('_', 1)[-1]}.convert",
            )
            output_bytes_io = decode_mp3(audio_data)
            
            # Cache logic starts

             # Save the audio data directly to the cache directory
            async with aiofiles.open(filepath, 'wb') as f:
                await f.write(audio_data)

            # Optionally, store the text prompt in a separate metadata file
            
            metadata_content = {
                "text": message.text,
                "voice_id": self.voice_id,
                "stability": self.stability,
                "similarity_boost":self.similarity_boost,
                "model_id":  self.model_id,
                "words_per_minute":self.words_per_minute,
                "usage_count": 1
            }
            async with aiofiles.open(metadata_filepath, 'w') as meta_file:
                await meta_file.write(json.dumps(metadata_content))

            # cache logic ends

            result = self.create_synthesis_result_from_wav(
                synthesizer_config=self.synthesizer_config,
                file=output_bytes_io,
                message=message,
                chunk_size=chunk_size,
            )
            convert_span.end()
            return result