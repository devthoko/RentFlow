document.documentElement.dataset.theme=localStorage.getItem("rentflow-theme")||"light";document.addEventListener("DOMContentLoaded",()=>{document.getElementById("theme-toggle")?.addEventListener("click",()=>{let t=document.documentElement.dataset.theme==="dark"?"light":"dark";document.documentElement.dataset.theme=t;localStorage.setItem("rentflow-theme",t)});document.querySelectorAll("nav a").forEach(a=>{if(a.pathname==="/" ? location.pathname==="/" : location.pathname.startsWith(a.pathname))a.classList.add("active")});document.querySelectorAll("form").forEach(f=>f.addEventListener("submit",()=>{f.querySelectorAll("button[type=submit],button:not([type])").forEach(b=>{b.disabled=true;b.dataset.original=b.textContent;b.textContent="Wird gespeichert …"})}));});
document.addEventListener("DOMContentLoaded",()=>{
 document.querySelectorAll("[data-icon]").forEach(a=>{const icon=document.createElement("i");icon.dataset.lucide=a.dataset.icon;a.prepend(icon)});
 if(window.lucide)lucide.createIcons();
 document.querySelectorAll(".photo-upload").forEach(input=>input.addEventListener("change",async()=>{
  const form=input.closest("form"),target=form.elements[input.dataset.target],preview=input.parentElement.parentElement.querySelector(".photo-previews");
  const submit=form.querySelector("button.primary");submit.disabled=true;
  try{for(const file of input.files){const data=new FormData();data.set("file",file);data.set("csrf",form.elements.csrf.value);
   const result=await fetch("/orders/"+input.dataset.order+"/photo",{method:"POST",body:data});
   if(!result.ok)throw new Error("Foto konnte nicht gespeichert werden. Bitte Dateityp und Größe prüfen.");
   const asset=await result.json();target.value=[target.value,asset.id].filter(Boolean).join(",");
   const image=document.createElement("img");image.src=asset.url;image.className="thumb";image.alt="Dokumentiertes Foto";preview.append(image);
  }}catch(error){const notice=document.createElement("p");notice.className="danger";notice.textContent=error.message;preview.append(notice)}
  finally{submit.disabled=false;input.value=""}
 }));
});
