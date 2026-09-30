import React, { useEffect, useRef, useState } from 'react';
import {
  Satellite,
  Cpu,
  Layers,
  Crosshair,
  Sparkles,
  Rocket,
  Play,
  ChevronRight,
  ShieldAlert,
} from 'lucide-react';
import { apiUrl } from './apiConfig.js';

// SIH landing page: polished entry leading into the existing exploration
// app. All functionality/routes stay intact -- this only gates the map
// behind onLaunch / onDemo. Stats are real backend totals with graceful
// fallback (never fabricated). All motion is CSS/SVG/canvas-rAF,
// lightweight, and disabled under prefers-reduced-motion.
const FEATURES = [
  {
    icon: Satellite,
    title: 'Satellite Intelligence',
    text: 'Real Sentinel-2 Level-2A scenes (10 m multispectral + SWIR) clipped to surveyed areas of interest.',
  },
  {
    icon: Cpu,
    title: 'AI/ML Engine',
    text: 'Spectral indices feed an Isolation Forest anomaly screen blended into a transparent mineralization score.',
  },
  {
    icon: Layers,
    title: 'GIS Analysis',
    text: 'Pixel overlays, candidate markers, drawn AOIs and reference corridors layered on live basemaps.',
  },
  {
    icon: Crosshair,
    title: 'Candidate Detection',
    text: 'DBSCAN clusters anomalous pixels into ranked exploration zones with auditable rank scores.',
  },
  {
    icon: Sparkles,
    title: 'Explainable AI',
    text: 'Every rank decomposes into score-point contributions — judges see exactly why a zone matters.',
  },
];

const STEPS = [
  { n: '01', title: 'Pick an area', text: 'Choose a corridor, search a place, or draw your own AOI on the map.' },
  { n: '02', title: 'Scan the pixels', text: 'Multispectral features become anomaly and mineralization percentiles.' },
  { n: '03', title: 'Rank the zones', text: 'Clusters become a shortlist ordered by transparent rank_score.' },
  { n: '04', title: 'Explain & export', text: 'Open the score breakdown, then download the PDF field report.' },
];

// Process captions shown in the orbital visual -- real pipeline stage
// names only, no measurements.
const PIPELINE_CAPTIONS = [
  'SATELLITE DATA',
  'SPECTRAL ANALYSIS',
  'AI ANOMALY DETECTION',
  'SPATIAL CLUSTERING',
  'EXPLORATION TARGETS',
];

function useReducedMotion() {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia?.('(prefers-reduced-motion: reduce)');
    if (!mq) return;
    setReduced(mq.matches);
    const onChange = (e) => setReduced(e.matches);
    mq.addEventListener?.('change', onChange);
    return () => mq.removeEventListener?.('change', onChange);
  }, []);
  return reduced;
}

