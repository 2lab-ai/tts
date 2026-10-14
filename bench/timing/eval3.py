import sys, json, re, numpy as np
exec(open(sys.argv[3]).read().split("errs = {")[0])
cache, faj = sys.argv[1:3]; FA = json.load(open(faj))
def score(min_ms, thr, lead):
    errs = []
    for ti, fa in enumerate(FA):
        a = np.load(f'{cache}/{ti}.npz', allow_pickle=True)['audio']; text = fa['text']
        db = env(a); gaps, on, off = pauses(db, thr, min_ms)
        W = np.cumsum([0] + [wt(c) for c in text])
        def interp(anc, ci):
            for (c0, t0), (c1, t1) in zip(anc, anc[1:]):
                if c0 <= ci <= c1: return t0 + (t1 - t0) * ((W[ci] - W[c0]) / max(1e-9, W[c1] - W[c0]))
            return anc[-1][1]
        base = [(0, on), (len(text), off)]; anc = [(0, on)]; used = set()
        for m in re.finditer(r'[,.!?](?=\s+\S)', text):
            p = m.end(); e = interp(base, p)
            cand = [(abs((g0 + g1) / 2 - e), g) for g, (g0, g1) in enumerate(gaps) if g not in used]
            if cand:
                d, g = min(cand)
                if d < 0.8:
                    used.add(g); nxt = p + re.search(r'\S', text[p:]).start(); anc += [(p, gaps[g][0]), (nxt, gaps[g][1])]
        anc.append((len(text), off)); anc.sort()
        for i, cs in enumerate([m.start() for m in re.finditer(r'\S+', text)]):
            if i: errs.append(interp(anc, cs) - lead - fa['start'][i])
    e = np.array(errs); a = np.abs(e)
    return f'bias={e.mean()*1000:+.0f} med={np.median(a)*1000:.0f} p90={np.percentile(a,90)*1000:.0f} w100={np.mean(a<=0.1)*100:.0f}% w200={np.mean(a<=0.2)*100:.0f}%'
for mm in (120, 200, 300):
    for thr in (-35, -45):
        print(f'snap min={mm}ms thr={thr}dB:', score(mm, thr, 0.0))
print('best + lead 0.04:', score(200, -45, 0.04))
