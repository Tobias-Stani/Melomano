// Girar la caja 3D: arrastrar, flechas del teclado, doble click da vuelta,
// botones [data-view] llevan a frente / lomo / dorso.
(function () {
    const stage = document.querySelector('.case-stage');
    if (!stage) return;
    const box = stage.querySelector('[data-case3d]');
    const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;

    let ry = -24, rx = -6, vy = 0, dragging = false, touched = false, lastX = 0, lastY = 0;

    function render() {
        box.style.transform = `rotateX(${rx}deg) rotateY(${ry}deg)`;
        box.style.setProperty('--rot', ((ry % 360) + 360) % 360 / 3.6);
    }

    function snapTo(y, x = -4) {
        touched = true;
        vy = 0;
        // Ir por el camino más corto al ángulo pedido
        const cur = ((ry % 360) + 360) % 360;
        let delta = y - cur;
        if (delta > 180) delta -= 360;
        if (delta < -180) delta += 360;
        box.classList.add('snap');
        ry += delta; rx = x;
        render();
        setTimeout(() => box.classList.remove('snap'), 700);
    }

    stage.addEventListener('pointerdown', e => {
        dragging = touched = true;
        box.classList.remove('snap');
        lastX = e.clientX; lastY = e.clientY; vy = 0;
        stage.setPointerCapture(e.pointerId);
    });
    stage.addEventListener('pointermove', e => {
        if (!dragging) return;
        vy = (e.clientX - lastX) * .5;
        ry += vy;
        rx = Math.max(-30, Math.min(30, rx - (e.clientY - lastY) * .3));
        lastX = e.clientX; lastY = e.clientY;
        render();
    });
    const release = () => { dragging = false; };
    stage.addEventListener('pointerup', release);
    stage.addEventListener('pointercancel', release);
    stage.addEventListener('dblclick', () => snapTo((((ry % 360) + 360) % 360 + 180) % 360));

    stage.addEventListener('keydown', e => {
        const step = { ArrowLeft: -20, ArrowRight: 20 }[e.key];
        if (step === undefined) return;
        e.preventDefault();
        touched = true;
        box.classList.add('snap');
        ry += step;
        render();
    });

    document.querySelectorAll('[data-view]').forEach(btn =>
        btn.addEventListener('click', () => snapTo(+btn.dataset.view)));

    // Inercia al soltar + balanceo suave mientras nadie la toca
    let t = 0;
    function tick() {
        if (!dragging && Math.abs(vy) > .05) {
            vy *= .94;
            ry += vy;
            render();
        } else if (!touched && !reduced) {
            t += .012;
            ry = -24 + Math.sin(t) * 14;
            render();
        }
        requestAnimationFrame(tick);
    }
    render();
    requestAnimationFrame(tick);
})();
