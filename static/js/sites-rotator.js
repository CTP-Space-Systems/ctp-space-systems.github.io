    (function(){
      /* CTPVerse Sites rotator — random 1:1 banner, one of the seven other CTP sites.
   Own site (CTP Space Systems) is excluded. Ids are the source's ctpsites-link /
   ctpsites-img. Local org-avatar files in /assets/sites/, no hotlinking. */
      var sites = [
        { name: 'CTPVerse Dashboard', img: '/assets/sites/ctpverse-org-avatar.jpg', url: 'https://ctpverse.github.io/' },
        { name: 'CTP-EOS', img: '/assets/sites/ctp-eos-triangle-logo.jpg', url: 'https://ctp-eos.github.io/' },
        { name: 'CTP Magazine', img: '/assets/sites/ctp-magazine-1254x1254.png', url: 'https://ctp-magazine.github.io/' },
        { name: 'FIN-DSP', img: '/assets/sites/findsp-logo-200x200.jpg', url: 'https://fin-dsp.github.io/' },
        { name: 'CTP Music Portal', img: '/assets/sites/ctp-music-org-avatar.jpg', url: 'https://ctp-music.github.io/' },
        { name: 'CTP-PSY', img: '/assets/sites/ctp-psy-org-avatar.jpg', url: 'https://ctp-psy.github.io/' },
        { name: 'CTPETEAMS', img: '/assets/sites/ctpeteams-logo-400.jpg', url: 'https://ctpeteams.github.io/' },
        { name: 'CTPIDM', img: '/assets/sites/ctpidm-org-avatar.jpg', url: 'https://ctpidm.github.io/' }
      ];
      var link = document.getElementById('ctpsites-link');
      var img = document.getElementById('ctpsites-img');
      if(!link || !img || sites.length < 2) return;
      var idx = 0;
      var timer = null;
      var reduceMotion = false;
      try{ reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches; }catch(e){}
      function show(i){
        idx = i;
        img.src = sites[i].img;
        img.alt = sites[i].name;
        link.href = sites[i].url;
        link.title = sites[i].name + ' — visit the site';
      }
      function randomNext(){
        var n = idx;
        while(n === idx){ n = Math.floor(Math.random() * sites.length); }
        show(n);
      }
      function stop(){ if(timer){ clearInterval(timer); timer = null; } }
      function start(){
        stop();
        if(reduceMotion) return;
        timer = setInterval(randomNext, 5000);
      }
      document.addEventListener('visibilitychange', function(){ if(document.hidden){ stop(); } else { start(); } });
      start();
    })();
