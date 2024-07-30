import asyncio
import hashlib
from typing import Optional

from loguru import logger

from vocode import getenv
from vocode.streaming.models.audio import AudioEncoding, SamplingRate
from vocode.streaming.models.message import BaseMessage
from vocode.streaming.models.synthesizer import CartesiaSynthesizerConfig
from vocode.streaming.synthesizer.base_synthesizer import BaseSynthesizer, SynthesisResult
from vocode.streaming.utils.create_task import asyncio_create_task


class CartesiaSSE(BaseSynthesizer[CartesiaSynthesizerConfig]):
    def __init__(
        self,
        synthesizer_config: CartesiaSynthesizerConfig,
    ):
        super().__init__(synthesizer_config)

        # Lazy import the cartesia module
        try:
            from cartesia import AsyncCartesia
        except ImportError as e:
            raise ImportError(f"Missing required dependancies for CartesiaSynthesizer") from e

        self.api_key = synthesizer_config.api_key or getenv("CARTESIA_API_KEY")
        if not self.api_key:
            raise ValueError("Missing Cartesia API key")

        self.cartesia_tts = AsyncCartesia

        if synthesizer_config.audio_encoding == AudioEncoding.LINEAR16:
            match synthesizer_config.sampling_rate:
                case SamplingRate.RATE_44100:
                    self.output_format = {
                        "sample_rate": 44100,
                        "encoding": "pcm_s16le",
                        "container": "raw",
                    }
                case SamplingRate.RATE_22050:
                    self.output_format = {
                        "sample_rate": 22050,
                        "encoding": "pcm_s16le",
                        "container": "raw",
                    }
                case SamplingRate.RATE_16000:
                    self.output_format = {
                        "sample_rate": 16000,
                        "encoding": "pcm_s16le",
                        "container": "raw",
                    }
                case SamplingRate.RATE_8000:
                    self.output_format = {
                        "sample_rate": 8000,
                        "encoding": "pcm_s16le",
                        "container": "raw",
                    }
                case _:
                    raise ValueError(
                        f"Unsupported PCM sampling rate {synthesizer_config.sampling_rate}"
                    )
        elif synthesizer_config.audio_encoding == AudioEncoding.MULAW:
            self.channel_width = 2
            self.output_format = {
                "sample_rate": 8000,
                "encoding": "pcm_mulaw",
                "container": "raw",
            }
        else:
            raise ValueError(f"Unsupported audio encoding {synthesizer_config.audio_encoding}")

        if not isinstance(self.output_format["sample_rate"], int):
            raise ValueError(f"Invalid type for sample_rate")
        self.sampling_rate = self.output_format["sample_rate"]
        self.num_channels = 1
        self.model_id = synthesizer_config.model_id
        self.voice_id = synthesizer_config.voice_id
        self.client = self.cartesia_tts(api_key=self.api_key)
        self.voice_embedding = self.client.voices.get(id=self.voice_id)["embedding"]

    async def create_speech_uncached(
        self,
        message: BaseMessage,
        chunk_size: int,
        is_first_text_chunk: bool = False,
        is_sole_text_chunk: bool = False,
    ) -> SynthesisResult:
        chunk_queue: asyncio.Queue[Optional[bytes]] = asyncio.Queue()
        asyncio_create_task(
            self.process_chunks(message, chunk_size, chunk_queue),
        )

        return SynthesisResult(
            self.chunk_result_generator_from_queue(chunk_queue),
            lambda seconds: self.get_message_cutoff_from_voice_speed(message, seconds),
        )

    async def process_chunks(
        self, message: BaseMessage, chunk_size: int, chunk_queue: asyncio.Queue[Optional[bytes]]
    ):
        try:
            generator = await self.client.tts.sse(
                model_id=self.model_id,
                transcript=message.text,
                voice_embedding=self.client.voices.get(id=self.voice_id)["embedding"],
                stream=True,
                output_format=self.output_format,
            )

            buffer = bytearray()
            async for event in generator:
                audio = event.get("audio")
                buffer.extend(audio)
                while len(buffer) >= chunk_size:
                    chunk_queue.put_nowait(bytes(buffer[:chunk_size]))
                    buffer = buffer[chunk_size:]

            if buffer:
                chunk_queue.put_nowait(bytes(buffer))
        except Exception as e:
            logger.debug(
                f"Caught error while processing audio chunks from CartesiaSynthesizer: {e}"
            )
        finally:
            chunk_queue.put_nowait(None)  # Sentinel to indicate end of stream

    async def chunk_result_generator_from_queue(self, chunk_queue: asyncio.Queue[Optional[bytes]]):
        while True:
            chunk = await chunk_queue.get()
            if chunk is None:
                break
            yield SynthesisResult.ChunkResult(chunk=chunk, is_last_chunk=False)
        yield SynthesisResult.ChunkResult(chunk=b"", is_last_chunk=True)

    @classmethod
    def get_voice_identifier(cls, synthesizer_config: CartesiaSynthesizerConfig):
        hashed_api_key = hashlib.sha256(f"{synthesizer_config.api_key}".encode("utf-8")).hexdigest()
        return ":".join(
            (
                "cartesia",
                hashed_api_key,
                str(synthesizer_config.voice_id),
                str(synthesizer_config.model_id),
                synthesizer_config.audio_encoding,
            )
        )

    async def tear_down(self):
        await super().tear_down()
        await self.client.close()
