#!/usr/bin/env python3
"""Minimal OpenAI-compatible client with strict per-decision token-budget accounting.

Primary arm: locally served vLLM. Replication arm: OpenRouter. Point ASP_API_URL at
whichever endpoint you mean; the budget accounting below is identical for both, which
is what makes the local-vs-API delta a measured quantity rather than a confound.

Every method (ASP and all baselines) MUST route calls through BudgetedSession so
that the equal-budget comparison of the paper (Table 2) is enforced by code,
not by convention. A session raises BudgetExhausted once the per-decision
budget B is spent (prompt + image + completion tokens, as reported by the API).

Env: OPENROUTER_API_KEY (replication arm), ASP_API_URL (defaults to OpenRouter)
"""
from __future__ import annotations
import base64
import json
import os
import random
import time
from dataclasses import dataclass, field

import requests

API_URL = os.environ.get("ASP_API_URL", "https://openrouter.ai/api/v1/chat/completions")

# Retry ladder for provider-side faults (see chat() for the three modes this covers).
# 8 tries with a 60s cap spans ~4 minutes of upstream rate-limiting, which is the
# observed duration of a DeepInfra shed on the shared gemma endpoints.
RETRIES = 8
BACKOFF_CAP = 60.0

# Slugs are NOT verified at import time and MUST NOT be trusted blind: OpenRouter
# renames and retires them. Run `python scripts/check_models.py` first -- it queries
# the live /models endpoint and reports which of these exist and accept images.
#
# REGISTERED grid (Sec 5.1), kept verbatim for the record and NOT used to run anything.
# API availability, checked against the live 421-model catalogue: qwen3.8-27b, gemma-4-31b
# and qwen3-vl-8b resolve; qwen2.5-vl-7b and qwen3-omni-30b-a3b DO NOT EXIST on OpenRouter.
# Only 3 of the 5 registered backbones are reachable, which is a deviation with a reason,
# not something to paper over. Do NOT map qwen3-vl-30b-a3b onto the qwen3-omni-30b-a3b key:
# Omni is a different model class (audio+video), so the substitute goes in under its own
# name and the paper says which slot it fills.
REGISTERED = {
    "qwen3.8-27b": "qwen/qwen3.8-27b",
    "gemma-4-31b": "google/gemma-4-31b-it",
    "qwen3-omni-30b-a3b": "qwen/qwen3-omni-30b-a3b-instruct",
    "qwen3-vl-8b": "qwen/qwen3-vl-8b-instruct",
    "qwen2.5-vl-7b": "qwen/qwen2.5-vl-7b-instruct",
}

# The MEASURED ladder: what scripts/run_grid.py actually runs, in ascending parameter
# order, because the x-axis of P2 is parameter count. Every slug here was verified present
# and image-capable, and its tokens/frame measured (IMG_TOKENS below). Two entries are
# substitutions for registered slugs that do not exist; docs/PROTOCOL.md's execution
# record and notes/deviations.md carry the mapping.
MODELS = {
    "ministral-3b":      "mistralai/ministral-3b-2512",        #  3B   substitute for the 7B slot
    "qwen3-vl-8b":       "qwen/qwen3-vl-8b-instruct",          #  8B   registered
    "gemma-3-12b":       "google/gemma-3-12b-it",              # 12B   added, fills the 8->27 gap
    # 14B, added late: gemma-3-12b is served by exactly ONE provider (DeepInfra) and that
    # provider shed load for long enough to lose all 24 of its main cells in one pass. A
    # ladder whose mid-rung depends on a single upstream endpoint is a ladder with a hole,
    # so the gap is filled twice, on two different providers. Measured 432 tok/frame.
    "ministral-14b":     "mistralai/ministral-14b-2512",       # 14B   second gap-filler
    "qwen3.8-27b":       "qwen/qwen3.8-27b",                   # 27B   registered (flagship)
    "qwen3-vl-30b-a3b":  "qwen/qwen3-vl-30b-a3b-instruct",     # 30B/A3B substitute for Omni
    "gemma-4-31b":       "google/gemma-4-31b-it",              # 31B   registered
}

