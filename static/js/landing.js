/* =========================================================================
   MessForecast — landing page motion
   -------------------------------------------------------------------------
   GSAP, vendored beside the page: the kitchen tablet runs without a network,
   so the landing page cannot reach a CDN either.

   One settle on the hero, one fade-up as each row arrives, and one count as
   the measured figures land. Every tween moves transform and opacity only,
   every tween is scoped to this page, and the whole thing stands down when
   the reader has asked for less motion. With scripting off the page is
   simply there.
   ========================================================================= */
(function () {
  'use strict';

  if (!window.gsap || !window.ScrollTrigger) { return; }

  gsap.registerPlugin(ScrollTrigger);

  var mm = gsap.matchMedia();

  mm.add('(prefers-reduced-motion: no-preference)', function () {
    var ctx = gsap.context(function () {
      /* --- the hero settles once -------------------------------------- */
      gsap
        .timeline({ defaults: { ease: 'power3.out' } })
        .fromTo(
          '.lp-hero-text > *',
          { autoAlpha: 0, y: 12 },
          { autoAlpha: 1, y: 0, duration: 0.45, stagger: 0.07 }
        )
        .fromTo(
          '.lp-shot-hero',
          { autoAlpha: 0, y: 16 },
          { autoAlpha: 1, y: 0, duration: 0.5 },
          0.08
        );

      /* --- each row arrives as it comes into view ---------------------- */
      gsap.utils.toArray('[data-reveal]').forEach(function (el) {
        gsap.fromTo(
          el,
          { autoAlpha: 0, y: 14 },
          {
            autoAlpha: 1,
            y: 0,
            duration: 0.5,
            ease: 'power3.out',
            scrollTrigger: {
              trigger: el,
              start: 'top 84%',
              once: true,
            },
          }
        );
      });

      /* --- the measured figures count up once --------------------------- */
      var figs = gsap.utils.toArray('[data-fig]');
      if (figs.length) {
        var tl = gsap.timeline({
          scrollTrigger: {
            trigger: figs[0].closest('table') || figs[0],
            start: 'top 86%',
            once: true,
          },
        });
        figs.forEach(function (el, i) {
          var target = parseFloat(el.getAttribute('data-fig'));
          var decimals = parseInt(el.getAttribute('data-decimals'), 10) || 0;
          var prefix = el.getAttribute('data-prefix') || '';
          var suffix = el.getAttribute('data-suffix') || '';
          var fmt = new Intl.NumberFormat('en-US', {
            minimumFractionDigits: decimals,
            maximumFractionDigits: decimals,
          });
          var proxy = { v: 0 };
          tl.to(
            proxy,
            {
              v: target,
              duration: 0.9,
              ease: 'power2.out',
              onUpdate: function () {
                el.textContent = prefix + fmt.format(proxy.v) + suffix;
              },
            },
            i * 0.08
          );
        });
      }
    });

    return function () {
      ctx.revert();
    };
  });

  /* The web fonts settle after the first paint, so the scroll measurements
     are taken again once they have. */
  if (document.fonts && document.fonts.ready) {
    document.fonts.ready.then(function () {
      ScrollTrigger.refresh();
    });
  }
})();
