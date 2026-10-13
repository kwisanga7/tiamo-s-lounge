document.addEventListener('DOMContentLoaded',()=>{
  const start=document.getElementById('start-scan'),stop=document.getElementById('stop-scan'),video=document.getElementById('scanner-video'),overlay=document.querySelector('.scanner-overlay'),placeholder=document.getElementById('scanner-placeholder'),status=document.getElementById('scan-status'),input=document.getElementById('ticket_code');
  if(!start)return;
  let stream=null,active=false;
  const stopCamera=()=>{active=false;if(stream)stream.getTracks().forEach(track=>track.stop());stream=null;video.srcObject=null;overlay.classList.remove('active');placeholder.style.display='flex';start.hidden=false;stop.hidden=true};
  start.addEventListener('click',async()=>{
    if(!('BarcodeDetector' in window)){status.textContent='Camera QR scanning is not supported here. Enter the code below.';return}
    try{const detector=new BarcodeDetector({formats:['qr_code']});stream=await navigator.mediaDevices.getUserMedia({video:{facingMode:'environment'}});video.srcObject=stream;await video.play();placeholder.style.display='none';overlay.classList.add('active');start.hidden=true;stop.hidden=false;active=true;status.textContent='Point the camera at a paid ticket QR code.';
      const scan=async()=>{if(!active)return;try{const codes=await detector.detect(video);if(codes.length){input.value=codes[0].rawValue;stopCamera();status.textContent='QR captured. Verify the ticket below.';return}}catch(e){}requestAnimationFrame(scan)};scan();
    }catch(error){status.textContent='Camera access was blocked. Enter the ticket code below instead.';stopCamera()}
  });
  stop.addEventListener('click',stopCamera);
  window.addEventListener('pagehide',stopCamera);
});
