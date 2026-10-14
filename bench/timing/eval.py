# eval.py <cache_dir> <fa.json> — estimator error vs forced-alignment word starts
import sys, json, re, numpy as np
cache, faj = sys.argv[1:3]; FA = json.load(open(faj)); SR = 44100
def wt(ch):
    if re.match(r'[가-힣]', ch): return 1.0
    if ch.isdigit(): return 0.6
    if re.match(r'[A-Za-z]', ch): return 0.35
    if ch == ' ': return 0.15
    if ch in ',.!?': return 0.0
    return 0.3
def env(a):
    f = int(SR * 0.01); n = len(a) // f
    rms = np.sqrt(np.mean(a[: n * f].reshape(n, f) ** 2, axis=1) + 1e-12)
    return 20 * np.log10(rms / (rms.max() + 1e-9))
def pauses(db, thr=-35, min_ms=90):
    q = db < thr; out = []; k = 0; n = len(db)
    while k < n:
        if q[k]:
            j = k
            while j < n and q[j]: j += 1
            if (j - k) * 10 >= min_ms and k > 0 and j < n: out.append((k * 0.01, j * 0.01))
            k = j
        else: k += 1
    loud = np.where(~q)[0]
    return out, loud[0] * 0.01, (loud[-1] + 1) * 0.01
def estimate(text, a, snap=True):
    db = env(a); gaps, on, off = pauses(db)
    W = np.cumsum([0] + [wt(c) for c in text])
    def interp(anc, ci):
        for (c0, t0), (c1, t1) in zip(anc, anc[1:]):
            if c0 <= ci <= c1: return t0 + (t1 - t0) * ((W[ci] - W[c0]) / max(1e-9, W[c1] - W[c0]))
        return anc[-1][1]
    base = [(0, on), (len(text), off)]
    if not snap: return lambda ci: interp(base, ci)
    punct = [m.end() for m in re.finditer(r'[,.!?](?=\s+\S)', text)]
    anc = [(0, on)]; used = set()
    for p in punct:
        e = interp(base, p)
        cand = [(abs((g0 + g1) / 2 - e), g) for g, (g0, g1) in enumerate(gaps) if g not in used]
        if cand:
            d, g = min(cand)
            if d < 1.2:
                used.add(g); nxt = p + re.search(r'\S', text[p:]).start()
                anc += [(p, gaps[g][0]), (nxt, gaps[g][1])]
    anc.append((len(text), off)); anc.sort()
    return lambda ci: interp(anc, ci)
errs = {'U': [], 'S_on': [], 'S_snap': []}
for ti, fa in enumerate(FA):
    a = np.load(f'{cache}/{ti}.npz', allow_pickle=True)['audio']; T = len(a) / SR; text = fa['text']
    offs = [m.start() for m in re.finditer(r'\S+', text)]
    nonspace = [i for i, c in enumerate(text) if not c.isspace()]
    e_on, e_snap = estimate(text, a, False), estimate(text, a, True)
    for i, cs in enumerate(offs):
        if i == 0: continue
        truth = fa['start'][i]
        errs['U'].append(T * sum(1 for k in nonspace if k < cs) / len(nonspace) - truth)
        errs['S_on'].append(e_on(cs) - truth); errs['S_snap'].append(e_snap(cs) - truth)
for k, e in errs.items():
    e = np.array(e); a = np.abs(e)
    print(f'{k}: n={len(e)} bias={e.mean()*1000:+.0f}ms median|e|={np.median(a)*1000:.0f}ms p90={np.percentile(a,90)*1000:.0f}ms within100={np.mean(a<=0.1)*100:.0f}% within200={np.mean(a<=0.2)*100:.0f}%')
