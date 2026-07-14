# Pipecat Batch Runtime Contract (Sprint 4 / TASK-WEB-005, ST-1 spike)

Findings from the live spike (`voice-agent/scripts/pipecat_spike.py`) locking the
exact `pipecat-ai` API the Sprint 4 batch pipeline depends on. Same discipline as
`gradium-tts-contract.md`: verify the real API before building on it.

- **Version:** `pipecat-ai 1.5.0`, Python 3.14.2, installed from public PyPI.
  Pinned `pipecat-ai>=1.5,<2` in `voice-agent/requirements.txt`.
- **Footprint note:** the base package pulls heavy transitive deps (numpy, scipy,
  numba, onnxruntime, openai, resampy, soxr, pyloudnorm, ...). Expected for a voice
  framework; acceptable for the voice-agent runtime.

## Frame processor

- Base class: `pipecat.processors.frame_processor.FrameProcessor`.
- Override `async def process_frame(self, frame: Frame, direction: FrameDirection)`.
  - **Must** call `await super().process_frame(frame, direction)` first (handles
    system frames: `StartFrame`, `EndFrame`, etc.).
  - Emit downstream with `await self.push_frame(frame, direction)`.
  - Frames you do not transform must still be forwarded (`push_frame`) or the
    pipeline stalls / drops them.
- `FrameDirection` is `DOWNSTREAM` (default) or `UPSTREAM`.
- Custom `__init__` must call `super().__init__()`.

## Frame types for the batch loop

| Stage | In | Out | Constructor |
|---|---|---|---|
| STT | `InputAudioRawFrame` | `TranscriptionFrame` | `InputAudioRawFrame(audio: bytes, sample_rate: int, num_channels: int)` |
| echo | `TranscriptionFrame` | `TextFrame` | `TranscriptionFrame(text, user_id, timestamp, language=None, ...)` |
| TTS | `TextFrame` | `TTSAudioRawFrame` | `TTSAudioRawFrame(audio: bytes, sample_rate: int, num_channels: int, context_id=None)` |
| sink | `TTSAudioRawFrame` | (collect) | `TextFrame(text: str)` |

`StartFrame` and `EndFrame` also flow through the pipeline and reach the sink; the
capturing sink must filter to the audio frames it cares about.

## Driving a finite (batch) pipeline

```python
pipeline = Pipeline([stt, echo, tts, sink])   # pipecat.pipeline.pipeline.Pipeline
task = PipelineTask(pipeline, params=PipelineParams(),
                    enable_rtvi=False, enable_turn_tracking=False,
                    cancel_on_idle_timeout=False, check_dangling_tasks=False)
await task.queue_frames([InputAudioRawFrame(...), EndFrame()])
runner = PipelineRunner(handle_sigint=False)   # handle_sigint=False is REQUIRED off the main thread
await runner.run(task)
# read the collected bytes from the sink processor
```

- Queue the input frames **and** a trailing `EndFrame` up front; `PipelineRunner.run`
  returns once the `EndFrame` reaches the end of the pipeline (`auto_end`).
- `handle_sigint=False` is **required** when driving the pipeline off the main thread
  (the HTTP server request threads) — otherwise it tries to install signal handlers.
- Output is collected by a terminal `FrameProcessor` (a "sink") that appends
  `TTSAudioRawFrame.audio` bytes; the caller reads them after `run()` returns.

## Runner-API decision (deprecation)

`PipelineTask` / `PipelineRunner` are **deprecated since 1.3.0** (removed in 2.0.0) in
favour of `PipelineWorker` / `WorkerRunner`. However, the new `WorkerRunner` only
consumes frames queued **after** it is live: queuing input + `EndFrame` up front (the
natural batch pattern) leaves the `EndFrame` unconsumed and the worker idle-hangs.

Decision for Sprint 4 (batch): use `PipelineTask` / `PipelineRunner` (which support
"queue everything up front, run to completion" directly), pin `pipecat-ai<2`, and
silence only their `DeprecationWarning` at our call site. Revisit the runner API in
**Sprint 5**, where a real streaming transport makes the live/worker model natural.

## Verified

- Spike pipeline `FakeSTT -> Echo -> FakeTTS -> CaptureSink` produced the expected
  bytes end to end (`PARITY OK`), completing in ~2 s. Sink saw
  `['StartFrame', 'TTSAudioRawFrame', 'EndFrame']`.
