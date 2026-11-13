// Side-profile aircraft illustrations, drawn as flat "poster" reductions.
// Every drawing faces right in a 480x150 box. Colours: cream body, a livery accent
// (tail, cheat line, engine ring) and a dark ink for windows, wings and shading.
const BODY = '#fbf4e6', INK = '#0f2236';
const n = v => Math.round(v * 10) / 10;
const poly = (pts, fill, extra = '') => `<polygon points="${pts.map(p => p.map(n).join(',')).join(' ')}" fill="${fill}" ${extra}/>`;
const ell = (cx, cy, rx, ry, fill, extra = '') => `<ellipse cx="${n(cx)}" cy="${n(cy)}" rx="${n(rx)}" ry="${n(ry)}" fill="${fill}" ${extra}/>`;

const AIRLINERS = {
  narrow:    {H: 38, xt: 34, finH: 48, tt: false, wing: [292, 72, 62, 18, 24], eng: [[-6, 17, 27, 11]], windows: true},
  regional:  {H: 32, xt: 56, finH: 44, tt: false, wing: [284, 58, 50, 14, 20], eng: [[-4, 14, 22, 9]], windows: true},
  wide_twin: {H: 52, xt: 30, finH: 56, tt: false, wing: [298, 98, 80, 22, 30], eng: [[-4, 22, 34, 15]], windows: true},
  wide_quad: {H: 54, xt: 30, finH: 58, tt: false, wing: [304, 100, 84, 22, 30], eng: [[8, 21, 30, 13], [-52, 28, 30, 13]], windows: true, hump: true},
  bizjet:    {H: 26, xt: 78, finH: 40, tt: true,  wing: [286, 60, 44, 12, 18], eng: [], rear: true, windows: false},
  turboprop: {H: 32, xt: 40, finH: 46, tt: true,  wing: [276, 52, 14, 8, 30], eng: [], prop: true, windows: true},
};

function airliner(p, c) {
  const y0 = 82, xn = 456, top = y0 - p.H / 2, bot = y0 + p.H / 2, xt = p.xt, H = p.H;
  let s = '';
  // Fin first so the fuselage overlaps its root.
  const fin = p.tt
    ? [[xt + 150, top + 3], [xt + 96, top - p.finH], [xt + 58, top - p.finH], [xt + 78, top + 3]]
    : [[xt + 150, top + 3], [xt + 84, top - p.finH], [xt + 46, top - p.finH], [xt + 72, top + 3]];
  s += poly(fin, c.accent);
  if (p.tt) {
    const ty = top - p.finH;
    s += poly([[xt + 112, ty + 2], [xt + 22, ty - 6], [xt + 22, ty - 1], [xt + 104, ty + 8]], INK, 'opacity=".55"');
  } else {
    s += poly([[xt + 134, y0 - H * .08], [xt + 30, y0 - H * .30], [xt + 24, y0 - H * .20], [xt + 100, y0 + H * .04]], INK, 'opacity=".5"');
  }
  // Fuselage
  s += `<path fill="${BODY}" d="M${xn - 70} ${n(top)} C${xn - 30} ${n(top)} ${xn} ${n(y0 - H * .25)} ${xn} ${n(y0 + H * .12)} C${xn} ${n(y0 + H * .36)} ${xn - 30} ${n(bot)} ${xn - 76} ${n(bot)} L${xt + 190} ${n(bot)} C${xt + 120} ${n(bot)} ${xt + 50} ${n(y0 + H * .18)} ${xt} ${n(y0 - H * .2)} C${xt + 30} ${n(top + H * .04)} ${xt + 90} ${n(top)} ${xt + 160} ${n(top)} Z"/>`;
  if (p.hump) s += ell(xn - 118, top + 3, 74, 12, BODY);
  if (p.rear) { // rear-fuselage engines on short pylons
    const ex = xt + 132, ey = top - 1;
    s += poly([[ex + 20, ey + 8], [ex - 26, ey + 8], [ex - 22, top + 6], [ex + 10, top + 4]], INK, 'opacity=".5"');
    s += ell(ex, ey, 36, 10, INK, 'opacity=".78"') + ell(ex + 32, ey, 5, 9, c.accent);
  }
  // Cheat line, windows, cockpit
  s += `<path d="M${xt + 190} ${n(y0 + H * .12)} L${xn - 96} ${n(y0 + H * .12)} L${xn - 40} ${n(y0 + H * .1)}" stroke="${c.accent}" stroke-width="${n(H * .13)}" fill="none" stroke-linecap="round"/>`;
  if (p.windows) {
    let w = '';
    for (let x = xn - 104; x > xt + 200; x -= 12.5) w += `<circle cx="${n(x)}" cy="${n(y0 - H * .17)}" r="2.1"/>`;
    s += `<g fill="${INK}" opacity=".42">${w}</g>`;
  }
  s += poly([[xn - 64, top + 5], [xn - 30, top + 7], [xn - 16, y0 - H * .06], [xn - 56, y0 - H * .1]], INK, 'opacity=".62"');
  // Wing (near side) then engines
  const [xw, ch, sw, dr, ct] = p.wing;
  const yr = p.prop ? top + 5 : y0 + H * .22;
  s += poly([[xw, yr], [xw - ch, yr], [xw - ch - sw + ct, yr + dr], [xw - sw, yr + dr]], INK, 'opacity=".5"');
  for (const [dx, dy, rx, ry] of p.eng) {
    const ex = xw + dx, ey = yr + dy;
    s += poly([[ex + 8, ey - ry], [ex - 24, ey - ry], [ex - 18, yr], [ex + 4, yr]], INK, 'opacity=".45"');
    s += ell(ex, ey, rx, ry, INK, 'opacity=".82"') + ell(ex + rx - 4, ey, ry * .42, ry * .86, c.accent) + ell(ex + rx - 2, ey, ry * .2, ry * .6, BODY);
  }
  if (p.prop) { // high-wing turboprop: nacelle and prop disc in front of the wing
    const ex = xw - 16, ey = top - 4;
    s += ell(ex, ey, 44, 11, INK, 'opacity=".85"') + ell(ex + 44, ey, 6, 9, c.accent);
    s += ell(ex + 52, ey, 3.5, 38, INK, 'opacity=".4"') + ell(ex + 52, ey, 1.6, 36, INK, 'opacity=".7"');
  }
  return s;
}

