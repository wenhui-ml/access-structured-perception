# Controlled local serving — REGISTERED AS PRIMARY, **NOT RUN**

> **Status: not run.** The registration named controlled local vLLM as the primary arm
> with OpenRouter as replication. Every number in the paper comes from the **API arm
> only**, at the user's explicit instruction not to use the GPU. This file is kept as the
> recipe for future-work item (iii) — adding the local arm and reporting its divergence
> from the API arm, as the registration intended.
>
> What the API arm keeps: pinned model slugs verified against the live catalogue,
> temperature 0, provider-side reasoning disabled, the returned model fingerprint recorded
> on every call, and per-call token accounting from the provider's own usage field.
> What it loses: provider routing, quantisation we cannot inspect, and silent revision
> changes (the fingerprint detects one, it does not prevent one).
>
> Note also that GPU work on this host goes through slurm, so nothing here should be run
> outside a scheduled job. `scripts/methods/asp.py` pins the local CLIP embedder to
> `device="cpu"` for the same reason.

Pin everything:

```bash
pip install vllm==<pin>          # log exact version + CUDA build
# one model at a time, single accelerator, no quantization, no prefix cache
vllm serve Qwen/Qwen3.8-27B            --dtype bfloat16 --enable-prefix-caching=false --max-num-seqs 1 --port 8000
vllm serve google/gemma-4-31b-it       --dtype bfloat16 --enable-prefix-caching=false --max-num-seqs 1 --port 8000
vllm serve Qwen/Qwen3-Omni-30B-A3B-Instruct --dtype bfloat16 --enable-prefix-caching=false --max-num-seqs 1 --port 8000
vllm serve Qwen/Qwen3-VL-8B-Instruct   --dtype bfloat16 --enable-prefix-caching=false --max-num-seqs 1 --port 8000
vllm serve Qwen/Qwen2.5-VL-7B-Instruct --dtype bfloat16 --enable-prefix-caching=false --max-num-seqs 1 --port 8000
```

Point the harness at it (OpenAI-compatible):
```bash
export OPENROUTER_API_KEY=dummy
export ASP_API_URL=http://localhost:8000/v1/chat/completions   # client override
```
Log per run: model repo SHA, tokenizer hash, vllm version, generation_config
hash -> results/traces/serving_manifest.json. Then re-run the identical grid
through OpenRouter (secondary) and report per-cell |local - API| in App. D.
