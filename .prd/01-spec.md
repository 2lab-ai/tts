---
title: 2lab-ai/tts — on-device speech + karaoke captions for any web page
type: spec
tags: [tts, supertonic, webgpu, karaoke, library]
---

# 01 — Spec (SSOT)

## Owner request (verbatim, 2026-10-14)
"여기서 작업한 내용을 이용하여 일반적인 사이트에서 이렇게 온디바이스 모델 추가하는 걸 라이브러리화해서 2lab-ai/tts으로 만들어줘 /
ts/js에서 임포트해서 쉽게 쓸수 있도록 / 화자는 cwon2를 f101로 변경해서 올려줘 / 목적은: 사이트에서 주어진 텍스트 뭉치를 자연스럽게
계속 음성으로 tts 출력하고 당연히 어느 부분 플레이중인지 받아서 화면에서도 실시간 자막(노래방 자막 처럼)표시할 수 있는 라이브러리 /
그래서 이 라이브러리 사용하면 몇줄 추가로 tts랑 노래방 자막 출력 기능을 만들수 있도록 해줘" — "디폴트로 supertonic-3 사용하는거고".

## Decisions
- **Repo and licensing** (owner, via trinity 3/3): the repo is public.
  - Code: MIT.
  - Voice `f101`: ships in `voices/` with `voices/f101.TERMS.md`. It is a Supertonic-3 style the owner trained from reference audio, not a real person.
  - Model weights: not in the repo. Fetched at runtime from Hugging Face `Supertone/supertonic-3` at a pinned revision, under BigScience Open RAIL-M. The README states the license split.
- **Distribution** (owner, via trinity 2:1 — fable preferred npm now): GitHub first.
  - `npm i github:2lab-ai/tts#vX.Y.Z` and `https://cdn.jsdelivr.net/gh/2lab-ai/tts@vX.Y.Z/src/index.js`.
  - package.json is npm-shaped (`name: @2lab-ai/tts`, `exports`, `types`, `files`), so an npm publish later is one step.
