// Forwards captured mono Float32 frames to the main thread for PCM16 conversion.
class PcmCaptureProcessor extends AudioWorkletProcessor {
  process(inputs) {
    const input = inputs[0];
    if (input && input[0]) {
      // Copy the frame; the underlying buffer is reused by the render quantum.
      this.port.postMessage(input[0].slice(0));
    }
    return true;
  }
}

registerProcessor("pcm-capture", PcmCaptureProcessor);
