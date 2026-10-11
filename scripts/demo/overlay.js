// Injected into every page of the demo recording: bottom-left captions, arrows that
// point at an element only when one is needed, a visible cursor, and full-screen cards.
(() => {
  const css = `
    #demo-cap { position: fixed; left: 28px; bottom: 28px; max-width: 600px; z-index: 2147483000;
      background: rgba(14,18,28,.92); color: #fff; padding: 14px 18px 15px; border-radius: 12px;
      font: 500 21px/1.38 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      box-shadow: 0 8px 30px rgba(0,0,0,.25); opacity: 0; transform: translateY(8px);
      transition: opacity .35s, transform .35s; pointer-events: none; }
    #demo-cap.on { opacity: 1; transform: none; }
    #demo-cap .tag { display: block; font-size: 14px; font-weight: 700; letter-spacing: .06em;
      text-transform: uppercase; color: #9ec5ff; margin-bottom: 4px; }
    #demo-svg { position: fixed; inset: 0; width: 100vw; height: 100vh; z-index: 2147482999;
      pointer-events: none; }
    #demo-svg path.arrow { fill: none; stroke: #ffb020; stroke-width: 5; stroke-linecap: round; }
    #demo-svg rect.ring { fill: rgba(255,176,32,.10); stroke: #ffb020; stroke-width: 4; }
    #demo-cursor { position: fixed; z-index: 2147483001; width: 22px; height: 22px; margin: -11px 0 0 -11px;
      border-radius: 50%; background: rgba(59,91,219,.35); border: 2px solid #3b5bdb;
      pointer-events: none; transition: transform .12s; left: -50px; top: -50px; }
    #demo-cursor.down { transform: scale(.7); background: rgba(59,91,219,.7); }
    #demo-card { position: fixed; inset: 0; z-index: 2147483002; display: flex; flex-direction: column;
      align-items: center; justify-content: center; text-align: center; gap: 18px;
      background: radial-gradient(ellipse at 50% 40%, #1d2a4a, #0b0f19 70%); color: #fff;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      opacity: 0; transition: opacity .5s; pointer-events: none; }
    #demo-card.on { opacity: 1; }
    #demo-card h1 { font-size: 64px; margin: 0; letter-spacing: -.01em; }
    #demo-card h2 { font-size: 30px; margin: 0; font-weight: 500; color: #c9d6ee; }
    #demo-card p { font-size: 22px; margin: 0; color: #9fb0cc; max-width: 1100px; line-height: 1.5; }
    #demo-card .att { margin-top: 26px; font-size: 24px; color: #fff; }
  `;
  const ensure = () => {
    if (document.getElementById("demo-style")) return;
    const style = document.createElement("style");
    style.id = "demo-style";
    style.textContent = css;
    document.head.appendChild(style);
    const cap = document.createElement("div");
    cap.id = "demo-cap";
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.id = "demo-svg";
    const cur = document.createElement("div");
    cur.id = "demo-cursor";
    const card = document.createElement("div");
    card.id = "demo-card";
    document.body.append(cap, svg, cur, card);
    addEventListener("mousemove", (e) => { cur.style.left = e.clientX + "px"; cur.style.top = e.clientY + "px"; }, true);
    addEventListener("mousedown", () => cur.classList.add("down"), true);
    addEventListener("mouseup", () => cur.classList.remove("down"), true);
  };

  window.__demo = {
    caption(text, tag) {
      ensure();
      const cap = document.getElementById("demo-cap");
      cap.innerHTML = (tag ? `<span class="tag">${tag}</span>` : "") + text;
      cap.classList.add("on");
    },
    hideCaption() {
      ensure();
      document.getElementById("demo-cap").classList.remove("on");
    },
    // Arrow from the caption box to the element (or the first line containing `text`).
    point(selector, text) {
      ensure();
      let el = document.querySelector(selector);
      if (text) el = [...document.querySelectorAll(selector)].find((n) => n.textContent.includes(text));
      if (!el) throw new Error("demo.point: nothing matches " + selector + " " + (text || ""));
      let box = el.getBoundingClientRect();
      if (text) {
        // Ring the line's visible text, not its leading spaces or the full row.
        const range = document.createRange();
        range.selectNodeContents(el);
        const lead = el.textContent.length - el.textContent.trimStart().length;
        if (lead && el.firstChild) range.setStart(el.firstChild, lead);
        box = range.getBoundingClientRect();
      }
      const cap = document.getElementById("demo-cap").getBoundingClientRect();
      const svg = document.getElementById("demo-svg");
      const pad = 6;
      const tx = box.left - pad, ty = box.top - pad, th = box.height + 2 * pad;
      const tw = Math.min(box.width, innerWidth - box.left - 20) + 2 * pad;
      const above = ty + th < cap.top;
      const ex = Math.max(tx + 14, Math.min(tx + tw / 2, tx + 140)), ey = above ? ty + th + 4 : ty - 4;
      const sx = Math.max(cap.left + 30, Math.min(ex + 60, cap.right - 30)), sy = cap.top - 6;
      const cx = (sx + ex) / 2 + 60, cy = above ? (sy + ey) / 2 : Math.min(sy, ey) - 40;
      const ang = Math.atan2(ey - cy, ex - cx), L = 18;
      const head = `M ${ex - L * Math.cos(ang - .45)} ${ey - L * Math.sin(ang - .45)} L ${ex} ${ey} L ${ex - L * Math.cos(ang + .45)} ${ey - L * Math.sin(ang + .45)}`;
      svg.innerHTML = `<rect class="ring" x="${tx}" y="${ty}" width="${tw}" height="${th}" rx="8"/>
        <path class="arrow" id="demo-shaft" d="M ${sx} ${sy} Q ${cx} ${cy} ${ex} ${ey}"/>
        <path class="arrow" d="${head}"/>`;
      const shaft = document.getElementById("demo-shaft");
      const len = shaft.getTotalLength();
      shaft.style.strokeDasharray = len;
      shaft.style.strokeDashoffset = len;
      shaft.getBoundingClientRect();
      shaft.style.transition = "stroke-dashoffset .5s ease-out";
      shaft.style.strokeDashoffset = 0;
    },
    unpoint() { ensure(); document.getElementById("demo-svg").innerHTML = ""; },
    card(html) {
      ensure();
      const card = document.getElementById("demo-card");
      card.innerHTML = html;
      card.classList.add("on");
    },
    hideCard() { ensure(); document.getElementById("demo-card").classList.remove("on"); },
  };
  if (document.readyState === "loading") addEventListener("DOMContentLoaded", ensure);
  else ensure();
})();