# PILOT grid: small multimodal models for API-only validation of the pipeline.
# These are NOT the registered backbones. Any number produced with them is a pilot
# number and must be reported as such -- see docs/PILOT.md for why that distinction
# is load-bearing (Assumption 1 may simply not hold at this scale, in which case a
# null result here says nothing about the theory).
# Verified present and image-capable via scripts/check_models.py against the live
# catalogue. Slugs I first guessed (qwen2.5-vl-3b/7b, pixtral-12b, llama-3.2-11b-vision)
# do NOT exist on OpenRouter -- which is exactly why check_models.py runs first.
PILOT_MODELS = {
    # All probed with a real single-frame question (scripts/probe_models.py) and, where the
    # first answer was empty, re-probed with reasoning disabled. Open-weight, image-capable,
    # <=31B total OR active -- the class Sec 5.1 is about. tok/frame is MEASURED where
    # calibrated (scripts/calibrate_tokens.py), else the one-frame prompt_tokens.
    "ministral-3b":      "mistralai/ministral-3b-2512",       # 3B      432 tok/frame
    "qwen3-vl-8b":       "qwen/qwen3-vl-8b-instruct",         # 8B      302   (registered)
    "qwen3-vl-8b-think": "qwen/qwen3-vl-8b-thinking",         # 8B      ~326
    "qwen3.5-9b":        "qwen/qwen3.5-9b",                   # 9B      ~324
    "gemma-3-12b":       "google/gemma-3-12b-it",             # 12B     259
    "gemma-3-27b-alt":   "google/gemma-3-27b-it",             # 27B     259   (JUDGE: do not use as backbone)
    "qwen3.5-27b":       "qwen/qwen3.5-27b",                  # 27B     ~337
    "qwen3.6-27b":       "qwen/qwen3.6-27b",                  # 27B     ~327
    "qwen3.8-27b":       "qwen/qwen3.8-27b",                  # 27B     ~368  (REGISTERED)
    "qwen3-vl-30b-a3b":  "qwen/qwen3-vl-30b-a3b-instruct",    # 30B/A3B 302
    "nemotron-omni-30b": "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
                                                              # 30B/A3B omni, FREE
    "gemma-4-31b":       "google/gemma-4-31b-it",             # 31B     295   (REGISTERED)
    "glm-4.6v":          "z-ai/glm-4.6v",                     # ?       ~413
    "qwen3.5-122b-a10b": "qwen/qwen3.5-122b-a10b",            # 122B/A10B
}

# FAILED the probe -- kept as a record so nobody re-adds them by name:
#   google/gemma-3-4b-it, mistralai/mistral-small-3.2-24b, google/gemma-4-26b-a4b-it:free
#       -> persistent provider 429
#   google/gemma-4-26b-a4b-it -> "There is no mug in this image." (paid tier, sees nothing)
#   mistralai/ministral-8b "Brown", ministral-14b "Gray", mistral-small-3.1-24b "Black.",
#       bytedance/ui-tars-1.5-7b "Brown", nvidia/nemotron-nano-12b-v2-vl "brown"
#       (and 3,359 prompt tokens for ONE frame)
#   deepseek/deepseek-v4-flash-vision-exp -> HTTP 404, no endpoints
#   meta-llama/llama-4-scout answers correctly but costs 753 tokens/frame, which leaves
#       room for only 5 frames at B=4096 -- unusable for a horizon-wall baseline.

if os.environ.get("ASP_PILOT"):
    MODELS.update(PILOT_MODELS)


# MEASURED per-image prompt-token cost, by differencing 0/1/3-frame requests
# (scripts/calibrate_tokens.py). Linear in the frame count for every model here.
# Every value is ABOVE the 240 the paper first assumed, which is why w must be
# derived from the budget rather than fixed at 16.
# Re-measured on the 640x480 SEW-Bench renders (scripts/calibrate_tokens.py); the
# values are unchanged from the 512x384 smoke frames, because every model here tiles
# to a fixed visual-token budget rather than scaling with resolution.
# Hard per-request image cap, imposed by the PROVIDER and not by us. Mistral's endpoint
# rejects any request carrying more than eight images with HTTP 400 "Total number of images
# exceeds the maximum allowed of 8" -- a deterministic constraint, not a transient fault, and
# verified per model against the live endpoint (probe at n=16: both Mistral models capped,
# both Gemma and all three Qwen backbones served 16 fine). It matters because Uniform-w is
# defined by a frame COUNT, so on a capped backbone w can be limited by the provider rather
# than by B, and a comparison that did not record which of the two was binding would be
# reporting an equal-budget result that was really an equal-provider-limit result.
IMG_CAP = {
    "mistralai/ministral-3b-2512": 8,
    "mistralai/ministral-14b-2512": 8,
    # DeepInfra caps this one at 30, discovered at the P3 budget where Uniform-w wants 62
    # frames: HTTP 400 "Too many images in request: 62 > 30". The limit is per provider AND
    # per model, so it has to be probed per endpoint rather than assumed from a family.
    "google/gemma-3-12b-it": 30,
}

