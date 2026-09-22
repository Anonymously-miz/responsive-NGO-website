(function(){
  // Map of Font Awesome icon class -> emoji fallback
  var FA_EMOJI = {
    'fa-shield':'🛡️',
    'fa-handshake-angle':'🤝',
    'fa-people-group':'👥',
    'fa-eye':'👁️',
    'fa-lightbulb':'💡',
    'fa-leaf':'🌿',
    'fa-scale-balanced':'⚖️',
    'fa-circle':'◯',
    'fa-check':'✅',
    'fa-times':'❌'
  };

  function fontAwesomeLoaded(){
    try{
      var el = document.createElement('i');
      el.className = 'fa-solid';
      el.style.position = 'absolute';
      el.style.left = '-9999px';
      document.body.appendChild(el);
      var cs = window.getComputedStyle(el);
      var ff = (cs && cs.fontFamily) ? cs.fontFamily.toLowerCase() : '';
      document.body.removeChild(el);
      if(!ff) return false;
      return ff.indexOf('fontawesome') !== -1 || ff.indexOf('font awesome') !== -1 || ff.indexOf('fa-') !== -1;
    }catch(e){
      return false;
    }
  }

  function replaceIcons(){
    document.querySelectorAll('i').forEach(function(i){
      if(!i.className) return;
      var classes = i.className.split(/\s+/);
      var faClass = classes.find(function(c){ return c.indexOf('fa-') === 0 && c !== 'fa' && c !== 'fa-solid' && c !== 'fa-regular' && c !== 'fa-brands'; });
      if(!faClass) return;
      var emoji = FA_EMOJI[faClass];
      if(!emoji) return;
      // Replace the <i> element with a text node (keeps layout simple)
      var span = document.createElement('span');
      span.className = 'icon-fallback';
      span.textContent = emoji;
      // try to copy font-size from parent if present
      try{
        var ps = window.getComputedStyle(i.parentElement);
        if(ps && ps.fontSize) span.style.fontSize = ps.fontSize;
      }catch(e){}
      i.parentNode.replaceChild(span, i);
    });
  }

  if(document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', function(){ if(!fontAwesomeLoaded()){ replaceIcons(); } });
  } else {
    if(!fontAwesomeLoaded()) replaceIcons();
  }
})();
