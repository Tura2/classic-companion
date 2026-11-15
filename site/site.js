// Shared by the English and Hebrew pages.
document.documentElement.classList.add("js");
const RTL = document.documentElement.dir === "rtl";

// The tour: without the script every screen shows in a column; with it, the dashboard's tabs.
(function(){
  const list=document.querySelector(".tabs"), tabs=[...list.querySelectorAll('[role="tab"]')];
  list.hidden=false;
  tabs.forEach(t=>{const p=document.getElementById(t.getAttribute("aria-controls"));p.setAttribute("role","tabpanel");p.tabIndex=0;});
  function pick(t,focus){
    tabs.forEach(b=>{const on=b===t;b.setAttribute("aria-selected",on);b.tabIndex=on?0:-1;
      document.getElementById(b.getAttribute("aria-controls")).hidden=!on;});
    if(focus)t.focus();
  }
  pick(tabs[0]);
  tabs.forEach((t,i)=>{
    t.addEventListener("click",()=>pick(t));
    t.addEventListener("keydown",e=>{
      const k={ArrowRight:RTL?-1:1,ArrowLeft:RTL?1:-1}[e.key];
      if(k){e.preventDefault();pick(tabs[(i+k+tabs.length)%tabs.length],true);}
      if(e.key==="Home"){e.preventDefault();pick(tabs[0],true);}
      if(e.key==="End"){e.preventDefault();pick(tabs[tabs.length-1],true);}
    });
  });
})();

// Each section's parts rise in once, a beat apart, as the section comes into view.
(function(){
  if(matchMedia("(prefers-reduced-motion: reduce)").matches||!("IntersectionObserver" in window))return;
  const els=[...document.querySelectorAll(".in")];
  const seen=new Map();
  els.forEach(el=>{
    const s=el.closest("section")||document.body, n=seen.get(s)||0;
    seen.set(s,n+1);
    el.style.transitionDelay=(n*75)+"ms";
    el.classList.add("pre");
  });
  const io=new IntersectionObserver(es=>es.forEach(e=>{
    if(!e.isIntersecting)return;
    e.target.classList.add("show");e.target.classList.remove("pre");io.unobserve(e.target);
  }),{rootMargin:"0px 0px -8% 0px"});
  requestAnimationFrame(()=>els.forEach(el=>io.observe(el)));
})();

// The latest release's version and date, in the page's own words (data-label); the plain link works without it.
fetch("https://api.github.com/repos/Tura2/classic-companion/releases/latest")
  .then(r=>r.ok?r.json():null).then(r=>{
    if(!r||!r.tag_name)return;
    const lang=document.documentElement.lang==="he"?"he-IL":"en-GB";
    const d=new Date(r.published_at).toLocaleDateString(lang,{day:"numeric",month:"short",year:"numeric"});
    const exe=(r.assets||[]).find(a=>a.name==="Companion.exe");
    // the buttons point straight at Companion.exe; if a release ever lacks it, send them to the release page
    if(!exe)document.querySelectorAll("a.dl").forEach(a=>a.href=r.html_url);
    const s=exe?Math.round(exe.size/1048576)+" MB":"";
    for(const id of ["dl","ver"]){
      const el=document.getElementById(id);
      if(el&&el.dataset.label)el.textContent=el.dataset.label.replace("{v}",r.tag_name).replace("{d}",d).replace(", {s}",s?", "+s:"");
    }
  }).catch(()=>{});
