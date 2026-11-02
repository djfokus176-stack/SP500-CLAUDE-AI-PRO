# -*- coding: utf-8 -*-
"""
LABORATORIUM STRATEGII (lab.py)
===============================
Odpowiada na jedno pytanie: "czy ta reguła ma przewagę, czy to przypadek?"

Jak to działa:
  * wspólny symulator z kosztami: wejście na OPEN następnej świecy po ASK/BID, wyjście po BID/ASK (pełny spread),
    SL/TP w wielokrotnościach ATR, w jednej świecy SL ma pierwszeństwo, luka przez SL = wyjście po OPEN,
    limit czasu = wyjście na OPEN następnej świecy;
  * walk-forward (zakotwiczony): parametry wybierane TYLKO na danych sprzed testu, wynik liczony TYLKO na danych "z przyszłości";
  * test istotności: wynik porównywany z losowymi wejściami o tej samej gęstości i tych samych zasadach wyjścia
    (rozkład zerowy wyznaczony Monte Carlo);
  * korekta na wielokrotne testowanie (Bonferroni) — im więcej reguł sprawdzasz, tym łatwiej o fałszywy "sukces".

Werdykt "ISTOTNA PRZEWAGA" wymaga jednocześnie: >= 30 transakcji poza próbą, dodatniej oczekiwanej wartości NETTO
oraz p po korekcie < 0.05. To warunek konieczny do dalszych testów forward (PAPER/DEMO), a nie gwarancja zysku.
"""
import numpy as np
import pandas as pd

try:  # przyspieszenie (opcjonalne): bez numba działa, tylko wolniej
    from numba import njit
    HAVE_NUMBA = True
except Exception:  # pragma: no cover
    HAVE_NUMBA = False

    def njit(*args, **kwargs):
        if args and callable(args[0]):
            return args[0]
        return lambda f: f


# ==========================================================
# SYMULATOR TRANSAKCJI (zgodny z modelem wykonania silnika v7)
# ==========================================================
@njit
def _sim_core(o, h, l, c, sig, atr, sl_m, tp_m, max_hold, hs, pnl_out, idx_out):
    n = len(o)
    k = 0
    i = 1
    while i < n - 2:
        d = sig[i]
        a = atr[i]
        if d == 0 or not (a > 0.0):
            i += 1
            continue
        entry = o[i + 1] + d * hs                 # LONG po ASK, SHORT po BID
        sl_p = -sl_m * a
        tp_p = tp_m * a
        j = i + 1
        pnl = 0.0
        done = False
        exit_bar = j
        while j < n:
            if d == 1:
                op = o[j] - hs - entry
                adv = l[j] - hs - entry
                fav = h[j] - hs - entry
            else:
                op = entry - (o[j] + hs)
                adv = entry - (h[j] + hs)
                fav = entry - (l[j] + hs)
            if op <= sl_p:                         # luka przez SL
                pnl = op
                done = True
                exit_bar = j
                break
            if adv <= sl_p:                        # SL przed TP w tej samej świecy
                pnl = sl_p
                done = True
                exit_bar = j
                break
            if fav >= tp_p:
                pnl = tp_p
                done = True
                exit_bar = j
                break
            if j - i >= max_hold:                  # limit czasu: wyjście na OPEN następnej świecy
                if j + 1 < n:
                    ex = o[j + 1] - hs if d == 1 else o[j + 1] + hs
                    pnl = d * (ex - entry)
                    done = True
                    exit_bar = j + 1
                break
            j += 1
        if not done:
            break
        pnl_out[k] = pnl
        idx_out[k] = i
        k += 1
        i = exit_bar + 1
    return k