- **Default engine:** Supertonic-3 (owner). Default voice: `f101`. Default language: `ko` (owner's sites).
- **Derived defaults:**
  - Source is plain ESM JavaScript with a hand-written `index.d.ts`, so no build step is needed: a GitHub install and the jsdelivr GitHub CDN both work from the tagged source. Zero npm runtime dependencies.
  - onnxruntime-web 1.30.0 is loaded at runtime from jsdelivr (pinned); `runtimeUrl` overrides.
  - Model files come from Hugging Face at revision `724fb5abbf5502583fb520898d45929e62f02c0b`; `modelUrl` overrides. Every file is checked against a pinned sha256. The pins were verified when these files were first downloaded.

## Measured facts (2026-10-14)
- **ONNX interfaces:**
  - `duration_predictor(text_ids, style_dp, text_mask) → duration [batch]`: one duration per utterance, no per-token alignment.
  - `text_encoder(text_ids, style_ttl, text_mask) → text_emb`.
  - `vector_estimator(noisy_latent, text_emb, style_ttl, latent_mask, text_mask, current_step, total_step)`.
  - `vocoder(latent) → wav`.
- **Karaoke timing** (bench/timing). Takes: 8 neutral sentences (6 Korean, 2 English), voice f101, 16 steps, speed 1.0. Ground truth = torchaudio MMS_FA forced alignment (uroman romanization), 91 word starts, excluding the first word of each sentence.

  | estimator | bias | median \|error\| | p90 | ≤100 ms | ≤200 ms |
  |---|---|---|---|---|---|
  | uniform per character | −18 ms | 182 ms | 464 ms | 30% | 53% |
  | syllable-weighted between speech onset and offset | +42 ms | 98 ms | 245 ms | 52% | 87% |
  | + punctuation anchors on pauses ≥120 ms below −45 dB (chosen) | +14 ms | 82 ms | 255 ms | 60% | 85% |

  - Duration-predictor prefixes are worse: the predictor adds end-of-utterance length to every prefix.
  - Whisper word timestamps are unusable as ground truth: whisper-turbo put every first word at 0.00 s although speech starts 0.34–0.61 s later, and it pulls word starts into preceding pauses.
  - The tuning set is small. E1 re-measures on held-out sentences with the in-browser engine's PCM.
- **CORS:**
  - huggingface.co `resolve/<rev>/…` sends `access-control-allow-origin`, then 302/307 to `cdn.hf.co` (ACAO `*`).
  - jsdelivr sends ACAO `*` and CORP cross-origin.
  - So redirects must be allowed (an earlier same-origin deployment used `redirect: 'error'`); integrity = the sha256 pin.
- **Speed** (an earlier deployment of the same engine):
  - WebGPU on Apple M-series: 64 steps, 19.9 s of audio in 2.4 s.
  - CPU wasm, 16 threads, cross-origin isolated: 8 steps, 18.1 s in 5.4 s.
  - CPU, 1 thread: 8 steps, 14.1 s in 13.0 s.
- **Workers:** `new Worker(url)` requires a same-origin script. A library imported from a CDN must start its worker from a blob module that imports the cross-origin worker module (CORS-enabled).

## Public API (contract)
```ts
import { createTTS } from '@2lab-ai/tts';
const tts = createTTS({ voice: 'f101', lang: 'ko' });   // all options optional
tts.on('status', (s) => …);   // { state: 'idle'|'loading'|'ready'|'error', pct?, device?: 'gpu'|'cpu', reason? }
const p = tts.speak(text, { captions: el });            // call from a user gesture (audio unlock)
p.on('word', (w) => …);       // { index, text, start, end, sentence }  (seconds on the playback clock)
p.on('sentence', (s) => …);   // { index, text, start, end, words }
p.on('progress', (x) => …);   // per animation frame: { sentence, word, char, time }
p.pause(); p.resume(); p.stop(); await p.done;           // done resolves on natural end or stop
tts.read(element);            // speaks element.textContent and highlights the words in place (karaoke)
tts.preload();                // fetch + init the model without speaking
tts.dispose();
```
- **Options:**
  - `voice`: `'f101'`, a Supertonic preset name (`F1`..`F5`, `M1`..`M5`), a URL, or a `{style_ttl, style_dp}` object.
  - `lang` (default `'ko'`).
  - `speed` (default 1.0).
  - `quality`: `{ gpuSteps: 32, cpuSteps: 8 }`, adapted at runtime with a floor and a cap.
  - `lead` (seconds, default 0): shift captions earlier.
  - `device`: `'auto'|'gpu'|'cpu'`.
  - `modelUrl`, `runtimeUrl`, `workerUrl`.
  - `cache` (Cache Storage on/off, default on).
  - `seed` (default random).
- **Karaoke UI** (`captions` option or `karaoke(el, playback)`):
  - Captions mode shows the current sentence in a box. Each character fills left to right as it is spoken: `--tts-fill` 0..1 on the current word span, `tts-done` on spoken words.
  - In-place mode (`read(element)`) wraps the element's text-node words in spans and restores the DOM on stop.
  - Styling: `karaoke.css` (link it) or default rules injected through a constructable stylesheet. No inline style attributes, so it works under `style-src 'self'`.
- **Device order:** WebGPU adapter → `gpu`. No adapter, or GPU sessions fail → `cpu` (wasm; threads `min(8, cores)` when `crossOriginIsolated`, else 1). No WebAssembly → `error` with a reason.

## Vertical trace (one `speak(text)`)
- **§0 Client:** `speak(text, {captions})` → a playback object, status events, caption DOM.
- **§1 Text:** split into sentences (`. ! ? 。` and line breaks) → chunks of at most `maxChunk` characters (ko 120, others 300; supertonic 1.3.1 rule) → per chunk `preprocess(lang)` + `textToIds(indexer)`. Words = whitespace-separated tokens of the ORIGINAL text, each mapped to character offsets of the chunk.
- **§2 Engine (worker):**
  - `load` fetches `tts.json`, `unicode_indexer.json` and the 4 onnx files (Cache Storage first; else fetch with redirects allowed, sha256 = pin, cache.put) and the voice JSON, then creates sessions per device order.
  - `synth(chunk, steps, seed)` → Float32 PCM 44.1 kHz.
  - The worker also computes the chunk's timing on a 10 ms RMS envelope (dB relative to the chunk peak):
    - speech onset and offset at −35 dB;
    - pauses: runs ≥ 120 ms below −45 dB;
    - each `, . ! ?` followed by more text is anchored to the unused pause nearest (within 0.8 s) its syllable-weighted estimate: the punctuation sits at the pause start, the next word at the pause end;
    - syllable-weighted interpolation between anchors (Hangul syllable 1, digit 0.6, Latin letter 0.35, space 0.15, other 0.3, `, . ! ?` 0) gives per-character start times.
  - Returns `{ pcm, sampleRate, charTimes, synthMs, steps, device }`.
- **§3 Player (main thread):**
  - AudioContext. Chunk i+1 is synthesized while chunk i plays (look-ahead 1, or 2 on GPU).
  - Gapless scheduling: chunk start = previous end + 0.3 s (supertonic join silence).
  - Word and sentence times = chunk start + charTimes − lead.
  - A rAF loop emits `progress`, plus `word` / `sentence` on boundaries.
  - Steps adapt per chunk: synth > 0.5 × audio → halve (floor gpu 16 / cpu 5); < 0.15 × audio → double (cap gpu 64 / cpu 8).
  - A buffer underrun waits (status `buffering`) instead of skipping.
- **§4 Side effects:** Cache Storage `2lab-tts-supertonic3-<rev>` (~380 MB); entries for other revisions are deleted. No network writes.
- **§5 Errors:** model fetch / sha256 mismatch / session failure → status `error` with a reason; `p.done` rejects. Unsupported characters are reported once and removed from the speech (still displayed). Errors are never silent.
- **§6 Output:** audio plus word/sentence/progress events plus the karaoke DOM.

## Contract tests (start RED)
- **T1 text:** `preprocess` + `textToIds` + chunking match supertonic 1.3.1 for a ko/en/ja fixture set. The fixture comes from the Python package; the generator lives in `bench/`.
- **T2 timing:** on synthetic PCM (tone bursts and silences at known times) the estimator puts the punctuation anchors inside the silences and is monotonic; the lead is applied.
- **T3 player:** with a fake engine, events are ordered, words are monotonic, pause/resume/stop work, `done` resolves and rejects correctly, and look-ahead is bounded.
- **T4 karaoke:** captions and in-place DOM: fill classes per progress; in-place mode restores the original DOM byte for byte on stop.
- **T5 types:** `examples/typed.ts` compiles with `tsc --noEmit` against `index.d.ts`.
- **E1 browser (Playwright, local Chrome):**
  - WebGPU: speak held-out Korean and English paragraphs (not the bench sentences); words monotonic; captions fill. The engine's PCM and word times are exported via a test hook and scored with bench/timing forced alignment: median ≤ 120 ms, ≥ 80% within 200 ms.
  - CPU: no adapter (in-worker override); same checks.
  - Cross-origin: the library is imported from a second origin, so the blob worker shim is used.
- **E2 demo (GitHub Pages):** the public demo page loads the model from Hugging Face and speaks with karaoke captions. This is the "general site" receipt.

## File map
- `src/index.js` (createTTS), `src/engine.js` (worker client + cross-origin shim), `src/worker.js` (sessions, synth, timing), `src/text.js`, `src/timing.js`, `src/player.js`, `src/karaoke.js`, `src/pins.js`.
- `index.d.ts`, `karaoke.css`, `voices/f101.json`, `voices/f101.TERMS.md`.
- `examples/` (plain HTML plus `typed.ts`), `test/*.test.js` (node --test), `e2e/`, `bench/timing/`.
- `README.md` (Korean and English quick start, license split), `LICENSE` (MIT), `.github/workflows/{ci,pages}.yml`.

## Internal module contracts (so units can be built in parallel)
- **`src/text.js`**
  - `segment(text, { lang, maxChunk }) → Chunk[]`, where `Chunk = { text, start, end, words: Word[] }` and `Word = { text, start, end }`. All offsets index into the ORIGINAL input, so captions show the original text.
  - `preprocess(text, lang)` and `textToIds(text, lang, indexer)`, ported from supertonic 1.3.1.
- **`src/timing.js`:** `charTimes(pcm: Float32Array, sampleRate, text) → Float32Array` (start second of every character of `text`, monotonic), with the algorithm above. Pure, runs in the worker.
- **`src/engine.js`:** `createEngine(opts) → Engine`.
  - `load() → Promise<{ device: 'gpu'|'cpu' }>`; emits `progress { loaded, total, pct }`.
  - `synth({ text, lang }, { steps, seed }) → Promise<{ pcm, sampleRate, charTimes, synthMs, steps, device }>`.
  - `cancel()`, `dispose()`, `on(event, fn)`.
  - It owns the worker (same-origin URL, or a blob shim when the module URL is cross-origin).
- **`src/worker.js`:** the message protocol is internal to engine.js/worker.js.
- **`src/player.js`:** `createPlayback(engine, chunks, opts) → Playback`, the public playback object. Scheduling, events, steps adaptation.
- **`src/karaoke.js`:** `karaoke(target, playback, { mode: 'captions'|'inplace' }) → { destroy() }`.
- **`src/index.js`:** `createTTS(opts) → TTS`; wires the pieces together; `read(el)` = segment(el.textContent) + karaoke inplace.