// Lightweight drifting data particles (single canvas, capped count,
// gold/white, slow). Static frame when reduced motion is preferred.
function ParticleField({ reduced }) {
  const ref = useRef(null);
  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const rand = (a, b) => a + Math.random() * (b - a);
    // Three depth layers: [count, radius, alpha, speed] — far/small/slow,
    // mid, near/bright/faster for parallax space travel.
    const LAYERS = [
      { n: 55, rMin: 0.4, rMax: 0.9, aMin: 0.22, aMax: 0.45, v: 0.35 },
      { n: 30, rMin: 0.8, rMax: 1.4, aMin: 0.35, aMax: 0.65, v: 0.7 },
      { n: 15, rMin: 1.3, rMax: 2.1, aMin: 0.55, aMax: 0.95, v: 1.15 },
    ];
    let raf = 0;
    let w = 0;
    let h = 0;
    const resize = () => {
      const r = canvas.parentElement.getBoundingClientRect();
      w = canvas.width = Math.max(1, Math.floor(r.width));
      h = canvas.height = Math.max(1, Math.floor(r.height));
    };
    resize();
    window.addEventListener('resize', resize);
    const stars = [];
    for (const L of LAYERS) {
      for (let i = 0; i < L.n; i++) {
        const roll = Math.random();
        stars.push({
          x: Math.random(), y: Math.random(),
          r: rand(L.rMin, L.rMax), a: rand(L.aMin, L.aMax),
          ph: rand(0, 6.28), tw: rand(0.4, 1.1),
          vx: rand(0.5, 1.2) * L.v, vy: rand(-0.85, -0.3) * L.v,
          // Mostly cool white, some soft pink, few gold (foreground identity).
          tint: roll < 0.18 ? 'pink' : roll < 0.3 ? 'gold' : 'white',
        });
      }
    }
    const meteors = [];
    const impacts = [];
    const sparks = [];
    let nextMeteor = 0;
    const draw = (t) => {
      ctx.clearRect(0, 0, w, h);
      for (const s of stars) {
        const tw = 0.72 + 0.28 * Math.sin(t * 0.001 * s.tw + s.ph);
        const x = (((s.x % 1) + 1) % 1) * w;
        const y = (((s.y % 1) + 1) % 1) * h;
        ctx.beginPath();
        ctx.arc(x, y, s.r, 0, Math.PI * 2);
        const alpha = (s.a * tw).toFixed(3);
        ctx.fillStyle = s.tint === 'pink'
          ? `rgba(249, 168, 212, ${alpha})`
          : s.tint === 'gold'
            ? `rgba(251, 191, 36, ${alpha})`
            : `rgba(226, 232, 240, ${alpha})`;
        ctx.fill();
      }
      for (const m of meteors) {
        // Life envelope: fade-in -> bright pass -> fade-out.
        const k = Math.min(1, Math.max(0, (t - m.born) / m.life));
        const env = (k < 0.12 ? k / 0.12 : 1) * (k > 0.55 ? 1 - (k - 0.55) / 0.45 : 1);
        const tail = m.cyan ? '34, 211, 238' : m.magenta ? '232, 121, 249' : '249, 168, 212';
        const grad = ctx.createLinearGradient(m.x, m.y, m.x - m.dx * m.len, m.y - m.dy * m.len);
        grad.addColorStop(0, `rgba(255, 255, 255, ${(0.95 * env).toFixed(3)})`);
        grad.addColorStop(0.2, `rgba(${tail}, ${(0.6 * env).toFixed(3)})`);
        grad.addColorStop(1, `rgba(${tail}, 0)`);
        ctx.strokeStyle = grad;
        ctx.lineWidth = m.big ? 2 : 1.2;
        ctx.beginPath();
        ctx.moveTo(m.x, m.y);
        ctx.lineTo(m.x - m.dx * m.len, m.y - m.dy * m.len);
        ctx.stroke();
        // Soft bloom around the head (stronger for foreground meteors).
        const haloR = m.big ? 14 : 8;
        const halo = ctx.createRadialGradient(m.x, m.y, 0, m.x, m.y, haloR);
        halo.addColorStop(0, `rgba(255, 255, 255, ${(0.85 * env).toFixed(3)})`);
        halo.addColorStop(0.35, `rgba(${tail}, ${(0.4 * env).toFixed(3)})`);
        halo.addColorStop(1, `rgba(${tail}, 0)`);
        ctx.fillStyle = halo;
        ctx.beginPath();
        ctx.arc(m.x, m.y, haloR, 0, Math.PI * 2);
        ctx.fill();
      }
      // Distant impact glows: expanding faint ring, quick fade.
      for (const im of impacts) {
        const k = (t - im.born) / im.life;
        const r = 4 + k * 24;
        ctx.strokeStyle = `rgba(249, 168, 212, ${(0.35 * (1 - k)).toFixed(3)})`;
        ctx.lineWidth = 1.2;
        ctx.beginPath();
        ctx.arc(im.x, im.y, r, 0, Math.PI * 2);
        ctx.stroke();
        ctx.fillStyle = `rgba(249, 168, 212, ${(0.12 * (1 - k)).toFixed(3)})`;
        ctx.beginPath();
        ctx.arc(im.x, im.y, r * 0.6, 0, Math.PI * 2);
        ctx.fill();
      }
      for (const s of sparks) {
        const k = 1 - (t - s.born) / s.life;
        ctx.fillStyle = `rgba(252, 211, 77, ${(0.7 * Math.max(0, k)).toFixed(3)})`;
        ctx.beginPath();
        ctx.arc(s.x, s.y, 1.1, 0, Math.PI * 2);
        ctx.fill();
      }
    };
    if (reduced) {
      draw(0);
      return () => window.removeEventListener('resize', resize);
    }
    const onVis = () => {
      if (!document.hidden) raf = requestAnimationFrame((tt) => step(tt));
    };
    document.addEventListener('visibilitychange', onVis);
    const step = (t) => {
      if (document.hidden) {
        raf = requestAnimationFrame(step);
        return;
      }
      for (const s of stars) {
        s.x += ((s.vx * 0.016) / 100) * 6;
        s.y += ((s.vy * 0.016) / 100) * 6;
      }
      // Shooting stars: exactly 1 at a time (rare overlap of 2), with a
      // guaranteed respawn 0.5-2 s after the previous one finishes, so the
      // effect is always observable within seconds of page load.
      const canSpawn = meteors.length === 0
        || (meteors.length === 1 && meteors[0].big && Math.random() < 0.25);
      if (t > nextMeteor && canSpawn) {
        // Alternate upper-left -> lower-right and upper-right -> lower-left,
        // with varied angles, speeds, sizes and tints.
        const dir = Math.random() < 0.5 ? 1 : -1;
        const big = Math.random() < 0.18;
        const ang = rand(0.5, 0.72);
        const tintRoll = Math.random();
        const span = Math.max(w, h);
        meteors.push({
          x: dir === 1 ? rand(-0.05, 0.4) * w : rand(0.6, 1.05) * w,
          y: rand(-0.05, 0.25) * h,
          dx: Math.cos(ang) * dir, dy: Math.sin(ang),
          sp: big ? rand(8, 10) : rand(9, 13),
          // Tail 15-30% of viewport span (longer for foreground meteors).
          len: big ? span * rand(0.22, 0.3) : span * rand(0.15, 0.24),
          born: t, life: rand(1000, 1500),
          big, cyan: tintRoll > 0.82, magenta: tintRoll <= 0.82 && tintRoll > 0.5,
        });
        nextMeteor = t + rand(500, 2000);
      }
      for (let i = meteors.length - 1; i >= 0; i--) {
        const m = meteors[i];
        if (t - m.born >= m.life) {
          // Distant impact whisper for big meteors ending low on screen.
          if (m.big && m.y > h * 0.5 && impacts.length === 0 && sparks.length < 4) {
            impacts.push({ x: m.x, y: m.y, born: t, life: 650 });
            for (let j = 0; j < 8; j++) {
              const a = rand(0, Math.PI * 2);
              const sp = rand(0.4, 1.4);
              sparks.push({
                x: m.x, y: m.y, born: t, life: rand(300, 500),
                vx: Math.cos(a) * sp, vy: Math.sin(a) * sp,
              });
            }
          }
          meteors.splice(i, 1);
          // Guarantee the next meteor follows shortly after the sky empties.
          if (meteors.length === 0) nextMeteor = t + rand(500, 2000);
          continue;
        }
        m.sp *= 1.012;
        m.x += m.dx * m.sp;
        m.y += m.dy * m.sp;
        m.len *= 0.995;
      }
      for (let i = impacts.length - 1; i >= 0; i--) {
        if (t - impacts[i].born >= impacts[i].life) impacts.splice(i, 1);
      }
      for (let i = sparks.length - 1; i >= 0; i--) {
        const s = sparks[i];
        if (t - s.born >= s.life) {
          sparks.splice(i, 1);
          continue;
        }
        s.x += s.vx;
        s.y += s.vy;
      }
      draw(t);
      raf = requestAnimationFrame(step);
    };
    nextMeteor = performance.now() + 400;
    raf = requestAnimationFrame(step);
    return () => {
      cancelAnimationFrame(raf);
      document.removeEventListener('visibilitychange', onVis);
      window.removeEventListener('resize', resize);
    };
  }, [reduced]);
  return <canvas ref={ref} className="absolute inset-0 h-full w-full" aria-hidden="true" />;
}

