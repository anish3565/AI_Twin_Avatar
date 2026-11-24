// Cartoon avatar for the Avatar mode.
// Free and client-side: no video, no GPU. The mouth opens and closes while
// the browser is reading a reply aloud, and blinks now and then.

function avatarMouthTarget(time, speaking) {
  if (!speaking) return 0;
  const wave = 0.5 + 0.5 * Math.sin(time / 90);
  const jitter = 0.55 + 0.45 * Math.abs(Math.sin(time / 37) * Math.cos(time / 113));
  return Math.min(1, wave * jitter + 0.12);
}

// isSpeaking: function returning true while a reply is being spoken.
function startAvatar(isSpeaking) {
  const mouth = document.getElementById("avatar-mouth");
  const head = document.getElementById("avatar-head");
  if (!mouth || !head) return;
  let open = 0;
  let last = performance.now();

  const frame = (now) => {
    const dt = Math.min(64, now - last);
    last = now;
    const target = avatarMouthTarget(now, isSpeaking());
    // Ease toward the target so the mouth does not snap between frames.
    open += (target - open) * Math.min(1, dt / 50);
    mouth.setAttribute("ry", (1.5 + open * 13).toFixed(2));
    mouth.setAttribute("rx", (12 + open * 3).toFixed(2));
    head.style.transform = isSpeaking() ? `translateY(${(-open * 1.5).toFixed(2)}px)` : "";
    requestAnimationFrame(frame);
  };
  requestAnimationFrame(frame);
}
