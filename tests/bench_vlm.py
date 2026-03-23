"""
VLM benchmark for NanoLLM on Jetson Orin NX 16GB
Measures: model load time, peak memory, inference latency (1/4/8 frames)
"""
import time
import resource
import numpy as np
from PIL import Image
from nano_llm import NanoLLM, ChatHistory

MODEL = "Efficient-Large-Model/VILA1.5-3b"
PROMPT = "Describe what is happening in this image in one sentence."
FRAME_COUNTS = [1, 4, 8]
WARMUP_RUNS = 2
MEASURE_RUNS = 5

def make_test_frame(width=384, height=384):
    """Generate a random test frame (simulates nvvidconv RGBA output at 384x384)."""
    arr = np.random.randint(0, 255, (height, width, 3), dtype=np.uint8)
    return Image.fromarray(arr, mode="RGB")

def mem_mb():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024

def run_inference(model, frames, prompt, max_new_tokens=64):
    """Run inference using ChatHistory embedding (NanoLLM multimodal API)."""
    chat = ChatHistory(model)
    for img in frames:
        chat.append('user', image=img)
    chat.append('user', text=prompt)
    embedding, _ = chat.embed_chat()
    tokens = []
    for token in model.generate(embedding, max_new_tokens=max_new_tokens, streaming=True):
        tokens.append(token)
    return "".join(tokens)

print(f"=== NanoLLM VLM Benchmark ===")
print(f"Model: {MODEL}\n")

# --- Load model ---
print("[1/3] Loading model...", flush=True)
t0 = time.time()
model = NanoLLM.from_pretrained(MODEL, api="mlc", quantization="q4f16_ft")
load_time = time.time() - t0
print(f"      Load time : {load_time:.1f}s")
print(f"      RSS memory: {mem_mb()} MB\n")

# --- Warmup ---
print("[2/3] Warming up...", flush=True)
test_img = make_test_frame()
for _ in range(WARMUP_RUNS):
    run_inference(model, [test_img], PROMPT)

# --- Benchmark per frame count ---
print("[3/3] Measuring inference latency...\n")
results = {}
for n_frames in FRAME_COUNTS:
    frames = [make_test_frame() for _ in range(n_frames)]
    latencies = []
    for _ in range(MEASURE_RUNS):
        t0 = time.time()
        run_inference(model, frames, PROMPT)
        latencies.append(time.time() - t0)
    avg = sum(latencies) / len(latencies)
    results[n_frames] = avg
    print(f"  {n_frames} frame(s): avg {avg*1000:.0f}ms  "
          f"(min {min(latencies)*1000:.0f}ms, max {max(latencies)*1000:.0f}ms)")

print("\n=== Summary ===")
print(f"Model load : {load_time:.1f}s")
for n, t in results.items():
    print(f"{n:>2} frame(s): {t*1000:.0f}ms/inference  ({1/t:.2f} inferences/sec)")
print(f"RSS memory : {mem_mb()} MB")
