# fa.py <cache_dir> <texts.py> <out.json> — MMS forced alignment word starts for each cached take (uroman romanization)
import sys, json, re, numpy as np, torch, torchaudio, uroman as ur
cache, texts_py, out = sys.argv[1:4]
ns = {}; exec(open(texts_py).read(), ns); TEXTS = ns['TEXTS']
bundle = torchaudio.pipelines.MMS_FA
model = bundle.get_model(with_star=False); tok = bundle.get_tokenizer(); aligner = bundle.get_aligner()
U = ur.Uroman()
res = []
for ti, (lang, text) in enumerate(TEXTS):
    z = np.load(f'{cache}/{ti}.npz', allow_pickle=True); a = torch.tensor(z['audio']).unsqueeze(0)
    wav = torchaudio.functional.resample(a, 44100, bundle.sample_rate)
    words = re.findall(r'\S+', text)
    rom = []
    for w in words:
        r = U.romanize_string(w, lcode='kor' if lang == 'ko' else 'eng').lower()
        r = re.sub(r"[^a-z']", '', r) or 'a'
        rom.append(r)
    with torch.inference_mode():
        em, _ = model(wav)
    spans = aligner(em[0], tok(rom))
    ratio = wav.size(1) / em.size(1) / bundle.sample_rate
    starts = [s[0].start * ratio for s in spans]
    ends = [s[-1].end * ratio for s in spans]
    res.append({'lang': lang, 'text': text, 'words': words, 'start': starts, 'end': ends})
    print(ti, ' '.join(f'{w}@{t:.2f}' for w, t in zip(words, starts)), file=sys.stderr)
json.dump(res, open(out, 'w'), ensure_ascii=False, indent=1)