function lightPlane(c, low, twin) {
  let s = '';
  const wy = low ? 90 : 42;
  s += poly([[128, 66], [98, 28], [80, 28], [102, 68]], c.accent);                      // fin
  s += poly([[140, 70], [88, 60], [86, 67], [128, 77]], INK, 'opacity=".5"');           // stabiliser
  s += `<path fill="${BODY}" d="M396 74 C396 62 384 55 362 53 L304 49 L238 49 C200 51 152 61 106 65 L96 65 L98 77 L106 79 C160 86 212 93 252 94 L354 94 C384 94 396 86 396 74 Z"/>`;
  s += `<path d="M130 79 L352 87" stroke="${c.accent}" stroke-width="5" fill="none" stroke-linecap="round"/>`;
  s += poly([[336, 60], [286, 56], [278, 73], [342, 73]], INK, 'opacity=".5"');           // windows
  if (low) {
    s += poly([[336, 86], [214, 88], [206, 97], [330, 97]], INK, 'opacity=".55"');
  } else {
    s += poly([[356, 43], [206, 39], [198, 46], [352, 50]], INK, 'opacity=".6"');
    s += `<path d="M306 94 L286 48" stroke="${INK}" stroke-width="3" opacity=".6"/>`;
  }
  if (twin) {
    s += ell(318, 104, 34, 9, INK, 'opacity=".82"') + ell(350, 104, 6, 8, c.accent);
    s += ell(356, 104, 3, 34, INK, 'opacity=".4"');
  }
  // Fixed gear
  s += `<g stroke="${INK}" stroke-width="3.5" opacity=".75"><path d="M356 93 L358 112"/><path d="M272 95 L266 112"/></g>`;
  s += `<g fill="${INK}" opacity=".85"><circle cx="358" cy="116" r="7"/><circle cx="266" cy="116" r="8"/></g>`;
  s += ell(398, 74, 7, 9, c.accent);
  if (!twin) s += ell(401, 74, 3, 40, INK, 'opacity=".38"') + ell(401, 74, 1.4, 38, INK, 'opacity=".7"');
  return s;
}

function helicopter(c) {
  let s = '';
  s += poly([[212, 58], [66, 52], [60, 59], [212, 78]], BODY);                           // tail boom
  s += poly([[84, 54], [58, 28], [74, 28], [100, 54]], c.accent);                        // fin
  s += `<circle cx="64" cy="42" r="15" fill="none" stroke="${INK}" stroke-width="2" opacity=".5"/>`;
  s += `<path fill="${BODY}" d="M338 82 C338 58 308 46 274 46 L236 48 C212 50 202 66 202 82 C202 95 216 100 238 100 L324 100 C334 100 338 92 338 82 Z"/>`;
  s += `<path d="M206 88 L336 88" stroke="${c.accent}" stroke-width="6" fill="none"/>`;
  s += poly([[334, 78], [324, 58], [292, 51], [292, 80]], INK, 'opacity=".62"');
  s += poly([[284, 78], [284, 56], [246, 54], [240, 78]], INK, 'opacity=".4"');
  s += `<rect x="264" y="34" width="8" height="14" fill="${INK}" opacity=".8"/>`;
  s += ell(268, 33, 168, 3.2, INK, 'opacity=".55"');
  s += `<g stroke="${INK}" stroke-width="4" opacity=".8" fill="none" stroke-linecap="round"><path d="M214 118 L344 118"/><path d="M346 118 C352 118 354 114 352 110"/><path d="M242 100 L238 118"/><path d="M314 100 L318 118"/></g>`;
  return s;
}

export const CATEGORIES = ['narrow', 'regional', 'wide_twin', 'wide_quad', 'bizjet', 'turboprop', 'single_high', 'single_low', 'twin_prop', 'helicopter'];

export function art(category, colours = {}) {
  const c = {accent: colours.accent || '#d96b54'};
  let inner;
  if (AIRLINERS[category]) inner = airliner(AIRLINERS[category], c);
  else if (category === 'single_high') inner = lightPlane(c, false, false);
  else if (category === 'single_low') inner = lightPlane(c, true, false);
  else if (category === 'twin_prop') inner = lightPlane(c, true, true);
  else if (category === 'helicopter') inner = helicopter(c);
  else inner = airliner(AIRLINERS.narrow, c);
  return `<svg viewBox="0 0 480 150" xmlns="http://www.w3.org/2000/svg" role="img" focusable="false">${inner}</svg>`;
}