// Animated pipeline caption rotator (fades through real stage names).
function PipelineCaption({ reduced }) {
  const [idx, setIdx] = useState(0);
  useEffect(() => {
    if (reduced) return;
    const t = setInterval(() => setIdx((i) => (i + 1) % PIPELINE_CAPTIONS.length), 2600);
    return () => clearInterval(t);
  }, [reduced]);
  return (
    <p className="font-mono text-[10px] tracking-[0.35em] text-amber-300/90 uppercase" aria-live="polite">
      <span key={idx} className="caption-swap">◈ {PIPELINE_CAPTIONS[idx]}</span>
    </p>
  );
}

// Count-up statistic (eases 0 → value; instant when reduced motion).
function CountUp({ value, reduced }) {
  const [shown, setShown] = useState(0);
  useEffect(() => {
    if (value == null || reduced) {
      setShown(value ?? 0);
      return;
    }
    let raf = 0;
    const start = performance.now();
    const dur = 1200;
    const step = (t) => {
      const k = Math.min(1, (t - start) / dur);
      setShown(Math.round(value * (1 - Math.pow(1 - k, 3))));
      if (k < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [value, reduced]);
  if (value == null) return <b className="text-amber-300">—</b>;
  return <b className="text-amber-300">{shown.toLocaleString()}</b>;
}

// Orbital satellite visual: earth disc + two orbit rings + one satellite
// marker circling (CSS rotation) + radar sweep scope beside it.
function OrbitalVisual({ reduced }) {
  return (
    <div className="relative mx-auto mt-10 h-56 w-56 sm:h-64 sm:w-64" aria-hidden="true">
      {/* orbit rings (brighter gold trail + soft glow) */}
      <svg viewBox="0 0 200 200" className="absolute inset-0 h-full w-full orbit-glow">
        <ellipse cx="100" cy="100" rx="92" ry="58" fill="none" stroke="rgba(251,191,36,0.6)" strokeWidth="1.25" transform="rotate(-18 100 100)" />
        <ellipse cx="100" cy="100" rx="70" ry="86" fill="none" stroke="rgba(34,211,238,0.3)" strokeWidth="1" transform="rotate(24 100 100)" />
        {/* data-flow packets: satellite data streaming down-orbit toward
            the earth disc (decorative SMIL, omitted under reduced motion) */}
        {!reduced && (
          <g fill="#fcd34d">
            <circle r="2" opacity="0.9">
              <animateMotion dur="7s" repeatCount="indefinite" path="M 192,100 m -92,0 a 92,58 -18 1,0 184,0 a 92,58 -18 1,0 -184,0" />
            </circle>
            <circle r="1.5" opacity="0.7">
              <animateMotion dur="7s" begin="-2.3s" repeatCount="indefinite" path="M 192,100 m -92,0 a 92,58 -18 1,0 184,0 a 92,58 -18 1,0 -184,0" />
            </circle>
            <circle r="1.5" opacity="0.7">
              <animateMotion dur="7s" begin="-4.6s" repeatCount="indefinite" path="M 192,100 m -92,0 a 92,58 -18 1,0 184,0 a 92,58 -18 1,0 -184,0" />
            </circle>
          </g>
        )}
        {/* earth disc + soft glow halo */}
        <circle cx="100" cy="100" r="42" fill="url(#earthhalo)" />
        <circle cx="100" cy="100" r="34" fill="url(#earthg)" stroke="rgba(251,191,36,0.65)" strokeWidth="1.25" />
        <ellipse cx="100" cy="100" rx="34" ry="12" fill="none" stroke="rgba(255,255,255,0.25)" strokeWidth="0.75" />
        <ellipse cx="100" cy="100" rx="34" ry="24" fill="none" stroke="rgba(255,255,255,0.18)" strokeWidth="0.75" />
        <line x1="100" y1="66" x2="100" y2="134" stroke="rgba(255,255,255,0.18)" strokeWidth="0.75" />
        <defs>
          <radialGradient id="earthg" cx="38%" cy="32%" r="80%">
            <stop offset="0%" stopColor="#1e3a5f" />
            <stop offset="70%" stopColor="#0b1c33" />
            <stop offset="100%" stopColor="#060d1a" />
          </radialGradient>
          <radialGradient id="earthhalo" cx="50%" cy="50%" r="50%">
            <stop offset="70%" stopColor="#fbbf24" stopOpacity="0.14" />
            <stop offset="100%" stopColor="#fbbf24" stopOpacity="0" />
          </radialGradient>
        </defs>
      </svg>
      {/* scanning arc ring around earth (slow counter-rotation) */}
      <svg viewBox="0 0 200 200" className={`absolute inset-0 h-full w-full ${reduced ? '' : 'orbit-spin-rev'}`} aria-hidden="true">
        <circle cx="100" cy="100" r="46" fill="none" stroke="rgba(251,191,36,0.5)" strokeWidth="1.5" strokeDasharray="26 14 8 14" strokeLinecap="round" />
      </svg>
      {/* satellite on orbit (rotates around centre) */}
      <div className={`absolute inset-0 ${reduced ? '' : 'orbit-spin'}`}>
        <svg viewBox="0 0 200 200" className="h-full w-full">
          <g transform="rotate(-18 100 100)">
            {/* scanning beam: satellite -> earth edge (pulsing gold gradient) */}
            {!reduced && (
              <polygon points="186,68 192,74 134,91 130,87" fill="url(#beamg)" className="beam-pulse" />
            )}
            {/* live connection line satellite -> earth */}
            <line x1="189" y1="71" x2="133" y2="90" stroke="rgba(252,211,77,0.65)" strokeWidth="1" strokeDasharray="4 3" className={reduced ? '' : 'dash-flow'} />
            {/* glowing satellite body */}
            <circle cx="189" cy="71" r="7" fill="#fbbf24" opacity="0.22" />
            <rect x="184" y="68" width="10" height="6" rx="1" fill="#fde68a" />
            <rect x="180" y="69.5" width="4" height="3" fill="#b45309" />
            <rect x="194" y="69.5" width="4" height="3" fill="#b45309" />
            <circle cx="189" cy="71" r="1.4" fill="#fffbeb" />
          </g>
          <defs>
            <linearGradient id="beamg" x1="189" y1="71" x2="131" y2="89" gradientUnits="userSpaceOnUse">
              <stop offset="0%" stopColor="#fbbf24" stopOpacity="0.55" />
              <stop offset="100%" stopColor="#fbbf24" stopOpacity="0" />
            </linearGradient>
          </defs>
        </svg>
      </div>
      {/* radar sweep scope */}
      <div className="absolute -bottom-2 -right-2 h-20 w-20 sm:h-24 sm:w-24">
        <div className="absolute inset-0 rounded-full border border-amber-400/40 bg-black/50" />
        <div className="absolute inset-2 rounded-full border border-amber-400/25" />
        <div className="absolute inset-4 rounded-full border border-amber-400/20" />
        <div className={`absolute inset-0 rounded-full ${reduced ? '' : 'radar-sweep'}`} />
        <div className="absolute left-1/2 top-1/2 h-1 w-1 -translate-x-1/2 -translate-y-1/2 rounded-full bg-amber-300" />
        <div className="absolute left-[30%] top-[38%] h-1 w-1 rounded-full bg-emerald-400/90" />
        <div className="absolute left-[64%] top-[62%] h-1 w-1 rounded-full bg-emerald-400/70" />
      </div>
    </div>
  );
}

export default function Landing({ onLaunch, onDemo }) {
  const [stats, setStats] = useState(null);
  const [backendUp, setBackendUp] = useState(null);
  const reduced = useReducedMotion();

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [t, c] = await Promise.all([
          fetch(apiUrl('/api/candidates?dataset=t45que&limit=1')).then((r) => r.json()),
          fetch(apiUrl('/api/candidates?dataset=chennai&limit=1')).then((r) => r.json()),
        ]);
        if (!cancelled) {
          setStats({ t45que: t?.total ?? null, chennai: c?.total ?? null });
          setBackendUp(true);
        }
      } catch {
        if (!cancelled) setBackendUp(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const total = stats ? (stats.t45que ?? 0) + (stats.chennai ?? 0) : null;

  return (
    <div className="absolute inset-0 z-50 overflow-y-auto bg-slate-950 text-white landing-root">
      {/* ambient background + particles + faint topographic contours */}
      <div className="pointer-events-none fixed inset-0 landing-bg" aria-hidden="true" />
      <svg className="pointer-events-none fixed inset-0 h-full w-full opacity-[0.05]" aria-hidden="true" preserveAspectRatio="xMidYMid slice" viewBox="0 0 1200 800">
        <g fill="none" stroke="#fbbf24" strokeWidth="1">
          <path d="M120,620 C220,540 260,460 380,440 C500,420 560,480 700,450 C840,420 900,340 1020,330" />
          <path d="M80,670 C200,580 260,500 390,478 C520,456 590,520 730,488 C870,456 940,370 1070,360" />
          <path d="M40,720 C180,620 260,540 400,516 C540,492 620,560 760,526 C900,492 980,400 1120,390" />
          <path d="M0,770 C160,660 260,580 410,554 C560,528 650,600 790,564 C930,528 1020,430 1170,420" />
          <path d="M180,180 C280,140 360,150 460,120 C560,90 640,110 740,80" />
          <path d="M140,230 C260,185 350,195 460,162 C570,129 660,150 770,118" />
        </g>
      </svg>
      <div className="pointer-events-none fixed inset-0" aria-hidden="true">
        <ParticleField reduced={reduced} />
      </div>
      <div className="pointer-events-none fixed inset-0 overflow-hidden" aria-hidden="true">
        <div className="grid-scan absolute inset-x-0 top-0" />
      </div>

      <div className="relative mx-auto max-w-6xl px-5 sm:px-8 pb-16">
        {/* top bar */}
        <header className="flex items-center justify-between py-5 landing-rise">
          <div className="flex items-center gap-3">
            <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-amber-500/15 border border-amber-500/40 text-amber-400 font-mono font-black text-sm shadow-[0_0_25px_rgba(245,158,11,0.25)]">
              Mn25
            </div>
            <div>
              <p className="text-sm font-extrabold tracking-tight uppercase">
                GeoManganese AI <span className="text-amber-400 font-normal">//</span> Team RIZZLERS
              </p>
              <p className="text-[11px] font-mono text-slate-400">SIH26009 · Smart India Hackathon</p>
            </div>
          </div>
          <span className="hidden sm:inline-flex items-center gap-1.5 text-[10px] font-mono px-2.5 py-1 rounded-full border border-cyan-500/40 text-cyan-300 bg-cyan-500/10">
            <span className={`inline-block w-1.5 h-1.5 rounded-full ${backendUp === false ? 'bg-red-400' : backendUp ? 'bg-emerald-400 status-pulse' : 'bg-amber-400'}`} />
            {backendUp === false ? 'BACKEND OFFLINE' : backendUp ? 'SYSTEMS NOMINAL' : 'LINKING…'}
          </span>
        </header>

        {/* hero */}
        <section className="pt-8 sm:pt-12 pb-6 text-center landing-rise landing-d1">
          <p className="text-[11px] font-mono tracking-[0.3em] text-amber-400 uppercase mb-4">
            Multispectral Remote Sensing · Mineral Potential Targeting
          </p>
          <h1 className="text-4xl sm:text-6xl font-black tracking-tight leading-[1.05]">
            Find manganese ground
            <br />
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-amber-300 via-amber-400 to-cyan-300">
              from orbit first.
            </span>
          </h1>
          <p className="mx-auto mt-5 max-w-2xl text-sm sm:text-base text-slate-300 leading-relaxed">
            AI-assisted satellite intelligence for manganese exploration — screening
            Sentinel-2 imagery to a ranked shortlist of exploration targets, each one
            explained, mapped, and exportable.
          </p>

          <OrbitalVisual reduced={reduced} />
          <div className="mt-4 h-5">
            <PipelineCaption reduced={reduced} />
          </div>
          {!reduced && (
            <div className="mt-1" aria-hidden="true">
              <span className="cap-dots">
                <span className="cap-dot" />
                <span className="cap-dot" />
                <span className="cap-dot" />
              </span>
              <div className="cap-scan" />
            </div>
          )}

          {/* live stats */}
          <div className="mx-auto mt-5 flex flex-wrap items-center justify-center gap-2.5 font-mono text-[11px]">
            <span className="px-3 py-1.5 rounded-lg border border-slate-700/70 bg-slate-900/70">
              T45QUE <CountUp value={stats?.t45que ?? null} reduced={reduced} /> targets
            </span>
            <span className="px-3 py-1.5 rounded-lg border border-slate-700/70 bg-slate-900/70">
              CHENNAI <CountUp value={stats?.chennai ?? null} reduced={reduced} /> targets
            </span>
            <span className="px-3 py-1.5 rounded-lg border border-slate-700/70 bg-slate-900/70">
              RANKED <CountUp value={total} reduced={reduced} /> total
            </span>
            <span className="px-3 py-1.5 rounded-lg border border-slate-700/70 bg-slate-900/70 inline-flex items-center gap-1.5">
              GIS ENGINE
              <span className={`inline-block w-1.5 h-1.5 rounded-full ${backendUp === false ? 'bg-red-400' : backendUp ? 'bg-emerald-400 status-pulse' : 'bg-amber-400'}`} />
              <span className={backendUp === false ? 'text-red-300' : backendUp ? 'text-emerald-300' : 'text-amber-300'}>
                {backendUp === false ? 'OFFLINE' : backendUp ? 'ONLINE' : '…'}
              </span>
            </span>
          </div>

          {/* CTAs */}
          <div className="mt-8 flex flex-col sm:flex-row items-center justify-center gap-3">
            <button
              onClick={onLaunch}
              className="cta-launch group w-full sm:w-auto px-7 py-3.5 rounded-xl bg-amber-500 hover:bg-amber-400 text-slate-950 font-extrabold text-sm tracking-wide shadow-[0_0_35px_rgba(245,158,11,0.35)] transition-all hover:shadow-[0_0_50px_rgba(245,158,11,0.5)] active:scale-95 cursor-pointer flex items-center justify-center gap-2"
            >
              <Rocket className="w-4 h-4 transition-transform group-hover:-translate-y-0.5" />
              LAUNCH EXPLORATION
              <ChevronRight className="w-4 h-4 transition-transform group-hover:translate-x-0.5" />
            </button>
            <button
              onClick={onDemo}
              className="cta-demo group w-full sm:w-auto px-7 py-3.5 rounded-xl border border-purple-400/50 bg-purple-500/10 hover:bg-purple-500/20 text-white font-bold text-sm tracking-wide transition-all active:scale-95 cursor-pointer flex items-center justify-center gap-2"
            >
              <Play className="w-4 h-4 text-purple-300 transition-transform group-hover:scale-110" />
              GUIDED DEMO MODE
            </button>
          </div>
          <p className="mt-3 text-[11px] font-mono text-slate-500">
            No setup beyond the running frontend + backend · 8-step judge tour included
          </p>
        </section>

        {/* feature cards */}
        <section className="landing-rise landing-d2">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
            {FEATURES.map((f) => (
              <div
                key={f.title}
                className="landing-card rounded-2xl border border-slate-700/60 bg-slate-900/70 backdrop-blur p-4 flex flex-col gap-2.5 hover:border-amber-500/50 transition-colors"
              >
                <div className="w-9 h-9 rounded-lg bg-amber-500/10 border border-amber-500/30 flex items-center justify-center">
                  <f.icon className="w-4 h-4 text-amber-400" />
                </div>
                <h3 className="text-[13px] font-bold">{f.title}</h3>
                <p className="text-[11px] text-slate-400 leading-relaxed">{f.text}</p>
              </div>
            ))}
          </div>
        </section>

        {/* how it works */}
        <section className="mt-10 landing-rise landing-d3">
          <h2 className="text-center text-lg font-extrabold tracking-tight uppercase">
            From pixels <span className="text-amber-400">to drill targets</span>
          </h2>
          <div className="mt-5 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            {STEPS.map((s) => (
              <div
                key={s.n}
                className="rounded-2xl border border-slate-800 bg-slate-950/60 p-4"
              >
                <p className="font-mono text-amber-500/80 text-xs font-bold">{s.n}</p>
                <h3 className="mt-1 text-[13px] font-bold">{s.title}</h3>
                <p className="mt-1 text-[11px] text-slate-400 leading-relaxed">{s.text}</p>
              </div>
            ))}
          </div>
        </section>

        {/* honesty strip */}
        <section className="mt-8 landing-rise landing-d4">
          <div className="flex items-start gap-2.5 rounded-2xl border border-slate-700/60 bg-slate-900/60 px-4 py-3">
            <ShieldAlert className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
            <p className="text-[11px] text-slate-300 leading-relaxed">
              <b className="text-white">Honest AI:</b> every output is an <i>exploration
              target requiring ground validation</i> — never a confirmed deposit. Scores are
              spectral-outlier percentiles, and yield figures are illustrative reference
              scenarios, always labelled as such.
            </p>
          </div>
        </section>

        <footer className="mt-10 text-center">
          <button
            onClick={onLaunch}
            className="text-xs font-mono text-amber-400 hover:text-amber-300 transition-colors cursor-pointer"
          >
            Enter the platform →
          </button>
          <p className="mt-3 text-[10px] font-mono text-slate-600">
            GeoManganese AI · Team RIZZLERS · SIH26009
          </p>
        </footer>
      </div>
    </div>
  );
}
