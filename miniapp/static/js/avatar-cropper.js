/**
 * Avatar cropper module — circular crop with drag + zoom.
 * Usage: openAvatarCropper(file, onSave) where onSave receives a Blob (JPEG).
 */
export function createAvatarCropperModule() {
  const OUTPUT_SIZE = 512; // export resolution px

  /**
   * Open a fullscreen modal with the image, circular mask, drag & zoom.
   * @param {File} file - selected image file
   * @param {(blob: Blob) => void} onSave - called with cropped JPEG blob
   */
  function open(file, onSave) {
    console.log("[avatar-cropper] open called, file:", file?.name, file?.size);
    const reader = new FileReader();
    reader.onload = () => {
      console.log("[avatar-cropper] file read, dataUrl length:", reader.result?.length);
      _buildModal(reader.result, onSave);
    };
    reader.onerror = (err) => {
      console.error("[avatar-cropper] FileReader error:", err);
    };
    reader.readAsDataURL(file);
  }

  function _buildModal(dataUrl, onSave) {
    // ── State ──
    let scale = 1;
    let minScale = 1;
    let offsetX = 0;
    let offsetY = 0;
    let dragging = false;
    let dragStartX = 0;
    let dragStartY = 0;
    let dragOffsetX = 0;
    let dragOffsetY = 0;
    let lastPinchDist = 0;
    const img = new Image();

    // ── DOM ──
    const backdrop = document.createElement("div");
    backdrop.className = "avatar-cropper-backdrop";
    backdrop.innerHTML = `
      <div class="avatar-cropper-modal">
        <div class="avatar-cropper-header">
          <h3>Кадрирование аватарки</h3>
          <button class="secondary-button avatar-cropper-close" type="button">
            <i data-lucide="x" style="width:18px;height:18px"></i>
          </button>
        </div>
        <div class="avatar-cropper-body">
          <canvas class="avatar-cropper-canvas"></canvas>
          <div class="avatar-cropper-hint">Перетащите для перемещения, прокрутите для масштабирования</div>
        </div>
        <div class="avatar-cropper-footer">
          <div class="avatar-cropper-zoom-row">
            <i data-lucide="zoom-out" style="width:16px;height:16px;color:var(--muted)"></i>
            <input type="range" class="avatar-cropper-zoom" min="100" max="400" value="100" />
            <i data-lucide="zoom-in" style="width:16px;height:16px;color:var(--muted)"></i>
          </div>
          <div class="avatar-cropper-actions">
            <button class="secondary-button avatar-cropper-cancel" type="button">Отмена</button>
            <button class="primary-button avatar-cropper-save" type="button">
              <i data-lucide="check" style="width:16px;height:16px"></i><span>Сохранить</span>
            </button>
          </div>
        </div>
      </div>
    `;

    const canvas = backdrop.querySelector(".avatar-cropper-canvas");
    const ctx = canvas.getContext("2d");
    const zoomSlider = backdrop.querySelector(".avatar-cropper-zoom");

    function close() {
      backdrop.remove();
    }

    backdrop.querySelector(".avatar-cropper-close").addEventListener("click", close);
    backdrop.querySelector(".avatar-cropper-cancel").addEventListener("click", close);
    // Defer backdrop-click-to-close to avoid the originating click event
    // (from the file input label) bubbling up and immediately closing the modal
    requestAnimationFrame(() => {
      backdrop.addEventListener("click", (e) => {
        if (e.target === backdrop) close();
      });
    });

    // ── Image load ──
    img.onload = () => {
      _initCanvas();
      _draw();
      if (window.lucide) lucide.createIcons({ nodes: [backdrop] });
    };
    img.src = dataUrl;

    // ── Canvas sizing ──
    function _initCanvas() {
      const modal = backdrop.querySelector(".avatar-cropper-modal");
      const bodyEl = backdrop.querySelector(".avatar-cropper-body");
      // Use modal width, ensure square-ish canvas
      const size = Math.min(bodyEl.clientWidth, window.innerHeight * 0.55);
      const dpr = window.devicePixelRatio || 1;
      canvas.width = size * dpr;
      canvas.height = size * dpr;
      canvas.style.width = size + "px";
      canvas.style.height = size + "px";
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

      // Compute min scale so image covers the circle
      const circleR = size * 0.42;
      const circleDiam = circleR * 2;
      minScale = circleDiam / Math.min(img.naturalWidth, img.naturalHeight);
      scale = minScale;
      offsetX = 0;
      offsetY = 0;
      zoomSlider.min = Math.round(minScale * 100);
      zoomSlider.max = Math.round(minScale * 400);
      zoomSlider.value = Math.round(scale * 100);
    }

    function _draw() {
      const w = canvas.width / (window.devicePixelRatio || 1);
      const h = canvas.height / (window.devicePixelRatio || 1);
      const cx = w / 2;
      const cy = h / 2;
      const circleR = w * 0.42;

      ctx.clearRect(0, 0, w, h);

      // Draw image centered + offset
      const iw = img.naturalWidth * scale;
      const ih = img.naturalHeight * scale;
      const ix = cx - iw / 2 + offsetX;
      const iy = cy - ih / 2 + offsetY;
      ctx.drawImage(img, ix, iy, iw, ih);

      // Dark overlay outside circle
      ctx.save();
      ctx.fillStyle = "rgba(0, 0, 0, 0.55)";
      ctx.beginPath();
      ctx.rect(0, 0, w, h);
      ctx.arc(cx, cy, circleR, 0, Math.PI * 2, true);
      ctx.fill("evenodd");

      // Circle border
      ctx.strokeStyle = "rgba(255, 255, 255, 0.6)";
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(cx, cy, circleR, 0, Math.PI * 2);
      ctx.stroke();
      ctx.restore();
    }

    // ── Clamp offsets so image always covers circle ──
    function _clamp() {
      const w = canvas.width / (window.devicePixelRatio || 1);
      const circleR = w * 0.42;
      const iw = img.naturalWidth * scale;
      const ih = img.naturalHeight * scale;
      const maxX = iw / 2 - circleR;
      const maxY = ih / 2 - circleR;
      offsetX = Math.max(-maxX, Math.min(maxX, offsetX));
      offsetY = Math.max(-maxY, Math.min(maxY, offsetY));
    }

    // ── Zoom ──
    function _setScale(newScale) {
      scale = Math.max(minScale, Math.min(minScale * 4, newScale));
      zoomSlider.value = Math.round(scale * 100);
      _clamp();
      _draw();
    }

    zoomSlider.addEventListener("input", () => {
      _setScale(parseInt(zoomSlider.value, 10) / 100);
    });

    canvas.addEventListener("wheel", (e) => {
      e.preventDefault();
      const delta = e.deltaY > 0 ? -0.03 : 0.03;
      _setScale(scale + delta * scale);
    }, { passive: false });

    // ── Drag (mouse) ──
    canvas.addEventListener("mousedown", (e) => {
      dragging = true;
      dragStartX = e.clientX;
      dragStartY = e.clientY;
      dragOffsetX = offsetX;
      dragOffsetY = offsetY;
      canvas.style.cursor = "grabbing";
    });

    window.addEventListener("mousemove", (e) => {
      if (!dragging) return;
      offsetX = dragOffsetX + (e.clientX - dragStartX);
      offsetY = dragOffsetY + (e.clientY - dragStartY);
      _clamp();
      _draw();
    });

    window.addEventListener("mouseup", () => {
      dragging = false;
      canvas.style.cursor = "grab";
    });

    // ── Drag (touch) ──
    canvas.addEventListener("touchstart", (e) => {
      if (e.touches.length === 1) {
        dragging = true;
        dragStartX = e.touches[0].clientX;
        dragStartY = e.touches[0].clientY;
        dragOffsetX = offsetX;
        dragOffsetY = offsetY;
      } else if (e.touches.length === 2) {
        dragging = false;
        lastPinchDist = _pinchDist(e.touches);
      }
    }, { passive: true });

    canvas.addEventListener("touchmove", (e) => {
      e.preventDefault();
      if (e.touches.length === 1 && dragging) {
        offsetX = dragOffsetX + (e.touches[0].clientX - dragStartX);
        offsetY = dragOffsetY + (e.touches[0].clientY - dragStartY);
        _clamp();
        _draw();
      } else if (e.touches.length === 2) {
        const dist = _pinchDist(e.touches);
        if (lastPinchDist > 0) {
          const ratio = dist / lastPinchDist;
          _setScale(scale * ratio);
        }
        lastPinchDist = dist;
      }
    }, { passive: false });

    canvas.addEventListener("touchend", () => {
      dragging = false;
      lastPinchDist = 0;
    });

    function _pinchDist(touches) {
      const dx = touches[0].clientX - touches[1].clientX;
      const dy = touches[0].clientY - touches[1].clientY;
      return Math.sqrt(dx * dx + dy * dy);
    }

    // ── Save ──
    backdrop.querySelector(".avatar-cropper-save").addEventListener("click", () => {
      const blob = _exportBlob();
      if (blob) {
        close();
        onSave(blob);
      }
    });

    function _exportBlob() {
      const w = canvas.width / (window.devicePixelRatio || 1);
      const circleR = w * 0.42;
      const cx = w / 2;
      const cy = w / 2;

      const out = document.createElement("canvas");
      out.width = OUTPUT_SIZE;
      out.height = OUTPUT_SIZE;
      const outCtx = out.getContext("2d");

      // Source region in image coordinates
      const iw = img.naturalWidth * scale;
      const ih = img.naturalHeight * scale;
      const imgX = cx - iw / 2 + offsetX;
      const imgY = cy - ih / 2 + offsetY;

      // Circle bounds in canvas coords
      const cropLeft = cx - circleR;
      const cropTop = cy - circleR;
      const cropSize = circleR * 2;

      // Map back to original image pixel coords
      const srcX = (cropLeft - imgX) / scale;
      const srcY = (cropTop - imgY) / scale;
      const srcSize = cropSize / scale;

      // Clip to circle
      outCtx.beginPath();
      outCtx.arc(OUTPUT_SIZE / 2, OUTPUT_SIZE / 2, OUTPUT_SIZE / 2, 0, Math.PI * 2);
      outCtx.closePath();
      outCtx.clip();

      outCtx.drawImage(img, srcX, srcY, srcSize, srcSize, 0, 0, OUTPUT_SIZE, OUTPUT_SIZE);

      // Convert to blob synchronously via toDataURL → fetch
      const dataUrl = out.toDataURL("image/jpeg", 0.92);
      const binary = atob(dataUrl.split(",")[1]);
      const array = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i++) array[i] = binary.charCodeAt(i);
      return new Blob([array], { type: "image/jpeg" });
    }

    // ── Mount ──
    document.body.appendChild(backdrop);
    canvas.style.cursor = "grab";
  }

  return { open };
}
