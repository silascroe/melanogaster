"""Design arithmetic only; no retinal neuron rule, recordings, or fitting."""
from pathlib import Path
import hashlib
import json
import os
import re

import numpy as np
from scipy.integrate import quad
from scipy.optimize import minimize_scalar
from scipy.special import erf, expit

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'outputs/research/lc10a-response-design-v1'
os.environ.setdefault('MPLCONFIGDIR', str(OUT/'mpl-cache'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

EXPECTED_SOURCE_HASHES = {
    'LICENSE': 'a2010f343487d3f7618affe54f789f5487602331c0a8d03f49e9a7c547cf0499',
    'sampleLC10Model_tethered.m': '304ab9f31c2739441a810e61bf40e14115bc3eb977c20d4ecded3414aea7c496',
    'temporalRF_LC10.m': 'a24f609650c4a4780140963dff4f5247be1d453b0a9af00e639d7bdf4097f373',
}
for name, expected in EXPECTED_SOURCE_HASHES.items():
    source = OUT/'sources'/name
    actual = hashlib.sha256(source.read_bytes()).hexdigest()
    if actual != expected:
        raise ValueError(f'Pinned author-source hash mismatch: {name}')
source_text = (OUT/'sources/temporalRF_LC10.m').read_text(encoding='utf-8')
for name, expected in {'kappa': .84962, 'sigma': 5.5273,
                       'alpha': -.1859, 'beta': 15.5884}.items():
    found = re.search(r'\b'+name+r'\s*=\s*([-+.0-9eE]+)\s*;', source_text)
    if found is None or float(found.group(1)) != expected:
        raise ValueError(f'Author coefficient does not match the design: {name}')


def shape(lag):
    return expit(5.5273*(0.84962-lag))*expit(15.5884*(lag-0.1859))


area, _ = quad(shape, 0, 3, epsabs=1e-13)
tail, _ = quad(shape, 3, np.inf, epsabs=1e-13)
mean = quad(lambda u: u*shape(u), 0, 3, epsabs=1e-13)[0]/area
peak = minimize_scalar(lambda u: -shape(u), bounds=(0,3), method='bounded',
                       options={'xatol':1e-12}).x
lags = np.linspace(0,3,10001)
legacy = np.exp(5.5273*(0.84962-lags))/(
    (np.exp(15.5884*(-lags+0.1859))+1)*
    (np.exp(5.5273*(0.84962-lags))+1))
equation_error = float(np.max(np.abs(legacy-shape(lags))))
assert equation_error < 1e-14

mass_checks = []
for dt in (.0015,.002):
    edges = np.arange(0,3+dt/2,dt)
    edges[-1] = 3.
    weights = np.array([quad(shape, a,b,epsabs=1e-13)[0]/area
                        for a,b in zip(edges[:-1],edges[1:])])
    assert abs(weights.sum()-1) < 1e-12 and np.all(weights>=0)
    # Integral of a held unit pulse from .300 to .600, evaluated at .900 s.
    # These endpoints align with both grids. It uses past bins n-1-m.
    n = round(.9/dt)
    f = ((np.arange(n)*dt >= .3-1e-12)&(np.arange(n)*dt < .6-1e-12)).astype(float)
    discrete = sum(weights[m]*f[n-1-m] for m in range(n))
    continuous = quad(shape, .3,.6,epsabs=1e-13)[0]/area
    assert abs(discrete-continuous)<1e-12
    mass_checks.append(dict(dt_s=dt,bins=len(weights),mass=float(weights.sum()),
                            held_input_quadrature_error=abs(discrete-continuous)))

# An infinite-panel, one-dimensional, centered static rectangle illustration.
# This is not the implemented 2D motion/vertical-pooling response or a size fit.
width = np.linspace(0,100,1001)
center = erf(width/(2*np.sqrt(2)*7.5))
surround = erf(width/(2*np.sqrt(2)*22.5))
dog = center-surround
dog_peak_width = np.sqrt(8*np.log(22.5/7.5)/(1/7.5**2-1/22.5**2))

fig,axes = plt.subplots(1,2,figsize=(11,4.3),layout='constrained')
axes[0].plot(lags,shape(lags)/area,label='Pinned author envelope, unit area')
axes[0].plot(lags,np.exp(-lags/.1)/.1,linestyle='--',label='100 ms exponential (illustration)')
axes[0].axvline(peak,color='gray',linewidth=.8)
axes[0].set(xlabel='Past input lag (s)',ylabel='Kernel density (1/s)',xlim=(0,2),ylim=(0,10.5),
            title=f'Envelope peak {peak:.3f} s; mean lag {mean:.3f} s')
axes[0].legend(fontsize=8)
axes[1].plot(width,center,label='Center mass, sigma 7.5 degrees')
axes[1].plot(width,surround,label='Surround mass, sigma 22.5 degrees')
axes[1].plot(width,dog,label='Center minus surround')
axes[1].set(xlabel='Centered rectangle width (degrees)',ylabel='Normalized mass',
            title='Synthetic 1D spatial construction, not measured tuning')
axes[1].legend(fontsize=8)
for ax in axes:ax.grid(alpha=.2)
fig.suptitle('LC10a response design: equation checks only; no neural response or fit run',fontsize=11)
figure = ROOT/'docs/evidence/lc10a_response_construction_v1.png'
fig.savefig(figure,dpi=150,metadata={'Software':'Fly Creature design construction checks'})
plt.close(fig)

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

report = dict(status='design arithmetic only; no neural candidate, recordings, or fitting',
              source_revision='d15afdfd21b93774cef963f5c92d511a9ea0d15e',
              source_sha256={p.name:sha(p) for p in sorted((OUT/'sources').iterdir())},
              kernel=dict(horizon_s=3,raw_area_s=area,raw_tail_area_s=tail,
                          omitted_total_area_fraction=tail/(area+tail),peak_lag_s=float(peak),
                          mean_lag_s=mean,raw_at_zero=float(shape(0.)),
                          stable_equation_max_error=equation_error,mass_checks=mass_checks),
              spatial_illustration=dict(scope='infinite-panel centered 1D static rectangle only',
                                        center_sigma_deg=7.5,surround_sigma_deg=22.5,
                                        difference_peak_width_deg=float(dog_peak_width),
                                        biological_parameter_fit=False),
              checker_sha256=sha(Path(__file__)),figure_sha256=sha(figure))
(OUT/'construction_checks.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n',encoding='utf-8')
print(json.dumps(report,indent=2,sort_keys=True))