def simulate(o, h, l, c, sig, atr, sl_m, tp_m, max_hold, spread):
    """Zwraca (pnl, indeksy_sygnałów) dla serii (tablice numpy float64 / int64)."""
    n = len(o)
    pnl = np.zeros(n // 2 + 2)
    idx = np.zeros(n // 2 + 2, dtype=np.int64)
    k = _sim_core(o, h, l, c, sig, atr, float(sl_m), float(tp_m), int(max_hold), float(spread) / 2.0, pnl, idx)
    return pnl[:k].copy(), idx[:k].copy()


# ==========================================================
# WSKAŹNIKI I SYGNAŁY (decyzja na ZAMKNIĘCIU świecy i, wejście na OPEN i+1)
# ==========================================================
def atr_wilder(h, l, c, n=14):
    prev_c = c.shift()
    tr = pd.concat([h - l, (h - prev_c).abs(), (l - prev_c).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1.0 / n, adjust=False).mean()


def rsi_wilder(c, n=14):
    d = c.diff()
    ag = d.clip(lower=0).ewm(alpha=1.0 / n, adjust=False).mean()
    al = (-d).clip(lower=0).ewm(alpha=1.0 / n, adjust=False).mean()
    rs = ag / al.where(al != 0)
    return (100 - 100 / (1 + rs)).where(al != 0, np.where(ag > 0, 100.0, 50.0)).fillna(50.0)


def _dir(up, dn):
    return np.where(up.to_numpy(), 1, np.where(dn.to_numpy(), -1, 0)).astype(np.int64)


def sig_ema_cross(df, fast, slow):
    diff = df["Close"].ewm(span=fast, adjust=False).mean() - df["Close"].ewm(span=slow, adjust=False).mean()
    return _dir((diff > 0) & (diff.shift() <= 0), (diff < 0) & (diff.shift() >= 0))


def sig_donchian(df, n):
    hh, ll = df["High"].rolling(n).max().shift(1), df["Low"].rolling(n).min().shift(1)
    c = df["Close"]
    return _dir((c > hh) & (c.shift() <= hh.shift()), (c < ll) & (c.shift() >= ll.shift()))


def sig_rsi_rev(df, n, lo, hi):
    r = rsi_wilder(df["Close"], n)
    return _dir((r < lo) & (r.shift() >= lo), (r > hi) & (r.shift() <= hi))


def sig_boll_rev(df, n, k):
    c = df["Close"]
    m, s = c.rolling(n).mean(), c.rolling(n).std()
    lo, hi = m - k * s, m + k * s
    return _dir((c < lo) & (c.shift() >= lo.shift()), (c > hi) & (c.shift() <= hi.shift()))


def sig_macd_cross(df, f, s, sg):
    macd = df["Close"].ewm(span=f, adjust=False).mean() - df["Close"].ewm(span=s, adjust=False).mean()
    diff = macd - macd.ewm(span=sg, adjust=False).mean()
    return _dir((diff > 0) & (diff.shift() <= 0), (diff < 0) & (diff.shift() >= 0))


def sig_pullback(df, fast, slow):
    c, lo, hi = df["Close"], df["Low"], df["High"]
    ef, es = c.ewm(span=fast, adjust=False).mean(), c.ewm(span=slow, adjust=False).mean()
    up = (ef > es) & (es > es.shift(3)) & (lo <= ef) & (c > ef) & (c > df["Open"])
    dn = (ef < es) & (es < es.shift(3)) & (hi >= ef) & (c < ef) & (c < df["Open"])
    return _dir(up, dn)


# nazwa -> (funkcja, siatka parametrów). Siatki są celowo małe: im więcej kombinacji, tym łatwiej o przeuczenie.
STRATEGIES = {
    "Przecięcie EMA (trend)": (sig_ema_cross, [{"fast": 5, "slow": 20}, {"fast": 9, "slow": 21}, {"fast": 12, "slow": 48}]),
    "Wybicie Donchian (trend)": (sig_donchian, [{"n": 20}, {"n": 40}, {"n": 80}]),
    "RSI — powrót do średniej": (sig_rsi_rev, [{"n": 14, "lo": 30, "hi": 70}, {"n": 7, "lo": 20, "hi": 80}, {"n": 14, "lo": 25, "hi": 75}]),
    "Bollinger — powrót do średniej": (sig_boll_rev, [{"n": 20, "k": 2.0}, {"n": 20, "k": 2.5}, {"n": 50, "k": 2.0}]),
    "MACD — przecięcie": (sig_macd_cross, [{"f": 12, "s": 26, "sg": 9}, {"f": 8, "s": 17, "sg": 9}, {"f": 24, "s": 52, "sg": 18}]),
    "Pullback w trendzie": (sig_pullback, [{"fast": 9, "slow": 50}, {"fast": 21, "slow": 100}, {"fast": 12, "slow": 60}]),
}
# (SL w ATR, TP w ATR). Na świecach 1-min spread bywa porównywalny z 1 ATR, więc zbyt ciasne stopy z założenia przegrywają z kosztami.
EXIT_GRID = [(1.5, 3.0), (3.0, 3.0), (3.0, 6.0), (6.0, 12.0)]


# ==========================================================
# WALK-FORWARD + TEST ISTOTNOŚCI
# ==========================================================
def _expectancy(p):
    return float(np.mean(p)) if len(p) else float("-inf")


def _prep(df):
    d = df[["Open", "High", "Low", "Close"]].astype(float).copy()
    d = d[~d.index.duplicated(keep="last")].sort_index().dropna()
    atr = atr_wilder(d["High"], d["Low"], d["Close"]).to_numpy()
    return d, atr


def data_quality(d, bar_seconds=None):
    """Ostrzeżenia o danych, które mogą dać FAŁSZYWE przewagi (zduplikowane/nieregularne świece, zerowa zmienność)."""
    warns = []
    if len(d) < 3:
        return ["Za mało świec."]
    dt = d.index.to_series().diff().dropna().dt.total_seconds()
    med = float(bar_seconds) if bar_seconds else float(dt.quantile(0.75))   # typowy interwał (odporny na luki weekendowe)
    if med > 0:
        near_dup = float((dt < 0.5 * med).mean())
        if near_dup > 0.02:
            warns.append(f"{near_dup * 100:.0f}% świec jest oddalonych o <½ typowego interwału — to wygląda na zduplikowane lub "
                         f"przemieszane dane. Takie dane dają fałszywe 'przewagi'. Wyniki NIE są wiarygodne.")
    flat = float(((d["High"] - d["Low"]) == 0).mean())
    if flat > 0.30:
        warns.append(f"{flat * 100:.0f}% świec ma zerowy zakres (High=Low) — dane mogą być niepełne (np. tylko ceny zamknięcia).")
    ret = d["Close"].pct_change().dropna()
    if len(ret) > 200 and abs(float(ret.autocorr(1))) > 0.3:
        warns.append(f"Autokorelacja zwrotów = {ret.autocorr(1):+.2f} — nienaturalnie wysoka dla rynku; sprawdź, czy dane nie są sztucznie wygładzone/powtórzone.")
    return warns


def _arrays(d):
    return (d["Open"].to_numpy(), d["High"].to_numpy(), d["Low"].to_numpy(), d["Close"].to_numpy())


def _eval(arrs, sig, atr, lo, hi, sl_m, tp_m, max_hold, spread):
    o, h, l, c = (a[lo:hi] for a in arrs)
    return simulate(o, h, l, c, np.ascontiguousarray(sig[lo:hi]), np.ascontiguousarray(atr[lo:hi]), sl_m, tp_m, max_hold, spread)[0]


def run_lab(df, spread, max_hold=40, n_folds=3, n_null=200, min_is_trades=30, seed=7, strategies=None, progress=None, bar_seconds=None):
    """
    df: OHLC z indeksem czasu. spread: pełny spread w jednostkach ceny (np. 0.8 pkt dla US500).
    Zwraca (tabela_wyników, szczegóły) — szczegóły zawierają transakcje poza próbą i wybrane parametry.
    """
    strategies = strategies or STRATEGIES
    d, atr = _prep(df)
    arrs = _arrays(d)
    n = len(d)
    quality = data_quality(d, bar_seconds)
    if n < 600:
        raise ValueError("Za mało danych (potrzeba co najmniej ~600 świec).")
    first_is = int(n * 0.4)                       # pierwsze 40% danych tylko do doboru parametrów
    edges = np.linspace(first_is, n, n_folds + 1).astype(int)
    rng = np.random.default_rng(seed)
    m_tests = len(strategies)
    rows, details = [], {}
    bh = float(d["Close"].iloc[-1] - d["Close"].iloc[first_is])

    for si, (name, (fn, grid)) in enumerate(strategies.items()):
        if progress:
            progress(si / m_tests, f"Testuję: {name}")
        sigs = [fn(d, **p) for p in grid]
        oos_all, folds_info = [], []
        for f in range(n_folds):
            is_hi, lo, hi = edges[f], edges[f], edges[f + 1]
            best, best_exp, best_n = None, -np.inf, 0
            for gi, sg in enumerate(sigs):
                for sl_m, tp_m in EXIT_GRID:
                    p = _eval(arrs, sg, atr, 0, is_hi, sl_m, tp_m, max_hold, spread)
                    if len(p) >= min_is_trades and _expectancy(p) > best_exp:
                        best, best_exp, best_n = (gi, sl_m, tp_m), _expectancy(p), len(p)
            if best is None:                       # za mało transakcji w próbie uczącej
                folds_info.append(None)
                continue
            gi, sl_m, tp_m = best
            p_oos = _eval(arrs, sigs[gi], atr, lo, hi, sl_m, tp_m, max_hold, spread)
            oos_all.append(p_oos)
            dens = float(np.count_nonzero(sigs[gi][lo:hi])) / max(hi - lo, 1)
            folds_info.append({"params": grid[gi], "sl": sl_m, "tp": tp_m, "lo": lo, "hi": hi, "dens": dens,
                               "is_exp": round(best_exp, 3), "is_n": best_n, "oos_n": len(p_oos),
                               "oos_exp": round(_expectancy(p_oos), 3) if len(p_oos) else None})
        used = [fi for fi in folds_info if fi is not None]
        oos = np.concatenate(oos_all) if oos_all else np.array([])
        if len(oos) == 0 or not used:
            rows.append({"Strategia": name, "Transakcji OOS": 0, "Skuteczność %": np.nan, "Oczekiwana wartość (pkt)": np.nan, "Wartość / spread": np.nan,
                         "95% przedział": "-", "Profit factor": np.nan, "Suma (pkt)": 0.0, "p (losowe wejścia)": np.nan,
                         "p po korekcie": np.nan, "Werdykt": "⏳ za mało transakcji"})
            details[name] = {"oos": oos, "folds": folds_info}
            continue

        # rozkład zerowy: losowe wejścia o tej samej gęstości, te same SL/TP, te same odcinki poza próbą
        null_exp = np.empty(n_null)
        for r in range(n_null):
            pooled = []
            for fi in used:
                lo, hi = fi["lo"], fi["hi"]
                m = hi - lo
                rs = np.where(rng.random(m) < fi["dens"], np.where(rng.random(m) < 0.5, 1, -1), 0).astype(np.int64)
                o, h, l, c = (a[lo:hi] for a in arrs)
                pooled.append(simulate(o, h, l, c, rs, atr[lo:hi], fi["sl"], fi["tp"], max_hold, spread)[0])
            pooled = np.concatenate(pooled)
            null_exp[r] = np.mean(pooled) if len(pooled) else -np.inf
        obs = float(np.mean(oos))
        p_raw = (1 + int(np.sum(null_exp >= obs))) / (n_null + 1)
        p_adj = min(1.0, p_raw * m_tests)
        sd = float(np.std(oos, ddof=1)) if len(oos) > 1 else 0.0
        half = 1.96 * sd / np.sqrt(len(oos)) if len(oos) > 1 else 0.0
        gw, gl = float(oos[oos > 0].sum()), float(-oos[oos <= 0].sum())
        pf = gw / gl if gl > 0 else (np.inf if gw > 0 else 0.0)
        if len(oos) >= 30 and obs > 0 and p_adj < 0.05:
            verdict = "✅ ISTOTNA PRZEWAGA (kandydat do testu forward)"
        elif obs > 0 and p_raw < 0.05:
            verdict = "🟡 słaba — po korekcie na wielokrotne testy nieistotna"
        elif obs > 0:
            verdict = "⚪ dodatnia, ale nieodróżnialna od losowej"
        else:
            verdict = "❌ ujemna po kosztach"
        rows.append({"Strategia": name, "Transakcji OOS": int(len(oos)), "Skuteczność %": round(100 * float(np.mean(oos > 0)), 1),
                     "Oczekiwana wartość (pkt)": float(f"{obs:.4g}"), "Wartość / spread": round(obs / spread, 2) if spread > 0 else np.nan,
                     "95% przedział": f"[{obs - half:+.4g}; {obs + half:+.4g}]",
                     "Profit factor": round(pf, 2) if np.isfinite(pf) else np.inf, "Suma (pkt)": round(float(oos.sum()), 1),
                     "p (losowe wejścia)": round(p_raw, 3), "p po korekcie": round(p_adj, 3), "Werdykt": verdict})
        details[name] = {"oos": oos, "folds": folds_info, "null": null_exp}
    if progress:
        progress(1.0, "Gotowe")
    table = pd.DataFrame(rows).sort_values("Oczekiwana wartość (pkt)", ascending=False, na_position="last").reset_index(drop=True)
    details["_meta"] = {"n_bars": n, "oos_bars": n - first_is, "buy_hold_oos_pkt": round(bh, 2), "spread": spread,
                        "max_hold": max_hold, "n_folds": n_folds, "n_null": n_null, "numba": HAVE_NUMBA, "ostrzezenia": quality,
                        "avg_atr": round(float(np.nanmean(atr)), 4)}
    return table, details


def load_ohlc_csv(file_or_path):
    """Wczytuje CSV z kolumnami czasu i Open/High/Low/Close (nazwy rozpoznawane bez względu na wielkość liter)."""
    raw = pd.read_csv(file_or_path)
    cols = {c.lower().strip(): c for c in raw.columns}
    need = {}
    for key, aliases in {"Open": ["open", "o"], "High": ["high", "h"], "Low": ["low", "l"], "Close": ["close", "c", "adj close"]}.items():
        hit = next((cols[a] for a in aliases if a in cols), None)
        if hit is None:
            raise ValueError(f"Brak kolumny {key} w pliku (znalezione: {list(raw.columns)})")
        need[key] = hit
    tcol = next((cols[a] for a in ["time", "datetime", "date", "timestamp", "gmt time", "local time"] if a in cols), raw.columns[0])
    idx = pd.to_datetime(raw[tcol], errors="coerce", utc=True)
    out = pd.DataFrame({k: pd.to_numeric(raw[v], errors="coerce") for k, v in need.items()})
    out.index = idx
    return out[~out.index.isna()].dropna().sort_index()
