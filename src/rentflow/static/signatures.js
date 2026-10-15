document.addEventListener("DOMContentLoaded",()=>{
 document.querySelectorAll(".signature-form").forEach(form=>{
 const canvas=form.querySelector("canvas"),ctx=canvas.getContext("2d");let drawing=false,ink=false;
 ctx.lineWidth=3;ctx.lineCap="round";ctx.strokeStyle="#16332d";
 const point=e=>{const r=canvas.getBoundingClientRect();return[(e.clientX-r.left)*canvas.width/r.width,(e.clientY-r.top)*canvas.height/r.height]};
 canvas.addEventListener("pointerdown",e=>{drawing=true;canvas.setPointerCapture(e.pointerId);ctx.beginPath();ctx.moveTo(...point(e));e.preventDefault()});
 canvas.addEventListener("pointermove",e=>{if(drawing){ctx.lineTo(...point(e));ctx.stroke();ink=true;e.preventDefault()}});
 canvas.addEventListener("pointerup",()=>drawing=false);canvas.addEventListener("pointercancel",()=>drawing=false);
 form.querySelector(".clear-signature").addEventListener("click",()=>{ctx.clearRect(0,0,canvas.width,canvas.height);ink=false});
 form.addEventListener("submit",e=>{if(!ink){e.preventDefault();e.stopImmediatePropagation();alert("Bitte zuerst unterschreiben.");return}form.querySelector("[name=signature]").value=canvas.toDataURL("image/png")},true);
 });
});