IMG_TOKENS = {
    "google/gemma-3-12b-it": 259,
    "google/gemma-3-27b-it": 259,
    "google/gemma-4-31b-it": 268,
    "qwen/qwen3-vl-8b-instruct": 302,
    "qwen/qwen3-vl-30b-a3b-instruct": 302,
    "qwen/qwen3.8-27b": 302,
    "mistralai/ministral-3b-2512": 432,
    "mistralai/ministral-14b-2512": 432,
}


class BudgetExhausted(Exception):
    pass


# "jpg" is a file extension, not a MIME subtype. Deriving the data-URI type from the
# extension emitted "data:image/jpg", which Qwen's provider happens to tolerate and
# DeepInfra (Gemma) rejects with a 422 whose message is about message ROLES -- so the
# whole Gemma family looked like a broken backbone rather than a one-word bug here.
_MIME = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "webp": "webp", "gif": "gif"}


def _img_content(path: str) -> dict:
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    ext = os.path.splitext(path)[1].lstrip(".").lower()
    return {"type": "image_url",
            "image_url": {"url": f"data:image/{_MIME.get(ext, 'jpeg')};base64,{b64}"}}


@dataclass
class BudgetedSession:
    model_key: str
    budget: int = 4096                 # per-decision budget B (tokens)
    temperature: float = 0.0
    spent: int = 0
    calls: list = field(default_factory=list)   # audit trail -> router traces (App. D)
    by_channel: dict = field(default_factory=lambda: {"Bs": 0, "Br": 0, "Bc": 0, "rho": 0})

    # Per-image token cost, used for the PRE-call estimate. Measured per model and
    # written here by scripts/calibrate_tokens.py; the fallback is deliberately
    # pessimistic so an uncalibrated model over-reserves rather than over-spends.
    img_tokens: int = 320       # conservative default; override from IMG_TOKENS below
    img_cap: int = 10**6        # provider images-per-request limit; override from IMG_CAP
    strict: bool = True               # refuse a call whose ESTIMATE exceeds the budget
    no_reasoning: bool = True         # bill-free, deterministic short answers (see chat())
    _reasoning_mandatory: bool = False  # latched when a provider refuses to disable it

    def __post_init__(self):
        # Use the measured constant when we have one; a guess here silently converts
        # the equal-budget comparison into an unequal one.
        m = IMG_TOKENS.get(MODELS.get(self.model_key, ""))
        if m:
            self.img_tokens = m
        c = IMG_CAP.get(MODELS.get(self.model_key, ""))
        if c:
            self.img_cap = c

    def remaining(self) -> int:
        return self.budget - self.spent

    @staticmethod
    def _est_text_tokens(text: str) -> int:
        # ~4 chars/token for English + JSON; only used for the pre-call reservation.
        return (len(text) + 3) // 4

    def estimate(self, text: str, n_images: int, max_completion: int) -> int:
        return self._est_text_tokens(text) + n_images * self.img_tokens + max_completion

    def chat(self, text: str, images: list[str] | None = None,
             max_completion: int = 512, tag: str = "") -> str:
        if self.remaining() <= 0:
            raise BudgetExhausted(f"budget {self.budget} exhausted")
        n_img = len(images or [])
        est = self.estimate(text, n_img, max_completion)
        if images and len(images) > self.img_cap:
            # Checked BEFORE the images are read and encoded: this is a caller bug, and there
            # is no reason to base64 a megabyte of frames to discover it. Truncating instead
            # of raising would quietly turn Uniform-16 into Uniform-8 and report the result
            # under the wrong name, so callers that can legitimately send fewer frames clamp
            # to self.img_cap themselves and log which limit bound (see baselines.py).
            raise RuntimeError(
                f"{MODELS[self.model_key]} accepts at most {self.img_cap} images per request "
                f"(provider limit); caller passed {len(images)} for tag={tag}. Clamp at the "
                f"call site and record w_limited_by='provider'.")
        if self.strict and est > self.remaining():
            # Equal-budget comparison is only meaningful if it binds BEFORE the spend.
            # Previously the budget was checked only on entry, so any single oversized
            # call (e.g. Uniform-16 sending 16 images at B=4096) sailed past it and the
            # overshoot was merely logged -- asymmetrically across methods, since
            # many-small-call methods like Asp were correctly truncated. That made the
            # headline table a comparison at unequal budgets.
            raise BudgetExhausted(
                f"call '{tag}' needs ~{est} tokens (text+{n_img} img+{max_completion} out) "
                f"but only {self.remaining()} of {self.budget} remain")
        content: list[dict] = [{"type": "text", "text": text}]
        for p in images or []:
            content.append(_img_content(p))
        payload = {
            "model": MODELS[self.model_key],
            "messages": [{"role": "user", "content": content}],
            "temperature": self.temperature,
            "max_tokens": min(max_completion, self.remaining()),
            "usage": {"include": True},
        }
        # Internal reasoning tokens are BILLED and count against B (Sec 4.5), and on a
        # reasoning backbone they swamp short calls: qwen3.8-27b spent 84 reasoning tokens
        # to answer "White", qwen3.6-27b 422. With the router's 8-token classify call that
        # returned an EMPTY string, so z silently fell back to CMP on every query and the
        # router stopped routing. Disabling reasoning fixes that and is what the thesis
        # wants anyway: Asp supplies depth through explicit access ROUNDS (Thm 3-4), so a
        # backbone thinking longer internally is a confound, not the mechanism under test.
        # reasoning.exclude only hides the tokens -- it still bills them -- so it is useless
        # here; reasoning.enabled=false actually turns it off (verified: 2 completion
        # tokens, 0 reasoning tokens, correct answer).
        if self.no_reasoning and not self._reasoning_mandatory:
            payload["reasoning"] = {"enabled": False}
        headers = {"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"}
        # OpenRouter proxies to third-party providers, and a provider can return 422 or
        # 429 for reasons that have nothing to do with our payload (role-normalisation
        # quirks, a temporarily unavailable image endpoint). Observed live: gemma-3-4b-it
        # returned 422 then 429 for an image request that qwen3-vl-8b served fine. Those
        # are retryable; a 4xx we actually caused is not, so surface the body either way.
        # Three failure modes seen live on this grid, all of them transient and all of them
        # capable of losing a whole cell if treated as fatal:
        #   (a) HTTP 429 "temporarily rate-limited upstream" -- DeepInfra shed load on
        #       gemma-3-12b for minutes at a time. The old ladder (2**attempt, 5 tries)
        #       gave up after 15s and cost 21 cells in one pass.
        #   (b) HTTP 400 whose body is "Provider returned error" -- an UPSTREAM fault
        #       wearing a client-error code. Verified by replaying the exact 8-image
        #       ministral-3b payload that 400'd: it served fine. A real payload bug is
        #       deterministic, so retrying costs one extra call and distinguishes them.
        #   (c) HTTP 200 whose body carries {"error": ...} and NO "choices" -- this used to
        #       surface as KeyError: 'choices' and kill the process.
        # Retry-After is honoured when the provider sends it; otherwise exponential with
        # jitter, so parallel workers do not re-collide after every backoff.
        def _transient(resp) -> bool:
            if resp.status_code in (408, 409, 422, 429, 500, 502, 503, 504):
                return True
            if resp.status_code == 200:
                try:
                    return "choices" not in resp.json()
                except Exception:
                    return True
            if resp.status_code == 400:
                low = resp.text.lower()
                return ("provider returned error" in low
                        and "reasoning is mandatory" not in low)
            return False

        # (d) The request can fail below HTTP entirely -- "Connection aborted / Connection
        # reset by peer" from the proxy, a read timeout on a slow multi-image call. requests
        # RAISES those instead of returning a response, so the status-code ladder above never
        # sees them and the cell died on the first one. They are the most obviously retryable
        # failure of the four.
        def _sleep(attempt: int, resp=None):
            hinted = resp.headers.get("Retry-After") if resp is not None else None
            try:
                wait = float(hinted) if hinted else None
            except ValueError:
                wait = None
            if wait is None:
                wait = min(BACKOFF_CAP, 2.0 ** attempt)
            time.sleep(min(BACKOFF_CAP, wait) * (0.75 + 0.5 * random.random()))

        r, neterr = None, None
        for attempt in range(RETRIES):
            try:
                r = requests.post(API_URL, json=payload, headers=headers, timeout=180)
            except (requests.exceptions.ConnectionError,
                    requests.exceptions.Timeout,
                    requests.exceptions.ChunkedEncodingError) as e:
                r, neterr = None, e
                if attempt < RETRIES - 1:
                    _sleep(attempt)
                    continue
                break
            neterr = None
            if _transient(r) and attempt < RETRIES - 1:
                _sleep(attempt, r)
                continue
            break
        if r is None and neterr is not None:
            raise RuntimeError(
                f"{API_URL} -> transport failure after {RETRIES} attempts for model "
                f"{MODELS[self.model_key]} (tag={tag}): {type(neterr).__name__}: {neterr}"
            ) from neterr
        # Some endpoints (openai/gpt-5-mini among them) REQUIRE reasoning and reject the
        # disable flag with HTTP 400. Latch that per session and retry, rather than failing
        # the cell -- this killed the first synthetic run at the very first judge call.
        if (r is not None and r.status_code == 400 and not self._reasoning_mandatory
                and "reasoning is mandatory" in r.text.lower()):
            self._reasoning_mandatory = True
            return self.chat(text, images=images,
                             max_completion=max(max_completion, 512), tag=tag)
        if r is None or r.status_code != 200:
            body = (r.text[:400] if r is not None else "no response")
            # Include the payload SHAPE. A provider-side schema complaint ("role must be
            # tool") says nothing about which field is actually malformed, and without
            # these numbers the only way to find out is to bisect by hand.
            shape = {"n_msgs": len(payload["messages"]),
                     "roles": [m["role"] for m in payload["messages"]],
                     "content_types": [c["type"] for c in content],
                     "text_chars": len(text), "max_tokens": payload["max_tokens"],
                     "keys": sorted(payload)}
            raise RuntimeError(f"{API_URL} -> HTTP {getattr(r, 'status_code', '?')} "
                               f"for model {MODELS[self.model_key]} (tag={tag}): {body}"
                               f"\n  payload shape: {shape}")
        data = r.json()
        if "choices" not in data:
            # Survived every retry with a 200-wrapped provider error. Fail loudly with the
            # body: silently returning "" here would score as a wrong answer and enter the
            # tables as a measurement.
            raise RuntimeError(f"{API_URL} -> HTTP 200 without 'choices' for model "
                               f"{MODELS[self.model_key]} (tag={tag}): "
                               f"{json.dumps(data)[:400]}")
        usage = data.get("usage", {})
        used = usage.get("total_tokens") or (
            usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0))
        self.spent += int(used)
        # Per-channel ledger. App. D registers a prediction about the REALISED
        # (B_s, B_r, B_c) split; without this the router's water-filling is
        # unobservable and that prediction is untestable.
        self.by_channel[self.channel_of(tag)] += int(used)
        out = data["choices"][0]["message"]["content"] or ""
        det = (usage.get("completion_tokens_details") or {}) if isinstance(usage, dict) else {}
        if not out.strip() and (det.get("reasoning_tokens") or 0) > 0 and max_completion < 256:
            # Reasoning ate the whole allowance. Log it rather than returning "" upward,
            # where an empty router class or an empty judge score becomes a wrong result
            # that looks like a measurement.
            self.calls.append({"tag": tag + ":empty_retry", "tokens": 0,
                               "channel": self.channel_of(tag),
                               "reasoning_tokens": det.get("reasoning_tokens")})
            return self.chat(text, images=images, max_completion=256, tag=tag)
        self.calls.append({"tag": tag, "tokens": int(used),
                           "channel": self.channel_of(tag),
                           "est": est, "n_images": len(images or []),
                           "fingerprint": data.get("model", "")})
        if self.spent > self.budget:
            # Can still happen when the provider's own count exceeds our estimate.
            self.calls[-1]["overshoot"] = self.spent - self.budget
        return out

    # tag -> budget channel, so the trace can be checked against Table 1
    @staticmethod
    def channel_of(tag: str) -> str:
        if tag.startswith("router"):
            return "rho"
        if "retr" in tag:
            return "Br"
        if "state" in tag:
            return "Bs"
        return "Bc"

    def split(self) -> dict:
        """Realised fractions of the decision budget, per channel."""
        tot = sum(self.by_channel.values()) or 1
        return {k: round(v / tot, 3) for k, v in self.by_channel.items()}
