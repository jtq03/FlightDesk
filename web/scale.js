// The desk screen is a small, close-up touch display. Everything is sized in rem, and on
// the kiosk (/display) one rem scales with the screen's short side (720px wide = 20px),
// so buttons and text stay finger-sized and proportional whichever way it is turned.
(function () {
  var kiosk = location.pathname === '/display';
  function fit() {
    document.documentElement.style.fontSize = kiosk ? Math.max(10, Math.min(innerWidth, innerHeight) / 36) + 'px' : '';
  }
  fit();
  addEventListener('DOMContentLoaded', fit, {once:true});
  addEventListener('load', fit, {once:true});
  requestAnimationFrame(fit);
  addEventListener('resize', fit);
})();
